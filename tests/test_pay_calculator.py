"""Pay calculator tests, checked against the award's own Schedule B.

Expected rates come from MA000009 Schedule B.2.1 and B.2.3 (rates from 1 July 2026).

Uses the fixed test data in tests/fixtures/ (see make_fixtures.py), so no download is needed.
Run from the paycheck-au folder:  python -m pytest -v
"""

from datetime import date
from decimal import Decimal

import pytest

from app.pay_calculator import calculate

# Schedule B values below are the rates from 1 July 2026, so test shifts on that date.
# Pinning the date keeps these tests passing after next year's rates are downloaded.
ON = date(2026, 7, 1)

LEVELS = [
    "Introductory level",
    "Level 1",
    "Level 2",
    "Level 3",
    "Level 4",
    "Level 5",
    "Level 6",
]

# Schedule B.2.3: adult casual employees, $ per hour
CASUAL = {
    "weekday": ["32.18", "33.05", "33.85", "34.96", "36.81", "39.13", "40.16"],
    "saturday": ["38.61", "39.66", "40.62", "41.96", "44.18", "46.95", "48.20"],
    "sunday": ["45.05", "46.27", "47.39", "48.95", "51.54", "54.78", "56.23"],
    "public_holiday": ["64.35", "66.10", "67.70", "69.93", "73.63", "78.25", "80.33"],
}
# Schedule B.2.1: adult full-time and part-time employees, $ per hour
FULL_TIME = {
    "weekday": ["25.74", "26.44", "27.08", "27.97", "29.45", "31.30", "32.13"],
    "saturday": ["32.18", "33.05", "33.85", "34.96", "36.81", "39.13", "40.16"],
    "sunday": ["38.61", "39.66", "40.62", "41.96", "44.18", "46.95", "48.20"],
    "public_holiday": ["57.92", "59.49", "60.93", "62.93", "66.26", "70.43", "72.29"],
}


def cases(table, employment):
    for day, rates in table.items():
        for level, rate in zip(LEVELS, rates, strict=True):
            yield level, employment, day, Decimal(rate)


@pytest.mark.parametrize(
    "level, employment, day, expected",
    [
        *cases(CASUAL, "casual"),
        *cases(FULL_TIME, "full_time"),
        *cases(FULL_TIME, "part_time"),
    ],
)
def test_hourly_rate_matches_schedule_b(level, employment, day, expected):
    assert calculate(level, employment, day, 8, ON).hourly_rate == expected


def test_the_example_question():
    # Level 2, casual, Sunday, 6 hours -> $47.39 x 6
    assert calculate("Level 2", "casual", "sunday", 6, ON).total == Decimal("284.34")


def test_casual_minimum_two_hours():
    r = calculate("Level 2", "casual", "weekday", 1, ON)
    assert r.hours_paid == 2
    assert r.total == Decimal("67.70")


def test_full_time_public_holiday_minimum_four_hours():
    r = calculate("Level 2", "full_time", "public_holiday", 3, ON)
    assert r.hours_paid == 4
    assert r.total == Decimal("243.72")


def test_part_hours():
    assert calculate("Level 2", "casual", "sunday", 6.5, ON).total == Decimal("308.04")


@pytest.mark.parametrize(
    "args",
    [
        ("Level 2", "casual", "sunday", 0),  # no hours
        ("Level 2", "casual", "sunday", 13),  # overtime, not supported yet
        ("Level 9", "casual", "sunday", 6),  # unknown level
        ("Level 2", "contractor", "sunday", 6),  # unknown employment type
        ("Level 2", "casual", "funday", 6),  # unknown day
    ],
)
def test_rejects_bad_input(args):
    with pytest.raises(ValueError):
        calculate(*args, ON)


def test_uses_rates_in_force_on_the_shift_date():
    current = calculate("Level 2", "casual", "sunday", 6, ON)
    earlier = calculate("Level 2", "casual", "sunday", 6, date(2026, 6, 30))
    assert current.rates_from == "2026-07-01"
    assert earlier.rates_from < current.rates_from
    assert earlier.hourly_rate < current.hourly_rate


def test_accepts_date_as_text():
    assert calculate("Level 2", "casual", "sunday", 6, "2026-07-01").total == Decimal(
        "284.34"
    )


def test_date_before_any_rates_is_rejected():
    with pytest.raises(ValueError, match="No row found"):
        calculate("Level 2", "casual", "sunday", 6, date(1999, 1, 1))