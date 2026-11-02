"""Section 7.1/7.2: DB-aware wrapper around the pure `rules.business_days`
engine. This module is the only place that turns a case's
`(source_channel, matter_type, priority, received_at)` into a due date
and a status — never duplicated inline at a call site.
"""

import datetime as dt

from rules.business_days import add_business_days, business_days_between
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Holiday, SlaPolicy

SLA_STATUSES = ("not_set", "on_track", "approaching", "breached")


async def fetch_holidays(session: AsyncSession) -> frozenset[dt.date]:
    rows = (await session.execute(select(Holiday.holiday_date))).scalars().all()
    return frozenset(rows)


async def fetch_policy(
    session: AsyncSession, *, source_channel: str, matter_type: str, priority: str
) -> SlaPolicy | None:
    """Section 7.2: an exact (source, matter_type, priority) match wins;
    otherwise a (source, matter_type=NULL, priority) wildcard row
    applies. No match at all means "policy not set" — the caller raises
    `SLA_POLICY_MISSING`, never guesses a number (Section 0 rule 2)."""
    specific = (
        await session.execute(
            select(SlaPolicy)
            .where(
                SlaPolicy.source_channel == source_channel,
                SlaPolicy.matter_type == matter_type,
                SlaPolicy.priority == priority,
            )
            .order_by(SlaPolicy.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if specific is not None:
        return specific
    return (
        await session.execute(
            select(SlaPolicy)
            .where(
                SlaPolicy.source_channel == source_channel,
                SlaPolicy.matter_type.is_(None),
                SlaPolicy.priority == priority,
            )
            .order_by(SlaPolicy.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def compute_due_at(received_at: dt.datetime, policy: SlaPolicy, holidays: frozenset[dt.date]) -> dt.date:
    return add_business_days(received_at.date(), policy.days, holidays)


def compute_sla_status(
    received_at: dt.datetime,
    due_at: dt.date | None,
    *,
    now: dt.datetime,
    holidays: frozenset[dt.date],
    warn_at: list[int],
) -> str:
    """`warn_at` is a list of business-day counts *before* the due date
    at which Section 7.3's `SLA_APPROACHING` should fire (e.g. `[3, 1]`
    — 3 and 1 business days out). Returns `not_set` when there's no
    policy at all."""
    if due_at is None:
        return "not_set"
    today = now.date()
    if today > due_at:
        return "breached"
    remaining = business_days_between(today, due_at, holidays)
    if warn_at and remaining <= max(warn_at):
        return "approaching"
    return "on_track"


class CaseSlaFacts:
    """Bundled result for a single case, built once per read so
    endpoints don't repeat the policy-lookup + due-date-compute dance."""

    def __init__(self, policy: SlaPolicy | None, due_at: dt.date | None, status: str):
        self.policy = policy
        self.due_at = due_at
        self.status = status


async def sla_facts_for_case(
    session: AsyncSession,
    *,
    source_channel: str,
    matter_type: str,
    priority: str,
    received_at: dt.datetime,
    now: dt.datetime | None = None,
    holidays: frozenset[dt.date] | None = None,
) -> CaseSlaFacts:
    policy = await fetch_policy(session, source_channel=source_channel, matter_type=matter_type, priority=priority)
    if policy is None:
        return CaseSlaFacts(None, None, "not_set")
    resolved_holidays = holidays if holidays is not None else await fetch_holidays(session)
    due_at = compute_due_at(received_at, policy, resolved_holidays)
    status = compute_sla_status(
        received_at, due_at, now=now or dt.datetime.now(dt.UTC), holidays=resolved_holidays, warn_at=policy.warn_at
    )
    return CaseSlaFacts(policy, due_at, status)
