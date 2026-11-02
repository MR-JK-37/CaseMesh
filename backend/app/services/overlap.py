"""Phase 4 / Section 8: DB-aware orchestration around the pure
`rules.overlap` module. Stage 1 (candidate fetch) and the event-driven
trigger (Section 8.4) live here; Stage 2 (scoring) is entirely
`rules.overlap.score_pair`, imported and called, never reimplemented —
`tests/test_overlap_api.py` only checks that this module wires real
rows into that function correctly, `rules/tests/test_overlap.py` checks
the scoring logic itself.
"""

import datetime as dt
import uuid
from contextlib import asynccontextmanager

from rules.overlap import CaseFacts, score_pair
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, CaseEvent, CaseInstitutionLink, OverlapCandidate, OverlapGroup
from app.services.alerts import raise_alert

WINDOW_DAYS = 90  # Section 8.2's W: open cases + disposed within W days


@asynccontextmanager
async def _as_system_role(session: AsyncSession, restore_role: str):
    """Temporarily elevates the already-open transaction to Section
    4.1's `system` identity so this function can read every bureau's
    `case_events` content (needed for the text-similarity signal) even
    though the caller's real principal cannot read across bureaus.
    Scoped narrowly: only queries issued inside this block run as
    `system`; the role is always restored on the way out, even on
    error, so the rest of the request keeps the caller's real RLS
    context."""
    await session.execute(text("SELECT set_config('app.role', 'system', true)"))
    try:
        yield
    finally:
        await session.execute(text("SELECT set_config('app.role', :v, true)"), {"v": restore_role})


async def _registered_description(session: AsyncSession, case_id: uuid.UUID) -> str | None:
    """The free-text `description` an officer optionally typed at
    registration time lives in the `registered` event's payload (T2
    content, Section 4.3) — never in `cases` itself, which must stay
    free of narrative text so it can be broadly readable (see
    `Case`'s docstring in app/models.py)."""
    row = (
        await session.execute(
            select(CaseEvent.payload)
            .where(CaseEvent.case_id == case_id, CaseEvent.event_type == "registered")
            .order_by(CaseEvent.seq)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row.get("description") if row else None


async def recompute_overlap_for_institution(
    session: AsyncSession, institution_id: uuid.UUID, *, actor_role: str
) -> None:
    """Section 8.2/8.4: refetches every open-or-recently-disposed case on
    this institution and rescores every pair. Deliberately O(n^2) in the
    number of cases *on one institution* (Section 8.2: "the cost per
    event is bounded by the number of cases on one institution", not the
    whole system).

    Called synchronously, inline, in the same request/transaction that
    just wrote a case event (`app/routers/cases.py#_append_event`) —
    there is no async job worker in this codebase (Section 10's ARQ
    workers are unbuilt, see docs/limitations.md), so "event-driven"
    here means "recomputed before the HTTP response is sent", not
    dispatched to a queue. An honest latency/throughput trade-off, not
    hidden behind a TODO: every case event pays the cost of rescoring
    its institution's other cases, synchronously.

    An officer's prior decision on a pair (confirmed/dismissed,
    relationship_type, dismiss_reason) is sticky across a rescore — a
    change in score/level never silently reopens or relabels something
    already decided; only the score/level/reasons/signals themselves
    refresh.
    """
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=WINDOW_DAYS)
    rows = (
        await session.execute(
            select(Case)
            .join(CaseInstitutionLink, CaseInstitutionLink.case_id == Case.id)
            .where(CaseInstitutionLink.institution_id == institution_id)
            .where((Case.status != "disposed") | (Case.disposed_at >= cutoff))
        )
    ).scalars().all()
    if len(rows) < 2:
        return
    by_id = {c.id: c for c in rows}

    async with _as_system_role(session, actor_role):
        descriptions = {c.id: await _registered_description(session, c.id) for c in rows}

    group = (
        await session.execute(select(OverlapGroup).where(OverlapGroup.institution_id == institution_id))
    ).scalar_one_or_none()
    if group is None:
        group = OverlapGroup(institution_id=institution_id)
        session.add(group)
        await session.flush()

    existing = {
        (row.case_a_id, row.case_b_id): row
        for row in (
            await session.execute(select(OverlapCandidate).where(OverlapCandidate.group_id == group.id))
        ).scalars().all()
    }

    def facts(case: Case) -> CaseFacts:
        return CaseFacts(
            case_id=str(case.id),
            bureau_id=str(case.assigned_bureau_id) if case.assigned_bureau_id else None,
            matter_type=case.matter_type,
            external_refs=tuple(case.external_refs),
            description=descriptions.get(case.id),
            received_at=case.received_at,
        )

    ids = list(by_id)
    touched: list[tuple[OverlapCandidate, str]] = []
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1 :]:
            key = tuple(sorted((id_a, id_b), key=str))
            result = score_pair(facts(by_id[key[0]]), facts(by_id[key[1]]))
            row = existing.get(key)
            if row is not None:
                row.score = result.score
                row.level = result.level
                row.reasons = [{"code": r.code, "text": r.text} for r in result.reasons]
                row.signals = result.signals
                row.config_version = result.config_version
                row.computed_at = dt.datetime.now(dt.UTC)
            else:
                row = OverlapCandidate(
                    group_id=group.id,
                    case_a_id=key[0],
                    case_b_id=key[1],
                    score=result.score,
                    level=result.level,
                    reasons=[{"code": r.code, "text": r.text} for r in result.reasons],
                    signals=result.signals,
                    config_version=result.config_version,
                )
                session.add(row)
            if result.level in ("potential", "high"):
                touched.append((row, result.level))
    await session.flush()

    # Section 7.3: OVERLAP_DETECTED / OVERLAP_HIGH_CONFIDENCE — deduped
    # per (pair, level), so re-scoring the same pair at the same level
    # never re-fires, but a pair crossing from `potential` to `high`
    # raises the stronger alert too (Section 8.5's banner already shows
    # the current state live; the alert catalogue is specifically about
    # *threshold crossings*).
    for row, level in touched:
        case_a, case_b = by_id[row.case_a_id], by_id[row.case_b_id]
        channels = [
            f"bureau:{b}" for b in {case_a.assigned_bureau_id, case_b.assigned_bureau_id} if b
        ] + ["broadcast:all"]
        code = "OVERLAP_HIGH_CONFIDENCE" if level == "high" else "OVERLAP_DETECTED"
        await raise_alert(
            session,
            code=code,
            severity="critical" if level == "high" else "info",
            resource_type="overlap_candidate",
            resource_id=row.id,
            message=f"{case_a.case_number} and {case_b.case_number} may need coordination ({level}, {row.score}/100).",
            dedup_key=f"{code}:{row.id}",
            channels=channels,
        )
