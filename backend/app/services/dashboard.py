"""Section 6.5's metrics registry, implemented. Every number here is
recomputed live from `cases`/`case_transfers`/`overlap_groups` on each
call — there is no `dashboard_counters` cache table yet (see
docs/limitations.md: at this data volume, live recomputation is both
simpler and impossible to let drift from reality, which is exactly the
property Section 6.5 asks a reconciliation test to prove). Exact SQL
per metric is documented in `docs/metrics.md`; this module is that
documentation turned into code, not a second, divergent definition of
the same numbers.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CASE_STATUSES, Bureau, Case, CaseTransfer, OverlapCandidate, OverlapGroup
from app.services.sla import (
    CaseSlaFacts,
    compute_due_at,
    compute_sla_status,
    fetch_holidays,
    fetch_policy,
)


@dataclass
class PolicyCache:
    """Avoids re-querying `sla_policies` once per case when computing
    tiles over every open case — the same (source, matter_type,
    priority) combination repeats heavily in real data."""

    session: AsyncSession
    _cache: dict[tuple[str, str, str], Any] = field(default_factory=dict)

    async def get(self, source_channel: str, matter_type: str, priority: str):
        key = (source_channel, matter_type, priority)
        if key not in self._cache:
            self._cache[key] = await fetch_policy(
                self.session, source_channel=source_channel, matter_type=matter_type, priority=priority
            )
        return self._cache[key]


async def sla_facts_fast(
    session: AsyncSession, case: Case, *, holidays: frozenset[dt.date], policy_cache: PolicyCache, now: dt.datetime
) -> CaseSlaFacts:
    policy = await policy_cache.get(case.source_channel, case.matter_type, case.priority)
    if policy is None:
        return CaseSlaFacts(None, None, "not_set")
    due_at = compute_due_at(case.received_at, policy, holidays)
    status = compute_sla_status(case.received_at, due_at, now=now, holidays=holidays, warn_at=policy.warn_at)
    return CaseSlaFacts(policy, due_at, status)


AGEING_BUCKETS = [(0, 5), (6, 10), (11, 20), (21, None)]


async def compute_tiles(session: AsyncSession, *, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.UTC)
    holidays = await fetch_holidays(session)
    policy_cache = PolicyCache(session)

    status_rows = (await session.execute(select(Case.status, func.count()).group_by(Case.status))).all()
    status_counts = {s: 0 for s in CASE_STATUSES}
    for status_name, count in status_rows:
        status_counts[status_name] = count
    total_cases = sum(status_counts.values())

    open_cases = (
        await session.execute(select(Case).where(Case.status != "disposed"))
    ).scalars().all()

    beyond_timeline = 0
    approaching = 0
    ageing = {f"{lo}-{hi if hi is not None else '+'}": 0 for lo, hi in AGEING_BUCKETS}
    workload: dict[str | None, dict[str, int]] = {}
    for case in open_cases:
        facts = await sla_facts_fast(session, case, holidays=holidays, policy_cache=policy_cache, now=now)
        if facts.status == "breached":
            beyond_timeline += 1
        elif facts.status == "approaching":
            approaching += 1

        age_days = (now.date() - case.received_at.date()).days
        for lo, hi in AGEING_BUCKETS:
            if age_days >= lo and (hi is None or age_days <= hi):
                ageing[f"{lo}-{hi if hi is not None else '+'}"] += 1
                break

        key = str(case.assigned_bureau_id) if case.assigned_bureau_id else None
        bucket = workload.setdefault(key, {"open": 0, "overdue": 0})
        bucket["open"] += 1
        if facts.status == "breached":
            bucket["overdue"] += 1

    bureau_rows = (await session.execute(select(Bureau.id, Bureau.name))).all()
    bureau_names = {str(bid): name for bid, name in bureau_rows}
    bureau_workload = [
        {
            "bureau_id": bureau_id,
            "bureau_name": bureau_names.get(bureau_id, "Unassigned") if bureau_id else "Unassigned",
            "open": counts["open"],
            "overdue": counts["overdue"],
        }
        for bureau_id, counts in sorted(workload.items(), key=lambda kv: kv[1]["open"], reverse=True)
    ]

    transfers_awaiting = (
        await session.execute(
            select(func.count()).select_from(CaseTransfer).where(CaseTransfer.state == "proposed")
        )
    ).scalar_one()

    overlap_rows = (
        await session.execute(
            select(OverlapGroup.institution_id, func.count(OverlapCandidate.id))
            .join(OverlapCandidate, OverlapCandidate.group_id == OverlapGroup.id)
            .where(OverlapCandidate.status == "pending")
            .group_by(OverlapGroup.institution_id)
            .order_by(func.count(OverlapCandidate.id).desc())
            .limit(3)
        )
    ).all()
    overlap_queue_total = (
        await session.execute(
            select(func.count()).select_from(OverlapCandidate).where(OverlapCandidate.status == "pending")
        )
    ).scalar_one()

    return {
        "as_of": now.isoformat(),
        "total_cases": total_cases,
        "pending": status_counts["pending"],
        "under_process": status_counts["under_process"],
        "escalated": status_counts["escalated"],
        "transferred": status_counts["transferred"],
        "disposed": status_counts["disposed"],
        "beyond_timeline": beyond_timeline,
        "approaching": approaching,
        "ageing_buckets": ageing,
        "bureau_workload": bureau_workload,
        "transfers_awaiting_acceptance": transfers_awaiting,
        "overlap_queue_total": overlap_queue_total,
        "overlap_queue_top_institutions": [
            {"institution_id": str(inst_id), "pending_candidates": count} for inst_id, count in overlap_rows
        ],
    }


async def compute_monthly_series(session: AsyncSession, *, months: int = 6, now: dt.datetime | None = None):
    """Section 9.6's "Monthly received vs disposed" bar chart. Buckets by
    calendar month in Python (not a DB `date_trunc` grouping) so the
    same bucket-edge logic is trivially testable without a live
    Postgres connection — acceptable at this data volume; would move to
    SQL if case volume made the full-table scan a problem (see
    docs/limitations.md)."""
    now = now or dt.datetime.now(dt.UTC)
    month_keys: list[tuple[int, int]] = []
    y, m = now.year, now.month
    for _ in range(months):
        month_keys.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_keys.reverse()

    received_rows = (await session.execute(select(Case.received_at))).scalars().all()
    disposed_rows = (
        await session.execute(select(Case.disposed_at).where(Case.disposed_at.is_not(None)))
    ).scalars().all()

    def bucket_counts(timestamps: list[dt.datetime]) -> dict[tuple[int, int], int]:
        counts: dict[tuple[int, int], int] = {}
        for ts in timestamps:
            key = (ts.year, ts.month)
            counts[key] = counts.get(key, 0) + 1
        return counts

    received_counts = bucket_counts(received_rows)
    disposed_counts = bucket_counts(disposed_rows)

    return [
        {
            "month": f"{y:04d}-{m:02d}",
            "received": received_counts.get((y, m), 0),
            "disposed": disposed_counts.get((y, m), 0),
        }
        for y, m in month_keys
    ]
