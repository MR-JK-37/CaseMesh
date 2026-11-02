"""Section 8.5: "scripts/eval_overlap.py computes precision/recall on
officer-labelled pairs and writes docs/overlap-eval.md. Until labels
exist, the UI shows 'confidence: uncalibrated'."

A labelled pair is any `OverlapCandidate` an officer has acted on:
`confirmed` (Section 8.5's "Confirm and link") is a positive label,
`dismissed` ("Dismiss (reason required, feeds tuning)") is a negative
one. "Flagged" means the computed `level` is `potential` or `high` (the
same cutoff the UI uses to show the banner at all — `info`-level pairs
are same-institution matches too weak to surface as "coordination
required"). Section 0 rule 2 forbids inventing an accuracy number, so
with zero labelled pairs this writes "uncalibrated", never a guessed
percentage.

Usage: python scripts/eval_overlap.py
"""

import asyncio
import datetime as dt
from pathlib import Path

from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import OverlapCandidate

# backend/scripts/eval_overlap.py -> repo root -> docs/, so this writes
# the same place regardless of the caller's current directory.
OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "overlap-eval.md"
FLAGGED_LEVELS = ("potential", "high")


def _render_uncalibrated() -> str:
    return (
        "# Overlap detection evaluation\n\n"
        f"_Last run: {dt.datetime.now(dt.UTC).isoformat()}_\n\n"
        "**confidence: uncalibrated**\n\n"
        "No officer has confirmed or dismissed any overlap candidate yet "
        "(Section 8.5's labelling source). No accuracy, precision, or "
        "recall number is shown — Section 0 rule 2 forbids inventing one. "
        "This file will compute real precision/recall once real "
        "confirm/dismiss decisions exist.\n"
    )


def _render_report(
    total_labelled: int, tp: int, fp: int, fn: int, tn: int, precision: float | None, recall: float | None
) -> str:
    def pct(x: float | None) -> str:
        return f"{x * 100:.1f}%" if x is not None else "n/a (denominator is zero)"

    caveat = ""
    if total_labelled < 30:
        caveat = (
            f"\n**Small sample warning:** only {total_labelled} labelled pair(s) exist. "
            "These numbers will be noisy until officers have labelled substantially more "
            "pairs through real use — treat as directional, not final.\n"
        )

    return (
        "# Overlap detection evaluation\n\n"
        f"_Last run: {dt.datetime.now(dt.UTC).isoformat()}_\n\n"
        f"Labelled pairs: {total_labelled} (confirmed = positive, dismissed = negative). "
        f"\"Flagged\" = computed level in {FLAGGED_LEVELS}.\n\n"
        "| | Flagged (potential/high) | Not flagged (info) |\n"
        "|---|---|---|\n"
        f"| **Confirmed (positive)** | TP = {tp} | FN = {fn} |\n"
        f"| **Dismissed (negative)** | FP = {fp} | TN = {tn} |\n\n"
        f"**Precision:** {pct(precision)}\n\n"
        f"**Recall:** {pct(recall)}\n"
        f"{caveat}"
    )


async def build_report() -> tuple[str, int]:
    async with SessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        rows = (await session.execute(select(OverlapCandidate))).scalars().all()

    labelled = [r for r in rows if r.status in ("confirmed", "dismissed")]

    if not labelled:
        return _render_uncalibrated(), 0

    tp = sum(1 for r in labelled if r.status == "confirmed" and r.level in FLAGGED_LEVELS)
    fn = sum(1 for r in labelled if r.status == "confirmed" and r.level not in FLAGGED_LEVELS)
    fp = sum(1 for r in labelled if r.status == "dismissed" and r.level in FLAGGED_LEVELS)
    tn = sum(1 for r in labelled if r.status == "dismissed" and r.level not in FLAGGED_LEVELS)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return _render_report(len(labelled), tp, fp, fn, tn, precision, recall), len(labelled)


if __name__ == "__main__":
    report_text, labelled_count = asyncio.run(build_report())
    OUTPUT_PATH.write_text(report_text)
    print(f"Wrote {OUTPUT_PATH} ({labelled_count} labelled pair(s))")
