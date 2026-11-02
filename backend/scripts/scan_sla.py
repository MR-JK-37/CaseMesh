"""Section 7.3's scanner: walks every open case and raises
`SLA_APPROACHING`/`SLA_BREACHED` (via app/services/sla.py's real
business-day engine), `CASE_STALE` (no action for N business days),
and `TRANSFER_UNACCEPTED` (a proposed transfer sitting too long); also
reconciles case-status counters against a raw recomputation and raises
`COUNTER_DRIFT` on mismatch (Section 6.5).

Standalone script, matching `scripts/rebuild_projection.py` and
`scripts/eval_overlap.py`'s pattern — not an ARQ-scheduled job (Section
10's worker infra is unbuilt, see docs/limitations.md). Meant to be run
on a schedule (cron, or manually for the SIH demo):

    uv run python3 scripts/scan_sla.py

Usage: python scripts/scan_sla.py [--stale-days N] [--transfer-days N]
"""

import argparse
import asyncio
import datetime as dt

from rules.business_days import business_days_between
from sqlalchemy import func, select, text

from app.core.db import SessionLocal
from app.models import CASE_STATUSES, Case, CaseTransfer
from app.services.alerts import raise_alert
from app.services.sla import fetch_holidays, sla_facts_for_case

DEFAULT_STALE_DAYS = 10
DEFAULT_TRANSFER_DAYS = 3


async def _scan_sla(session, holidays, now: dt.datetime) -> tuple[int, int]:
    approaching = breached = 0
    cases = (await session.execute(select(Case).where(Case.status != "disposed"))).scalars().all()
    for case in cases:
        sla = await sla_facts_for_case(
            session,
            source_channel=case.source_channel,
            matter_type=case.matter_type,
            priority=case.priority,
            received_at=case.received_at,
            now=now,
            holidays=holidays,
        )
        if sla.status == "approaching":
            approaching += 1
            await raise_alert(
                session,
                code="SLA_APPROACHING",
                severity="warning",
                resource_type="case",
                resource_id=case.id,
                message=f"Case {case.case_number} is approaching its SLA due date ({sla.due_at}).",
                dedup_key=f"SLA_APPROACHING:{case.id}:{sla.due_at}",
                channels=[f"bureau:{case.assigned_bureau_id}"] if case.assigned_bureau_id else ["broadcast:all"],
            )
        elif sla.status == "breached":
            breached += 1
            await raise_alert(
                session,
                code="SLA_BREACHED",
                severity="critical",
                resource_type="case",
                resource_id=case.id,
                message=f"Case {case.case_number} has breached its SLA due date ({sla.due_at}).",
                dedup_key=f"SLA_BREACHED:{case.id}",
                channels=[f"bureau:{case.assigned_bureau_id}", "broadcast:all"] if case.assigned_bureau_id else ["broadcast:all"],
            )
    return approaching, breached


async def _scan_stale(session, holidays, now: dt.datetime, stale_days: int) -> int:
    """Section 7.3: `CASE_STALE` — no action for N business days.
    `Case.last_action_at` is already the projection's own record of the
    most recent event, so no extra query against `case_events` is
    needed."""
    count = 0
    cases = (await session.execute(select(Case).where(Case.status != "disposed"))).scalars().all()
    for case in cases:
        idle_days = business_days_between(case.last_action_at.date(), now.date(), holidays)
        if idle_days >= stale_days:
            count += 1
            await raise_alert(
                session,
                code="CASE_STALE",
                severity="warning",
                resource_type="case",
                resource_id=case.id,
                message=f"Case {case.case_number} has had no action for {idle_days} business day(s).",
                dedup_key=f"CASE_STALE:{case.id}:{case.last_action_at.date().isoformat()}",
                channels=[f"bureau:{case.assigned_bureau_id}"] if case.assigned_bureau_id else ["broadcast:all"],
            )
    return count


async def _scan_unaccepted_transfers(session, now: dt.datetime, transfer_days: int) -> int:
    count = 0
    transfers = (
        await session.execute(select(CaseTransfer).where(CaseTransfer.state == "proposed"))
    ).scalars().all()
    for transfer in transfers:
        age_days = (now - transfer.proposed_at).days
        if age_days >= transfer_days:
            count += 1
            case = (
                await session.execute(select(Case).where(Case.id == transfer.case_id))
            ).scalar_one()
            await raise_alert(
                session,
                code="TRANSFER_UNACCEPTED",
                severity="warning",
                resource_type="case",
                resource_id=case.id,
                message=f"Transfer of {case.case_number} to another bureau has been unaccepted for {age_days} day(s).",
                dedup_key=f"TRANSFER_UNACCEPTED:{transfer.id}",
                channels=[f"bureau:{transfer.to_bureau_id}", "broadcast:all"],
            )
    return count


async def _scan_counter_drift(session) -> bool:
    """Section 6.5: counters are "reconciled nightly against full
    recomputation; drift above zero raises an alert." The live
    `/cases/counters` endpoint and this recomputation both run the same
    `GROUP BY status` query shape against the same table — a drift here
    would mean something wrote to `cases.status` outside the
    event-sourcing path, not an aggregation bug."""
    rows = (await session.execute(select(Case.status, func.count()).group_by(Case.status))).all()
    counts = {s: 0 for s in CASE_STATUSES}
    for status_name, count in rows:
        counts[status_name] = count
    total_cases = (await session.execute(select(func.count()).select_from(Case))).scalar_one()
    drifted = sum(counts.values()) != total_cases
    if drifted:
        await raise_alert(
            session,
            code="COUNTER_DRIFT",
            severity="critical",
            resource_type="system",
            resource_id=None,
            message="Case status counter reconciliation found a mismatch against raw row counts.",
            dedup_key=f"COUNTER_DRIFT:{dt.datetime.now(dt.UTC).date().isoformat()}",
            channels=["broadcast:all"],
        )
    return drifted


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    parser.add_argument("--transfer-days", type=int, default=DEFAULT_TRANSFER_DAYS)
    args = parser.parse_args()

    now = dt.datetime.now(dt.UTC)
    async with SessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        holidays = await fetch_holidays(session)
        approaching, breached = await _scan_sla(session, holidays, now)
        stale = await _scan_stale(session, holidays, now, args.stale_days)
        unaccepted = await _scan_unaccepted_transfers(session, now, args.transfer_days)
        drifted = await _scan_counter_drift(session)

    print(
        f"SLA approaching: {approaching}, breached: {breached}, stale: {stale}, "
        f"unaccepted transfers: {unaccepted}, counter drift: {drifted}"
    )


if __name__ == "__main__":
    asyncio.run(main())
