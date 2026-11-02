import datetime as dt

from rules.business_days import add_business_days, business_days_between, is_business_day

MONDAY = dt.date(2026, 11, 2)  # confirmed Monday
NO_HOLIDAYS: frozenset[dt.date] = frozenset()


def test_add_zero_days_is_identity():
    assert add_business_days(MONDAY, 0, NO_HOLIDAYS) == MONDAY


def test_add_business_days_skips_weekend():
    # Mon + 5 business days = next Monday (skips Sat/Sun)
    assert add_business_days(MONDAY, 5, NO_HOLIDAYS) == MONDAY + dt.timedelta(days=7)


def test_add_business_days_skips_holiday():
    wednesday = MONDAY + dt.timedelta(days=2)
    holidays = frozenset({wednesday})
    # Mon + 3 business days would land on Thursday normally; the holiday
    # pushes it one further.
    assert add_business_days(MONDAY, 3, NO_HOLIDAYS) == MONDAY + dt.timedelta(days=3)
    assert add_business_days(MONDAY, 3, holidays) == MONDAY + dt.timedelta(days=4)


def test_add_business_days_is_monotonic_in_days():
    results = [add_business_days(MONDAY, n, NO_HOLIDAYS) for n in range(15)]
    assert results == sorted(results)
    assert len(set(results)) == len(results)


def test_add_business_days_rejects_negative():
    try:
        add_business_days(MONDAY, -1, NO_HOLIDAYS)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_is_business_day_weekend():
    saturday = MONDAY + dt.timedelta(days=5)
    sunday = MONDAY + dt.timedelta(days=6)
    assert not is_business_day(saturday, NO_HOLIDAYS)
    assert not is_business_day(sunday, NO_HOLIDAYS)
    assert is_business_day(MONDAY, NO_HOLIDAYS)


def test_business_days_between_inverts_add():
    end = add_business_days(MONDAY, 10, NO_HOLIDAYS)
    assert business_days_between(MONDAY, end, NO_HOLIDAYS) == 10


def test_business_days_between_same_day_is_zero():
    assert business_days_between(MONDAY, MONDAY, NO_HOLIDAYS) == 0


def test_business_days_between_negative_when_reversed():
    end = add_business_days(MONDAY, 5, NO_HOLIDAYS)
    assert business_days_between(end, MONDAY, NO_HOLIDAYS) == -5
