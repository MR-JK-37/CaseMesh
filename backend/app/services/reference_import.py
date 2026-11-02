"""Section 5/M2's `AicteReferenceImporter`, pure-function core: parsing
and diffing are separated from the DB/HTTP layer (`routers/imports.py`)
so they're unit-testable without Postgres. CSV/XLSX in, never scraped —
Section 1.2 forbids automating against facilities.aicte-india.org and
Section 0 rule 6 requires asking a human before scraping anything else;
this only ever reads a file a human uploaded.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from app.models import PERMANENT_ID_REGEX

REQUIRED_COLUMNS = ("permanent_id", "name")
OPTIONAL_COLUMNS = (
    "address",
    "state",
    "district",
    "region_name",
    "programmes",
    "approved_intake",
)


@dataclass
class ParsedRow:
    row_number: int
    raw: dict[str, Any]
    errors: list[str] = field(default_factory=list)

    @property
    def permanent_id(self) -> str | None:
        return (self.raw.get("permanent_id") or "").strip() or None


def parse_csv(content: bytes) -> list[ParsedRow]:
    text = content.decode("utf-8-sig")  # -sig: tolerate an Excel-exported BOM
    reader = csv.DictReader(io.StringIO(text))
    return _validate_rows(reader)


def parse_xlsx(content: bytes) -> list[ParsedRow]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    dict_rows = (
        {header[i]: (row[i] if i < len(row) else None) for i in range(len(header))} for row in rows_iter
    )
    return _validate_rows(dict_rows)


def _validate_rows(dict_rows: Any) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    for i, raw in enumerate(dict_rows, start=2):  # row 1 is the header
        normalized = {
            k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k
        }
        errors: list[str] = []
        for col in REQUIRED_COLUMNS:
            if not normalized.get(col):
                errors.append(f"missing required column '{col}'")
        permanent_id = normalized.get("permanent_id")
        if permanent_id and not re.match(PERMANENT_ID_REGEX, str(permanent_id)):
            errors.append(f"permanent_id '{permanent_id}' does not match {PERMANENT_ID_REGEX}")
        approved_intake = normalized.get("approved_intake")
        if approved_intake not in (None, ""):
            try:
                normalized["approved_intake"] = int(approved_intake)
            except (ValueError, TypeError):
                errors.append(f"approved_intake '{approved_intake}' is not an integer")
        rows.append(ParsedRow(row_number=i, raw=normalized, errors=errors))
    return rows


# Fields compared for the diff view / update-vs-unchanged decision.
DIFFABLE_FIELDS = ("name", "address", "state", "district", "programmes", "approved_intake")


def compute_diff(existing: dict[str, Any] | None, parsed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Returns {field: {"old": ..., "new": ...}} for every field whose
    value actually differs. Empty dict means no changes (action should
    be "unchanged"). `existing=None` means every present field is "new"
    (action should be "create")."""
    diff: dict[str, dict[str, Any]] = {}
    for f in DIFFABLE_FIELDS:
        new_value = parsed.get(f) or None
        old_value = (existing or {}).get(f)
        if new_value is not None and new_value != old_value:
            diff[f] = {"old": old_value, "new": new_value}
    return diff
