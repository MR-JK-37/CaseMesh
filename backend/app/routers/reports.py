"""Section 9.7's report catalogue (R11). Every report's numbers are
derived from the exact same `compute_tiles`/`compute_monthly_series`
functions the dashboard uses (`app/services/dashboard.py`) — not a
second, parallel set of queries — specifically so
`tests/test_reports.py`'s "report totals equal dashboard totals" gate
is true by construction, not by coincidence that two independent
implementations happened to agree.
"""

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session
from app.services.csv_export import build_csv_export
from app.services.dashboard import compute_monthly_series, compute_tiles

router = APIRouter(prefix="/reports", tags=["reports"])


async def _bureau_workload(session: AsyncSession, _filters: dict[str, Any]):
    tiles = await compute_tiles(session)
    columns = ["Bureau/Cell", "Open cases", "Overdue (beyond timeline)"]
    rows = [[row["bureau_name"], row["open"], row["overdue"]] for row in tiles["bureau_workload"]]
    return columns, rows


async def _status_summary(session: AsyncSession, _filters: dict[str, Any]):
    tiles = await compute_tiles(session)
    columns = ["Status", "Count"]
    rows = [
        ["Pending", tiles["pending"]],
        ["Under process", tiles["under_process"]],
        ["Escalated", tiles["escalated"]],
        ["Transferred", tiles["transferred"]],
        ["Disposed", tiles["disposed"]],
        ["Total", tiles["total_cases"]],
    ]
    return columns, rows


async def _pending_ageing(session: AsyncSession, _filters: dict[str, Any]):
    tiles = await compute_tiles(session)
    columns = ["Age bucket (business-naive calendar days)", "Open cases"]
    rows = [[bucket, count] for bucket, count in tiles["ageing_buckets"].items()]
    return columns, rows


async def _disposal_rate(session: AsyncSession, _filters: dict[str, Any]):
    series = await compute_monthly_series(session, months=6)
    columns = ["Month", "Received", "Disposed", "Disposal rate (disposed/received)"]
    rows = []
    for point in series:
        rate = f"{point['disposed'] / point['received']:.0%}" if point["received"] else "n/a"
        rows.append([point["month"], point["received"], point["disposed"], rate])
    return columns, rows


REPORT_DEFS: dict[str, dict[str, Any]] = {
    "bureau_workload": {
        "title": "Bureau/Cell-wise workload",
        "description": "Open and overdue case counts per Bureau/Cell, from the same live recomputation as the dashboard's workload tile.",
        "run": _bureau_workload,
    },
    "status_summary": {
        "title": "Status-wise summary",
        "description": "Case counts by status (pending, under process, escalated, transferred, disposed).",
        "run": _status_summary,
    },
    "pending_ageing": {
        "title": "Pending ageing analysis",
        "description": "Open cases bucketed by calendar days since receipt.",
        "run": _pending_ageing,
    },
    "disposal_rate": {
        "title": "Monthly disposal rate",
        "description": "Received vs disposed per month for the last 6 months, with disposal rate.",
        "run": _disposal_rate,
    },
}


@router.get("")
async def list_reports(
    principal: Principal = Depends(get_current_principal),
):
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    return [
        {"id": report_id, "title": d["title"], "description": d["description"]} for report_id, d in REPORT_DEFS.items()
    ]


@router.get("/{report_id}/run")
async def run_report(
    report_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    bureau_id: str | None = None,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    definition = REPORT_DEFS.get(report_id)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown report")

    filters: dict[str, Any] = {}
    if bureau_id:
        filters["bureau_id"] = bureau_id
    columns, rows = await definition["run"](session, filters)
    generated_at = dt.datetime.now(dt.UTC).isoformat()

    if format == "json":
        return {
            "report_id": report_id,
            "title": definition["title"],
            "generated_at": generated_at,
            "filters": filters,
            "columns": columns,
            "rows": rows,
        }

    body = build_csv_export(
        columns=columns,
        rows=rows,
        report_id=report_id,
        generated_by=f"user:{principal.user_id}",
        generated_at=generated_at,
        filters=filters,
    )
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{report_id}.csv"'},
    )
