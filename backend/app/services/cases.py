"""Section 6.3: the pure projection-update core. Deliberately separated
from the DB/HTTP layer so the exact same logic drives both the live
request path (`routers/cases.py`) and `scripts/rebuild_projection.py` —
the Phase 3 gate's "projection replay equality" test only means
something if there is exactly one implementation of "what does this
event do to the projection", not two that can drift apart.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventOutcome:
    """What one event does to the `cases` projection — a partial update,
    never a direct status assignment from outside this module (Section
    6.3's "no code path updates cases.status directly")."""

    fields: dict[str, Any]


def compute_projection_updates(
    current_status: str, event_type: str, payload: dict[str, Any], event_time: dt.datetime
) -> EventOutcome:
    """Given the case's status *before* this event and the event itself,
    returns the fields that change. Pure: no DB, no I/O, no randomness
    — safe to call identically from a live request and from a full
    event-log replay."""

    base = {"last_action_type": event_type, "last_action_at": event_time}

    if event_type == "registered":
        return EventOutcome(
            {
                **base,
                "status": "pending",
                "matter_type": payload["matter_type"],
                "source_channel": payload["source_channel"],
                "priority": payload.get("priority", "standard"),
                "confidential": payload.get("confidential", False),
                "received_at": payload["received_at"],
                "assigned_bureau_id": payload.get("assigned_bureau_id"),
                "assigned_officer_id": payload.get("assigned_officer_id"),
                "expected_disposal_date": payload.get("expected_disposal_date"),
                "next_action_required": payload.get("next_action_required"),
            }
        )

    if event_type in ("assigned", "reassigned"):
        next_status = "under_process" if current_status == "pending" else current_status
        return EventOutcome(
            {
                **base,
                "status": next_status,
                "assigned_officer_id": payload["officer_id"],
            }
        )

    if event_type == "remark_added":
        next_status = "under_process" if current_status == "pending" else current_status
        updates = {**base, "status": next_status}
        if "next_action_required" in payload:
            updates["next_action_required"] = payload["next_action_required"]
        if "expected_disposal_date" in payload:
            updates["expected_disposal_date"] = payload["expected_disposal_date"]
        return EventOutcome(updates)

    if event_type == "transfer_proposed":
        return EventOutcome({**base, "status": "transferred"})

    if event_type == "transfer_accepted":
        return EventOutcome(
            {
                **base,
                "status": "under_process",
                "assigned_bureau_id": payload["to_bureau_id"],
                "assigned_officer_id": None,
            }
        )

    if event_type == "transfer_rejected":
        return EventOutcome({**base, "status": "under_process"})

    if event_type == "escalated":
        return EventOutcome({**base, "status": "escalated"})

    if event_type == "disposed":
        return EventOutcome(
            {**base, "status": "disposed", "disposed_at": event_time, "disposal_type": payload.get("disposal_type")}
        )

    if event_type == "reopened":
        return EventOutcome({**base, "status": "under_process", "disposed_at": None})

    raise ValueError(f"Unknown event_type: {event_type}")


CASE_NUMBER_PREFIX = "ICM"


def format_case_number(seq: int, year: int) -> str:
    """Section 6.2: `ICM-<YYYY>-<6-digit sequence>`. The sequence itself
    (gap-free not required, uniqueness is) comes from the DB Identity
    column on `cases.seq`; this just formats it."""
    return f"{CASE_NUMBER_PREFIX}-{year}-{seq:06d}"
