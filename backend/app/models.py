"""Section 6.1 core entities — Phase 1 (identity/RBAC/RLS/audit), Phase 2
(institution reference data), Phase 3 (case lifecycle) slices."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base

# Section 4.1's 10 roles, exactly as named in the master prompt so they
# line up 1:1 with docs/decision-log.md and authz/policy.py.
ROLES = (
    "super_admin",
    "competent_authority",
    "senior_management",
    "bureau_head",
    "case_officer",
    "regional_officer",
    "nodal_pg_officer",
    "registry_operator",
    "auditor",
    "system",
)

# Section 4.1: "TOTP is mandatory for roles 1 to 4, 7 and 9" —
# super_admin, competent_authority, senior_management, bureau_head,
# nodal_pg_officer, auditor.
TOTP_REQUIRED_ROLES = frozenset(
    {"super_admin", "competent_authority", "senior_management", "bureau_head", "nodal_pg_officer", "auditor"}
)


def is_totp_required_for_role(role: str) -> bool:
    """Return True if TOTP MFA is mandatory for the given role."""
    return role in TOTP_REQUIRED_ROLES


def is_valid_role(role: str) -> bool:
    """Validate whether a role string is one of the recognized system roles."""
    return role in ROLES


def get_all_roles() -> list[str]:
    """Return a list of all recognized system roles."""
    return list(ROLES)


def get_totp_required_roles() -> list[str]:
    """Return a list of roles that strictly require TOTP MFA."""
    return list(TOTP_REQUIRED_ROLES)


CASE_STATUSES = (
    "pending",
    "under_process",
    "transferred",
    "escalated",
    "disposed",
    "withdrawn",
)
TERMINAL_CASE_STATUSES = frozenset({"disposed", "withdrawn"})


def is_terminal_status(status: str) -> bool:
    """Return True if case status represents a completed/terminal lifecycle state."""
    return status in TERMINAL_CASE_STATUSES


def is_active_case_status(status: str) -> bool:
    """Return True if case status represents an ongoing active workflow."""
    return status in CASE_STATUSES and status not in TERMINAL_CASE_STATUSES



class Bureau(Base):
    """Section 1.2 "Organisation master": Bureau or Cell. Admin-editable
    and versioned in spirit (full version history is a Phase 2+ add —
    see docs/limitations.md); seeded from official pages with
    provenance, never treated as a single source of truth given
    Section 15's documented disagreement between sources."""

    __tablename__ = "bureaus"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # 'bureau' | 'cell'
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="user_entered")
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegionalOffice(Base):
    __tablename__ = "regional_offices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="user_entered")
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Section 4.1 lockout: 5 failures / 10 minutes, configurable later
    # (Phase 2 admin console) — hardcoded threshold for now, see
    # core/config.py.
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    assignments: Mapped[list["UserAssignment"]] = relationship(back_populates="user")


