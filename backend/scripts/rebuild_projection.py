"""Section 6.3: rebuilds the `cases` projection from `case_events` alone
and compares against live state. Reuses `compute_projection_updates`
(app/services/cases.py) — the exact same function the live request path
uses — so this is a real replay-equality check, not an independent
reimplementation that could silently drift.

Usage: python scripts/rebuild_projection.py [--case-id UUID]
Exits non-zero (and prints every mismatch) if any case's live row
disagrees with what replaying its own event log produces — the nightly
drift check Section 6.3/10 asks for. Phase 5: a mismatch also raises a
real `PROJECTION_DRIFT` alert (Section 7.3), deduped per case per run
date so re-running the same day's check doesn't spam duplicates.
"""

import argparse
import asyncio
import datetime as dt
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import Case, CaseEvent
from app.services.alerts import raise_alert
from app.services.cases import compute_projection_updates, format_case_number

PROJECTED_FIELDS = (
    "status",
    "matter_type",
    "source_channel",
    "priority",
    "confidential",
    "received_at",
    "expected_disposal_date",
    "disposed_at",
    "disposal_type",
    "assigned_bureau_id",
    "assigned_officer_id",
    "last_action_type",
    "last_action_at",
    "next_action_required",
)


@dataclass
class Replayed:
    fields: dict[str, Any] = field(default_factory=dict)


def replay(events: list[CaseEvent]) -> Replayed:
    state = Replayed()
    status = "pending"
    for event in events:
        outcome = compute_projection_updates(status, event.event_type, event.payload, event.created_at)
        state.fields.update(outcome.fields)
        status = state.fields.get("status", status)
    return state


def _normalize(value: Any) -> Any:
    """JSONB payloads round-trip UUIDs/dates as strings; live ORM
    columns are typed. Compare on string form so the diff is about real
    mismatches, not Python type noise."""
    if value is None:
        return None
    if isinstance(value, (uuid.UUID, dt.date, dt.datetime)):
        return str(value)
    return value


async def check_case(session, case: Case) -> list[str]:
    events = (
        await session.execute(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.seq))
    ).scalars().all()
    replayed = replay(events)

    mismatches = []
    for f in PROJECTED_FIELDS:
        live = _normalize(getattr(case, f))
        expected = _normalize(replayed.fields.get(f))
        if live != expected:
            mismatches.append(f"{f}: live={live!r} replayed={expected!r}")

    expected_case_number = format_case_number(case.seq, case.received_at.year)
    if case.case_number != expected_case_number:
        mismatches.append(f"case_number: live={case.case_number!r} expected={expected_case_number!r}")

    return mismatches


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", default=None)
    args = parser.parse_args()

    async with SessionLocal() as session, session.begin():
        # 'system' (Section 4.1's machine identity), not 'super_admin':
        # super_admin deliberately has no case-content access by
        # default, which includes case_events — this operational job
        # needs to actually read them to verify integrity. See
        # docs/decision-log.md.
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        query = select(Case)
        if args.case_id:
            query = query.where(Case.id == uuid.UUID(args.case_id))
        cases = (await session.execute(query)).scalars().all()

        total_mismatches = 0
        for case in cases:
            mismatches = await check_case(session, case)
            if mismatches:
                total_mismatches += 1
                print(f"MISMATCH {case.case_number} ({case.id}):")
                for m in mismatches:
                    print(f"  - {m}")
                today = dt.datetime.now(dt.UTC).date().isoformat()
                await raise_alert(
                    session,
                    code="PROJECTION_DRIFT",
                    severity="critical",
                    resource_type="case",
                    resource_id=case.id,
                    message=f"Case {case.case_number}'s projection disagrees with its event log replay.",
                    dedup_key=f"PROJECTION_DRIFT:{case.id}:{today}",
                    channels=["broadcast:all"],
                )

        print(f"Checked {len(cases)} case(s), {total_mismatches} with drift.")
        return 1 if total_mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
