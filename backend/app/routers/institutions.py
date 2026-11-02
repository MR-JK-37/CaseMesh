import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import Case, CaseInstitutionLink, Institution, InstitutionAlias, User
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/institutions", tags=["institutions"])


class InstitutionOut(BaseModel):
    id: str
    permanent_id: str
    name: str
    address: str | None
    state: str | None
    district: str | None
    programmes: str | None
    approved_intake: int | None
    status: str
    data_origin: str
    source_name: str
    source_url: str | None
    verified_by_email: str | None
    verified_at: str | None
    created_at: str


def _to_out(inst: Institution, verified_by_email: str | None) -> InstitutionOut:
    return InstitutionOut(
        id=str(inst.id),
        permanent_id=inst.permanent_id,
        name=inst.name,
        address=inst.address,
        state=inst.state,
        district=inst.district,
        programmes=inst.programmes,
        approved_intake=inst.approved_intake,
        status=inst.status,
        data_origin=inst.data_origin,
        source_name=inst.source_name,
        source_url=inst.source_url,
        verified_by_email=verified_by_email,
        verified_at=inst.verified_at.isoformat() if inst.verified_at else None,
        created_at=inst.created_at.isoformat(),
    )


@router.get("", response_model=list[InstitutionOut])
async def list_institutions(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 1.2: public reference data, readable by every
    authenticated official (T1-equivalent — this is not case content).
    Shows `pending_review` rows too, with their status visible, rather
    than hiding import results until verified (Section 1.4's honest
    empty/partial-state rule)."""
    if not can(principal.role, "institution:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (await session.execute(select(Institution).order_by(Institution.name))).scalars().all()
    verifier_ids = {r.verified_by for r in rows if r.verified_by}
    verifiers = {}
    if verifier_ids:
        verifiers = {
            u.id: u.email
            for u in (await session.execute(select(User).where(User.id.in_(verifier_ids)))).scalars().all()
        }
    return [_to_out(r, verifiers.get(r.verified_by)) for r in rows]


@router.get("/{institution_id}", response_model=InstitutionOut)
async def get_institution(
    institution_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "institution:read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    inst = (
        await session.execute(select(Institution).where(Institution.id == uuid.UUID(institution_id)))
    ).scalar_one_or_none()
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")
    verifier_email = None
    if inst.verified_by:
        verifier_email = (
            await session.execute(select(User.email).where(User.id == inst.verified_by))
        ).scalar_one_or_none()
    return _to_out(inst, verifier_email)


class CaseHistoryRow(BaseModel):
    id: str
    case_number: str
    matter_type: str
    status: str
    assigned_bureau_id: str | None
    received_at: str


class CaseHistoryOut(BaseModel):
    cases: list[CaseHistoryRow]
    note: str | None


@router.get("/{institution_id}/cases", response_model=CaseHistoryOut)
async def get_institution_case_history(
    institution_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 2.1 R2's consolidated case history, built on top of
    Phase 3's `cases` table — T1 coordination metadata only (case ID,
    matter type, status, handling bureau, date), the same boundary
    `GET /cases` uses: this is exactly R2's "list of every case across
    all bureaus the viewer may see", not case content. Was a hardcoded
    empty stub through Phase 2/3 (Section 0 rule 2 — no fabricated
    placeholder before cases existed); now real."""
    if not can(principal.role, "institution:read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    inst = (
        await session.execute(select(Institution.id).where(Institution.id == uuid.UUID(institution_id)))
    ).scalar_one_or_none()
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")

    rows = (
        await session.execute(
            select(Case)
            .join(CaseInstitutionLink, CaseInstitutionLink.case_id == Case.id)
            .where(CaseInstitutionLink.institution_id == uuid.UUID(institution_id))
            .order_by(Case.received_at.desc())
        )
    ).scalars().all()
    cases = [
        CaseHistoryRow(
            id=str(c.id),
            case_number=c.case_number,
            matter_type=c.matter_type,
            status=c.status,
            assigned_bureau_id=str(c.assigned_bureau_id) if c.assigned_bureau_id else None,
            received_at=c.received_at.isoformat(),
        )
        for c in rows
    ]
    return CaseHistoryOut(cases=cases, note=None if cases else "No cases have been registered for this institution yet.")


@router.post(
    "/{institution_id}/verify", response_model=InstitutionOut, dependencies=[Depends(require_csrf)]
)
async def verify_institution(
    institution_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "institution:verify"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    inst = (
        await session.execute(select(Institution).where(Institution.id == uuid.UUID(institution_id)))
    ).scalar_one_or_none()
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")

    inst.status = "active"
    inst.verified_by = uuid.UUID(principal.user_id)
    inst.verified_at = dt.datetime.now(dt.UTC)

    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="institution_verified",
        resource_type="institution",
        resource_id=institution_id,
    )
    await session.flush()
    verifier_email = (
        await session.execute(select(User.email).where(User.id == uuid.UUID(principal.user_id)))
    ).scalar_one()
    return _to_out(inst, verifier_email)


class AliasOut(BaseModel):
    id: str
    alias_name: str


@router.get("/{institution_id}/aliases", response_model=list[AliasOut])
async def list_aliases(
    institution_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "institution:read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (
        await session.execute(
            select(InstitutionAlias).where(InstitutionAlias.institution_id == uuid.UUID(institution_id))
        )
    ).scalars().all()
    return [AliasOut(id=str(r.id), alias_name=r.alias_name) for r in rows]


class AddAliasRequest(BaseModel):
    alias_name: str


@router.post(
    "/{institution_id}/aliases",
    response_model=AliasOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def add_alias(
    institution_id: str,
    body: AddAliasRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Storage only this phase — Section 8.1's resolver that actually
    consumes aliases for matching is Phase 4 (docs/limitations.md)."""
    if not can(principal.role, "institution:alias_manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    alias = InstitutionAlias(
        institution_id=uuid.UUID(institution_id),
        alias_name=body.alias_name,
        added_by=uuid.UUID(principal.user_id),
    )
    session.add(alias)
    await session.flush()
    return AliasOut(id=str(alias.id), alias_name=alias.alias_name)
