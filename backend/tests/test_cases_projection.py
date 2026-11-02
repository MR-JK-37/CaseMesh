"""Pure unit tests, no DB — the event->projection core is deliberately
separated so the exact logic used live is the same logic
scripts/rebuild_projection.py replays (Section 6.3)."""

import datetime as dt

import pytest

from app.services.cases import compute_projection_updates, format_case_number

NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.UTC)


def test_registered_sets_pending_and_required_fields():
    outcome = compute_projection_updates(
        "pending",
        "registered",
        {
            "matter_type": "ragging",
            "source_channel": "letter",
            "received_at": NOW,
            "assigned_bureau_id": "b1",
        },
        NOW,
    )
    assert outcome.fields["status"] == "pending"
    assert outcome.fields["matter_type"] == "ragging"
    assert outcome.fields["last_action_type"] == "registered"


def test_registered_defaults_priority_and_confidential():
    outcome = compute_projection_updates(
        "pending",
        "registered",
        {"matter_type": "rti", "source_channel": "email", "received_at": NOW},
        NOW,
    )
    assert outcome.fields["priority"] == "standard"
    assert outcome.fields["confidential"] is False


def test_assignment_moves_pending_to_under_process():
    outcome = compute_projection_updates("pending", "assigned", {"officer_id": "u1"}, NOW)
    assert outcome.fields["status"] == "under_process"
    assert outcome.fields["assigned_officer_id"] == "u1"


def test_assignment_does_not_regress_an_escalated_case():
    outcome = compute_projection_updates("escalated", "reassigned", {"officer_id": "u2"}, NOW)
    assert outcome.fields["status"] == "escalated"


def test_remark_moves_pending_to_under_process():
    outcome = compute_projection_updates("pending", "remark_added", {}, NOW)
    assert outcome.fields["status"] == "under_process"


def test_remark_can_update_next_action_and_expected_disposal():
    outcome = compute_projection_updates(
        "under_process",
        "remark_added",
        {"next_action_required": "Inspection report", "expected_disposal_date": dt.date(2026, 12, 1)},
        NOW,
    )
    assert outcome.fields["next_action_required"] == "Inspection report"
    assert outcome.fields["expected_disposal_date"] == dt.date(2026, 12, 1)


def test_remark_without_those_keys_does_not_touch_them():
    outcome = compute_projection_updates("under_process", "remark_added", {}, NOW)
    assert "next_action_required" not in outcome.fields
    assert "expected_disposal_date" not in outcome.fields


def test_transfer_proposed_sets_transferred_status():
    outcome = compute_projection_updates("under_process", "transfer_proposed", {}, NOW)
    assert outcome.fields["status"] == "transferred"


def test_transfer_accepted_moves_bureau_and_clears_officer():
    outcome = compute_projection_updates("transferred", "transfer_accepted", {"to_bureau_id": "b2"}, NOW)
    assert outcome.fields["status"] == "under_process"
    assert outcome.fields["assigned_bureau_id"] == "b2"
    assert outcome.fields["assigned_officer_id"] is None


def test_transfer_rejected_reverts_to_under_process():
    outcome = compute_projection_updates("transferred", "transfer_rejected", {}, NOW)
    assert outcome.fields["status"] == "under_process"


def test_escalation_sets_escalated():
    outcome = compute_projection_updates("under_process", "escalated", {}, NOW)
    assert outcome.fields["status"] == "escalated"


def test_disposal_sets_disposed_and_timestamp():
    outcome = compute_projection_updates("under_process", "disposed", {"disposal_type": "resolved"}, NOW)
    assert outcome.fields["status"] == "disposed"
    assert outcome.fields["disposed_at"] == NOW
    assert outcome.fields["disposal_type"] == "resolved"


def test_reopen_clears_disposed_at_and_returns_to_under_process():
    outcome = compute_projection_updates("disposed", "reopened", {}, NOW)
    assert outcome.fields["status"] == "under_process"
    assert outcome.fields["disposed_at"] is None


def test_unknown_event_type_raises():
    with pytest.raises(ValueError):
        compute_projection_updates("pending", "not_a_real_event", {}, NOW)


def test_case_number_format():
    assert format_case_number(1, 2026) == "ICM-2026-000001"
    assert format_case_number(123456, 2026) == "ICM-2026-123456"
