"""Section 7.4/9.7 export rules: formula-injection-safe CSV, watermarked
with who/when/what-filters, hashed so a recipient can verify a copy
hasn't been altered. One place builds every exported CSV so no report
endpoint reinvents (or forgets) these rules.
"""

import csv
import hashlib
import io
import json
from typing import Any

# OWASP CSV-injection guidance: a cell whose first character is one of
# these can be interpreted as a formula by Excel/Sheets/LibreOffice when
# opened — prefixing a single quote neutralizes it while leaving the
# visible value unchanged for a human reader.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


def build_csv_export(
    *,
    columns: list[str],
    rows: list[list[Any]],
    report_id: str,
    generated_by: str,
    generated_at: str,
    filters: dict[str, Any],
) -> bytes:
    """Builds the exact bytes written to the response body: a leading
    watermark comment line, the header row, every data row (each cell
    passed through `safe_cell`), then a trailing hash line. The hash
    covers only the header + data rows (not the watermark line, which
    necessarily varies run to run) so a recipient can re-derive it from
    the visible table and confirm nothing in the data was altered after
    export."""
    data_buf = io.StringIO()
    writer = csv.writer(data_buf)
    writer.writerow([safe_cell(c) for c in columns])
    for row in rows:
        writer.writerow([safe_cell(c) for c in row])
    data_bytes = data_buf.getvalue().encode("utf-8")
    digest = hashlib.sha256(data_bytes).hexdigest()

    watermark = (
        f"# ICM export — TEST DATA, NOT REAL AICTE RECORDS — report={report_id} "
        f"generated_by={generated_by} generated_at={generated_at} "
        f"filters={json.dumps(filters, sort_keys=True, default=str)}\n"
    )
    trailer = f"# sha256={digest}\n"
    return watermark.encode("utf-8") + data_bytes + trailer.encode("utf-8")