class UserAssignment(Base):
    """Section 4.1 `user_assignments`: a user to a Bureau and/or Region
    with a role context. A user may hold more than one assignment (e.g.
    case_officer in RB *and* PGRC is unusual but not forbidden by the
    problem statement, so this is many-to-many, not a single FK on
    `users`)."""

    __tablename__ = "user_assignments"
    __table_args__ = (UniqueConstraint("user_id", "bureau_id", "region_id", name="uq_user_assignment"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bureau_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bureaus.id", ondelete="CASCADE"))
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regional_offices.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="assignments")


class RefreshTokenFamily(Base):
    """Section 4.1/7.4: 7-day rotating refresh token with family
    revocation. `current_version` increments on every successful
    refresh; a refresh token presenting a stale version means reuse of
    an already-rotated-away token, which revokes the whole family."""

    __tablename__ = "refresh_token_families"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    device_label: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLogEntry(Base):
    """Section 7.4/M14: hash-chained, append-only. `icm_app` is never
    granted UPDATE/DELETE on this table (infra/initdb + the Phase 1
    migration's GRANTs) — a trigger additionally rejects both at the DB
    level so the guarantee doesn't depend solely on the app never doing
    it (Section 6.3's "no code path" discipline applied to audit rows
    too)."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Monotonic ordering key, separate from created_at: Postgres's now()
    # returns the same value for every statement in one transaction, so
    # multiple entries appended together (a real case — e.g. a case
    # action that writes several audit rows atomically, Section 6.3)
    # would tie on created_at and sort unstably, silently breaking the
    # hash chain's "previous row" lookup. A BIGSERIAL is allocated at
    # INSERT time regardless of transaction, so it's always strictly
    # ordered (found via a real failing test, not anticipated in
    # advance — see docs/decision-log.md).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False, unique=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100))
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginAttempt(Base):
    """Rate-limit/lockout audit trail, separate from AuditLogEntry
    because this is high-volume and queried differently (by email+time
    window), not part of the tamper-evident chain."""

    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100))
    ip_prefix: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Phase 2: institution reference data + import pipeline (M2, Section
# 1.2/1.3). Every non-user-typed row carries the provenance fields
# Section 1.3 requires (data_origin, source_name, source_url,
# retrieved_at via created_at, source_checksum via the owning
# import_job's source_document, verified_by/verified_at).

PERMANENT_ID_REGEX = r"^1-\d{6,12}$"  # Section 15: configurable, UNVERIFIED exact format


class SourceDocument(Base):
    """Section 6.1: the uploaded file an import job was parsed from.
    `sha256` is the provenance `source_checksum` Section 1.3 requires."""

    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportJob(Base):
    """Section 5/M2: one CSV/XLSX upload. `status` moves
    previewed -> committed (or stays previewed/discarded) — rows are
    never written to `institutions` until a human commits, per Section
    1.4's "human-validate before activation"."""

    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="previewed")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportJobRow(Base):
    """One parsed CSV/XLSX row with its computed diff against any
    existing institution (matched by permanent_id) — this is what the
    review UI's diff view (Phase 2 gate) actually shows."""

    __tablename__ = "import_job_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parsed_permanent_id: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # create|update|unchanged|error
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(String(500))
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id"))


class Institution(Base):
    """Section 6.1/M2. `status` is `pending_review` until a human
    verifies it (Section 1.4), separate from whether it was just
    created or updated by an import."""

    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    permanent_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    state: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regional_offices.id"))
    programmes: Mapped[str | None] = mapped_column(String(500))
    approved_intake: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_review")

    data_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_jobs.id"))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InstitutionAlias(Base):
    """Section 8.1's institution-resolution matching will consume these
    (Phase 4) — created here because Section 5/M2 asks for "alias
    management" as part of the registry itself, not the overlap engine.
    No matching logic reads this table yet; it is simply storage plus a
    minimal add/list endpoint this phase (see docs/limitations.md)."""

    __tablename__ = "institution_aliases"
    __table_args__ = (UniqueConstraint("institution_id", "alias_name", name="uq_institution_alias"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    alias_name: Mapped[str] = mapped_column(String(300), nullable=False)
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Phase 3: case lifecycle (M3/M4, Section 6.2/6.3). `cases` is a
# deterministic projection of `case_events` — Section 6.3's "no code
# path updates cases.status directly" — rebuilt by
# scripts/rebuild_projection.py and checked against live state by the
# Phase 3 gate's "projection replay equality" test.

# Section 6.1: PGRC's own stated scope, seeded as "matter type" exactly —
# sub-category refinement is an admin-console feature not built this
# phase (Section 6.1, docs/limitations.md).
MATTER_TYPES = (
    "student_faculty_stakeholder_complaint",
    "cpgrams_grievance",
    "ragging",
    "norm_violation",
    "vip_ministry_reference",
    "court_case",
    "parliament_question",
    "rti",
    "miscellaneous",
)


def is_valid_matter_type(matter_type: str) -> bool:
    """Validate whether a matter type is in the canonical PGRC matter types list."""
    return matter_type in MATTER_TYPES


def get_all_matter_types() -> list[str]:
    """Return all canonical PGRC matter types."""
    return list(MATTER_TYPES)


CASE_STATUSES = ("pending", "under_process", "transferred", "escalated", "disposed")

# Section 4.3/6.3's full event vocabulary — Phase 3 implements this
# subset; others (link/unlink, propose-disposal as distinct from
# approve/dispose) are noted in docs/limitations.md.
EVENT_TYPES = (
    "registered",
    "assigned",
    "reassigned",
    "remark_added",
    "transfer_proposed",
    "transfer_accepted",
    "transfer_rejected",
    "escalated",
    "disposed",
    "reopened",
)


class Case(Base):
    """The projection. Every column here is Section 4.3's T1
    "coordination metadata" — no free-text content lives here by
    design, so `cases` can be broadly readable (every authenticated
    official) without a T1/T2 leak; content (remarks) lives in
    `case_events`, which has its own, narrower RLS policy."""

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False, unique=True)
    case_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    matter_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_channel: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    external_refs: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_disposal_date: Mapped[date | None] = mapped_column(Date)
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposal_type: Mapped[str | None] = mapped_column(String(50))

    assigned_bureau_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bureaus.id"))
    assigned_officer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    last_action_type: Mapped[str] = mapped_column(String(30), nullable=False, default="registered")
    last_action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    next_action_required: Mapped[str | None] = mapped_column(String(300))

    registered_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CaseInstitutionLink(Base):
    """Section 5/M3: "multi-institution cases" — a case names one or
    more institutions."""

    __tablename__ = "case_institution_links"
    __table_args__ = (UniqueConstraint("case_id", "institution_id", name="uq_case_institution"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )


class CaseEvent(Base):
    """Section 6.3: append-only (no UPDATE/DELETE grant + a trigger, same
    discipline as `audit_log`). This is where T2 case *content* actually
    lives (`remark`) — RLS here is the real T1/T2 boundary, not `cases`.
    """

    __tablename__ = "case_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False, unique=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    remark: Mapped[str | None] = mapped_column(String(4000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseTransfer(Base):
    """Section 4/M4: propose/accept/reject, a first-class view, not just
    an event payload — so "transfers awaiting acceptance" (Section 9.6
    tile) can be queried directly once that tile is built (Phase 6)."""

    __tablename__ = "case_transfers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    from_bureau_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bureaus.id"), nullable=False)
    to_bureau_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bureaus.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    reason: Mapped[str | None] = mapped_column(String(1000))
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Phase 4: overlap detection + coordination (Section 8). Mirrors the
# T1/T2 split from Phase 3: `overlap_groups`/`overlap_candidates` carry
# only structured, non-sensitive fields (a score, a level, a list of
# short machine-generated reason strings — never raw complaint text),
# so they can be broadly visible like `cases` itself (no RLS) — that is
# the entire point of Section 4.3's "let bureaus see who else is
# handling an institution without exposing complaint content".
# `coordination_messages`/`coordination_decisions` carry real officer
# narrative and get the same bureau-restricted RLS as `case_events`.

