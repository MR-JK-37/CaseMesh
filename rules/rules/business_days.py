"""Section 7.1: the business-day engine. Pure function, no DB/web code —
the holiday set is handed in by the caller (`app/services/sla.py` reads
it from the `holidays` table). IST has no DST, so there is no DST edge
case to handle here (noted, not silently assumed away) — see the test
module for the property tests this docstring promises."""

from __future__ import annotations

import datetime as dt

_WEEKEND = (5, 6)  # Saturday, Sunday (date.weekday())


def is_business_day(d: dt.date, holidays: frozenset[dt.date]) -> bool:
    return d.weekday() not in _WEEKEND and d not in holidays


def add_business_days(start: dt.date, days: int, holidays: frozenset[dt.date]) -> dt.date:
    """Adds `days` business days to `start`, skipping weekends and the
    given holiday dates. `days` must be >= 0 — the SLA due-date use case
    never needs to go backward, and a negative count would make
    "monotonic in days" meaningless."""
    if days < 0:
        raise ValueError("days must be >= 0")
    current = start
    remaining = days
    while remaining > 0:
        current += dt.timedelta(days=1)
        if is_business_day(current, holidays):
            remaining -= 1
    return current


def business_days_between(start: dt.date, end: dt.date, holidays: frozenset[dt.date]) -> int:
    """Count of business days strictly after `start` up to and including
    `end` — the inverse direction of `add_business_days`, used to answer
    "how many business days has this case been open" (Section 7.3's
    `CASE_STALE`/ageing-bucket use cases). Returns a negative count if
    `end` is before `start` (the caller decides what that means)."""
    if end >= start:
        step = 1
        d = start
        count = 0
        while d < end:
            d += dt.timedelta(days=step)
            if is_business_day(d, holidays):
                count += 1
        return count
    return -business_days_between(end, start, holidays)


def next_business_day(d: dt.date, holidays: frozenset[dt.date]) -> dt.date:
    """Return d if it is already a business day, or the next upcoming business day."""
    current = d
    while not is_business_day(current, holidays):
        current += dt.timedelta(days=1)
    return current


def prev_business_day(d: dt.date, holidays: frozenset[dt.date]) -> dt.date:
    """Return d if it is already a business day, or the previous business day."""
    current = d
    while not is_business_day(current, holidays):
        current -= dt.timedelta(days=1)
    return current


def is_weekend(d: dt.date) -> bool:
    """Return True if the date falls on Saturday or Sunday."""
    return d.weekday() in _WEEKEND
