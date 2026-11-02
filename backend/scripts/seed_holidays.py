"""Section 7.1/3: seeds `holidays` from the Python `holidays` package's
India national calendar (Section 15: `holidays==0.107`, pinned and
verified). Idempotent — the `(holiday_date, name)` unique constraint
means re-running this for a year already seeded is a safe no-op per
row, not a duplicate-insert error, because every row is inserted with
`ON CONFLICT DO NOTHING` semantics via a pre-check.

This seeds *national* holidays only. AICTE-specific closures (Section
3's `HolidayCalendar` adapter: "super_admin can add AICTE-specific
closures with a source note") have no admin-console UI yet — see
docs/limitations.md — so for now they'd need a direct DB insert with an
honest `source_name` citing where the closure date came from.

Usage: python scripts/seed_holidays.py [--year YYYY ...]
Defaults to the current year and the next year (so SLA due-date maths
near a year boundary never silently falls back to "no holiday data").
"""

import argparse
import asyncio
import datetime as dt

import holidays as holidays_pkg
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Holiday

SOURCE_NAME = f"Python 'holidays' package (India national calendar), version {holidays_pkg.__version__}"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, action="append", default=None)
    args = parser.parse_args()
    years = args.year or [dt.date.today().year, dt.date.today().year + 1]

    india_holidays = holidays_pkg.country_holidays("IN", years=years)

    async with SessionLocal() as session, session.begin():
        existing = {
            (row.holiday_date, row.name)
            for row in (await session.execute(select(Holiday.holiday_date, Holiday.name))).all()
        }
        added = 0
        for holiday_date, name in sorted(india_holidays.items()):
            key = (holiday_date, name)
            if key in existing:
                continue
            session.add(
                Holiday(
                    holiday_date=holiday_date,
                    name=name,
                    data_origin="public_import",
                    source_name=SOURCE_NAME,
                )
            )
            added += 1
        print(f"Seeded {added} new holiday(s) for year(s) {years} (source: {SOURCE_NAME}).")


if __name__ == "__main__":
    asyncio.run(main())