OVERLAP_LEVELS = ("info", "potential", "high")
OVERLAP_CANDIDATE_STATUSES = ("pending", "confirmed", "dismissed")
COORDINATION_DECISION_TYPES = ("proceed_in_parallel", "consolidate", "hold")


class OverlapGroup(Base):
    """Section 8.5: "one overlap_group per institution with member
    cases" — a container so the queue shows the institution-level
    picture, not N pairs. Recomputed (never deleted) whenever a new
    candidate pair for the institution appears."""

    __tablename__ = "overlap_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OverlapCandidate(Base):
    """One scored pair within a group — `rules.overlap.score_pair`'s
    output, persisted. `reasons`/`signals` are JSONB but are always
    built from the fixed, structured vocabulary in `rules/rules/
    overlap.py` (never free text pulled from a case) — see that
    module's docstring for why "same complainant"/"same documents"
    signals are absent rather than faked."""

    __tablename__ = "overlap_candidates"
    __table_args__ = (UniqueConstraint("case_a_id", "case_b_id", name="uq_overlap_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("overlap_groups.id", ondelete="CASCADE"), nullable=False)
    case_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    case_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)

    score: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    config_version: Mapped[str] = mapped_column(String(30), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    relationship_type: Mapped[str | None] = mapped_column(String(50))
    dismiss_reason: Mapped[str | None] = mapped_column(String(500))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CoordinationThread(Base):
    """Section 8.5's "Start coordination" action, scoped to one
    candidate pair (a deliberate simplification of "one overlap_group
    with member cases" for *actions* — see docs/decision-log.md Phase 4
    entry: grouping-for-display stays institution-level, but an officer
    coordinates about a specific flagged pair, which keeps the RLS
    shape identical to `case_events`'s proven two-case-union pattern).
    Thread *metadata* (lead bureau, status) is T1-safe and unrestricted;
    its messages are not."""

    __tablename__ = "coordination_threads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("overlap_candidates.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    lead_bureau_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bureaus.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")


class CoordinationMessage(Base):
    """T2-equivalent content — RLS-restricted the same way as
    `case_events`: the two member cases' handling bureaus, plus
    competent_authority/system/self-authored."""

    __tablename__ = "coordination_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coordination_threads.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    author_role: Mapped[str] = mapped_column(String(30), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CoordinationDecision(Base):
    """Section 8.5/R12: "proceed in parallel needs a reason" — this
    phase requires a reason for every decision type, not just that one,
    since "consolidate"/"hold" deserve the same accountability and a
    uniform NOT NULL is simpler and stricter than a conditional check."""

    __tablename__ = "coordination_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coordination_threads.id", ondelete="CASCADE"), nullable=False
    )
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    consolidate_bureau_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bureaus.id"))
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Phase 5: SLA, alerts, real-time fabric (Section 6.4/7). `holidays`
# and `sla_policies` are reference/config data (like `bureaus`) —
# broadly readable, admin-editable, no RLS. `alerts` carries only
# structured, non-sensitive fields (same discipline as Phase 4's
# `overlap_candidates`: a code, a resource pointer, a short machine-
# generated message, never raw case content), so it is also broadly
# listable — Section 7.3 explicitly routes some alerts (e.g.
# `SLA_POLICY_MISSING`) to `super_admin`, who has no case-content
# access by design, so an alerts table restricted like `case_events`
# would be self-defeating. `outbox_events` is the transactional outbox
# (Section 6.4): one row per real-time-worthy state change, in the same
# transaction as the change itself.


