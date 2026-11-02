import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import ImportJob, ImportJobRow, Institution, SourceDocument
from app.services.alerts import raise_alert
from app.services.audit import append_audit_entry
from app.services.reference_import import compute_diff, parse_csv, parse_xlsx

router = APIRouter(prefix="/imports", tags=["imports"])


class ImportRowOut(BaseModel):
    id: str
    row_number: int
    permanent_id: str | None
    action: str
    diff: dict | None
    errors: list[str]


class ImportJobOut(BaseModel):
    id: str
    status: str
    row_count: int
    error_count: int
    source_filename: str
    source_name: str
    rows: list[ImportRowOut]


@router.post("", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def create_import_preview(
    file: UploadFile = File(...),
    source_name: str = Form(...),
    source_url: str | None = Form(None),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 1.2/5: upload a CSV/XLSX, parse it, diff every row against
    any existing institution (matched by permanent_id) — writes nothing
    to `institutions` yet. A human reviews this preview and calls
    POST /imports/{id}/commit to actually apply it (Section 1.4's
    "human-validate before activation")."""
    if not can(principal.role, "institution:import"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Empty file")

    filename = file.filename or "upload"
    if filename.lower().endswith(".xlsx"):
        parsed_rows = parse_xlsx(content)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.lower().endswith(".csv"):
        parsed_rows = parse_csv(content)
        content_type = "text/csv"
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File must be .csv or .xlsx")

    doc = SourceDocument(
        filename=filename,
        content_type=content_type,
        sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by=uuid.UUID(principal.user_id),
        source_name=source_name,
        source_url=source_url,
    )
    session.add(doc)
    await session.flush()

    job = ImportJob(
        source_document_id=doc.id,
        status="previewed",
        created_by=uuid.UUID(principal.user_id),
        row_count=len(parsed_rows),
    )
    session.add(job)
    await session.flush()

    existing_by_pid = {
        inst.permanent_id: inst
        for inst in (await session.execute(select(Institution))).scalars().all()
    }

    error_count = 0
    out_rows: list[ImportRowOut] = []
    for row in parsed_rows:
        if row.errors:
            error_count += 1
            action = "error"
            diff = None
        else:
            existing = existing_by_pid.get(row.permanent_id)
            diff = compute_diff(
                {
                    "name": existing.name,
                    "address": existing.address,
                    "state": existing.state,
                    "district": existing.district,
                    "programmes": existing.programmes,
                    "approved_intake": existing.approved_intake,
                }
                if existing
                else None,
                row.raw,
            )
            if existing is None:
                action = "create"
            elif diff:
                action = "update"
            else:
                action = "unchanged"

        job_row = ImportJobRow(
            import_job_id=job.id,
            row_number=row.row_number,
            raw_data=row.raw,
            parsed_permanent_id=row.permanent_id,
            action=action,
            diff=diff,
            error_message="; ".join(row.errors) if row.errors else None,
        )
        session.add(job_row)
        await session.flush()
        out_rows.append(
            ImportRowOut(
                id=str(job_row.id),
                row_number=row.row_number,
                permanent_id=row.permanent_id,
                action=action,
                diff=diff,
                errors=row.errors,
            )
        )

    job.error_count = error_count
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="import_previewed",
        resource_type="import_job",
        resource_id=str(job.id),
    )

    return ImportJobOut(
        id=str(job.id),
        status=job.status,
        row_count=job.row_count,
        error_count=error_count,
        source_filename=filename,
        source_name=source_name,
        rows=out_rows,
    )


@router.get("/{job_id}", response_model=ImportJobOut)
async def get_import(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "institution:import"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    job = (await session.execute(select(ImportJob).where(ImportJob.id == uuid.UUID(job_id)))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import job not found")
    doc = (
        await session.execute(select(SourceDocument).where(SourceDocument.id == job.source_document_id))
    ).scalar_one()
    rows = (
        await session.execute(
            select(ImportJobRow).where(ImportJobRow.import_job_id == job.id).order_by(ImportJobRow.row_number)
        )
    ).scalars().all()
    return ImportJobOut(
        id=str(job.id),
        status=job.status,
        row_count=job.row_count,
        error_count=job.error_count,
        source_filename=doc.filename,
        source_name=doc.source_name,
        rows=[
            ImportRowOut(
                id=str(r.id),
                row_number=r.row_number,
                permanent_id=r.parsed_permanent_id,
                action=r.action,
                diff=r.diff,
                errors=[r.error_message] if r.error_message else [],
            )
            for r in rows
        ],
    )


class CommitResultOut(BaseModel):
    created: int
    updated: int


@router.post(
    "/{job_id}/commit",
    response_model=CommitResultOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_csrf)],
)
async def commit_import(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Applies every non-error row: creates institutions with
    `status='pending_review'` (new) or updates the diffed fields
    (existing) — these still require a separate `/institutions/{id}/verify`
    before Section 1.4 considers them activated."""
    if not can(principal.role, "institution:import"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    job = (await session.execute(select(ImportJob).where(ImportJob.id == uuid.UUID(job_id)))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import job not found")
    if job.status == "committed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already committed")

    doc = (
        await session.execute(select(SourceDocument).where(SourceDocument.id == job.source_document_id))
    ).scalar_one()
    rows = (
        await session.execute(select(ImportJobRow).where(ImportJobRow.import_job_id == job.id))
    ).scalars().all()
    existing_by_pid = {
        inst.permanent_id: inst
        for inst in (await session.execute(select(Institution))).scalars().all()
    }

    created = updated = 0
    for row in rows:
        if row.action == "error" or not row.parsed_permanent_id:
            continue
        existing = existing_by_pid.get(row.parsed_permanent_id)
        if existing is None:
            inst = Institution(
                permanent_id=row.parsed_permanent_id,
                name=row.raw_data.get("name"),
                address=row.raw_data.get("address") or None,
                state=row.raw_data.get("state") or None,
                district=row.raw_data.get("district") or None,
                programmes=row.raw_data.get("programmes") or None,
                approved_intake=row.raw_data.get("approved_intake") or None,
                status="pending_review",
                data_origin="user_entered",
                source_name=doc.source_name,
                source_url=doc.source_url,
                import_job_id=job.id,
            )
            session.add(inst)
            await session.flush()
            row.institution_id = inst.id
            created += 1
        elif row.action == "update":
            for field in ("name", "address", "state", "district", "programmes", "approved_intake"):
                new_value = row.raw_data.get(field)
                if new_value:
                    setattr(existing, field, new_value)
            existing.import_job_id = job.id
            row.institution_id = existing.id
            updated += 1

    job.status = "committed"
    job.committed_by = uuid.UUID(principal.user_id)
    import datetime as dt

    job.committed_at = dt.datetime.now(dt.UTC)

    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="import_committed",
        resource_type="import_job",
        resource_id=str(job.id),
    )

    # Section 7.3: IMPORT_COMPLETED — one alert per job (dedup by job
    # id, since a job can only be committed once — the 409 above already
    # guards re-commit).
    await raise_alert(
        session,
        code="IMPORT_COMPLETED",
        severity="info",
        resource_type="import_job",
        resource_id=job.id,
        message=f"Import job committed: {created} institution(s) created, {updated} updated.",
        dedup_key=f"IMPORT_COMPLETED:{job.id}",
        channels=["broadcast:all"],
    )

    return {"created": created, "updated": updated}