class Holiday(Base):
    """Section 7.1/3's holiday calendar. Seeded from the `holidays`
    Python package (India national holidays) by
    `scripts/seed_holidays.py`; `super_admin` can add AICTE-specific
    closures with their own `source_name` (Section 3's `HolidayCalendar`
    adapter)."""

    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("holiday_date", "name", name="uq_holiday_date_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regional_offices.id"))
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SlaPolicy(Base):
    """Section 7.2: keyed by (source_channel, matter_type, priority) —
    `matter_type=NULL` means "applies to every matter type for this
    source+priority", the only shape Section 7.2's verified CPGRAMS
    numbers actually specify. Versioned: a policy is never edited in
    place, a new row with a higher `version` supersedes it, so a case's
    due date computed under an old policy stays explainable."""

    __tablename__ = "sla_policies"
    __table_args__ = (
        UniqueConstraint("source_channel", "matter_type", "priority", "version", name="uq_sla_policy_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_channel: Mapped[str] = mapped_column(String(30), nullable=False)
    matter_type: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    warn_at: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    escalate_after: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


ALERT_CODES = (
    "OVERLAP_DETECTED",
    "OVERLAP_HIGH_CONFIDENCE",
    "INSTITUTION_UNRESOLVED",
    "SLA_POLICY_MISSING",
    "SLA_APPROACHING",
    "SLA_BREACHED",
    "PENDING_REMINDER",
    "CASE_STALE",
    "TRANSFER_UNACCEPTED",
    "ESCALATION_RAISED",
    "IMPORT_COMPLETED",
    "PROJECTION_DRIFT",
    "COUNTER_DRIFT",
)
ALERT_SEVERITIES = ("info", "warning", "critical")


class Alert(Base):
    """Section 7.3. `dedup_key` is what makes "each fires once per
    threshold" real rather than aspirational: `raise_alert()`
    (app/services/alerts.py) only inserts a row when no existing alert
    shares this key, so re-scanning the same case for the same breach
    never duplicates. Acknowledging doesn't delete the row (audit
    trail); `acked_at` is simply set."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    dedup_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEvent(Base):
    """Section 6.4's transactional outbox: written in the same
    transaction as the state change it describes
    (`app/services/realtime.py#publish`), relayed to Valkey Streams by
    `scripts/run_relay.py`, a standalone polling process run alongside
    the API — not a separately-deployed ARQ worker (Section 10's worker
    infra is still unbuilt, see docs/limitations.md), and deliberately
    not an in-process FastAPI background task either (that was tried
    first and caused a real test-suite hang — see docs/decision-log.md).
    `payload` carries T1 data only (Section 6.4: "clients fetch T2 over
    REST with their own authorisation")."""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False, unique=True)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    relayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SavedView(Base):
    """Section 9.7's "saved views" on the cases table: a named, re-runnable
    filter set (R9). Personal to the user who saved it (`owner_id`) — no
    sharing mechanism yet (see docs/limitations.md); `filters` stores
    exactly the same query-param shape `GET /cases` accepts, so applying
    a saved view is just replaying those params, never a second filter
    language to keep in sync."""

    __tablename__ = "saved_views"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
