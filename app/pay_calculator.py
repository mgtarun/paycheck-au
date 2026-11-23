"""Calculate award pay for one shift from the MAPD CSVs. Pure Python, no LLM.

v1 scope: Hospitality award (MA000009), adult employees, ordinary hours only.
Not yet covered: overtime, evening/night penalties, junior and apprentice rates,
allowances, managerial and casino gaming staff.

Run: python app/pay_calculator.py "Level 2" casual sunday 6 [YYYY-MM-DD]
The optional date is the shift date (default: today), so past shifts use the
rates that applied at the time.
"""

import sys
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

AWARD = "MA000009"
DATA = "data/processed"

# classification_fixed_id for each level in Table 3 (clause 18.1).
# Fixed IDs stay the same every year; rates don't.
CLASSIFICATIONS = {
    "Introductory level": 242,
    "Level 1": 243,
    "Level 2": 246,
    "Level 3": 257,
    "Level 4": 268,
    "Level 5": 276,
    "Level 6": 282,
}

# Words that identify the right penalty rows in clause_description and
# penalty_description (checked against the real penalties.csv).
EMPLOYMENT_GROUP = {
    "casual": "adult casual",
    "full_time": "adult full-time and part-time",
    "part_time": "adult full-time and part-time",
}
DAY_PATTERN = {
    "weekday": r"^ordinary hours",
    "saturday": r"^saturday",
    "sunday": r"^sunday",
    "public_holiday": r"^public holiday",
}

# Minimum paid hours per shift, from the award text.
MIN_HOURS = {
    ("casual", "any"): (Decimal(2), "11.3"),
    ("casual", "public_holiday"): (Decimal(2), "29.4(b)"),
    ("full_time", "public_holiday"): (Decimal(4), "29.4(a)"),
    ("part_time", "public_holiday"): (Decimal(4), "29.4(a)"),
}
MAX_CASUAL_SHIFT = Decimal(12)  # clause 11.2(a); beyond this is overtime


@dataclass
class PayResult:
    level: str
    employment: str
    day: str
    shift_date: date
    rates_from: str  # operative_from of the rates used
    hours_worked: Decimal
    hours_paid: Decimal
    ordinary_rate: Decimal  # minimum hourly rate (Table 3)
    percent: Decimal  # e.g. 175 for casual Sunday
    hourly_rate: Decimal  # ordinary_rate x percent, rounded to cents
    total: Decimal
    notes: list[str]


def money(x) -> Decimal:
    """Round to cents, half up, using exact decimal maths."""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(f"{DATA}/{AWARD}_{name}.csv").drop_duplicates()


def exactly_one(df: pd.DataFrame, what: str) -> pd.Series:
    """Return the only matching row. Fail loudly on 0 or 2+ matches."""
    if len(df) == 0:
        raise ValueError(f"No row found for {what}")
    if len(df) > 1:
        raise ValueError(
            f"{len(df)} rows matched {what}; make the filter stricter:\n"
            f"{df.head(10).to_string()}"
        )
    return df.iloc[0]


def in_force(df: pd.DataFrame, on: date) -> pd.DataFrame:
    """Keep only the rows that applied on this date.

    The CSVs hold several years of rates. For each date, the rates in force are
    the ones with the latest operative_from that is on or before that date.
    """
    started = df[pd.to_datetime(df["operative_from"]).dt.date <= on]
    if started.empty:
        return started
    return started[started["operative_from"] == started["operative_from"].max()]


def ordinary_rate(level: str, on: date) -> tuple[Decimal, str, str]:
    """Minimum hourly rate for an adult at this level on a date.

    Returns (rate, base_pay_rate_id, operative_from).
    """
    if level not in CLASSIFICATIONS:
        raise ValueError(
            f"Unknown level {level!r}. Options: {', '.join(CLASSIFICATIONS)}"
        )
    fixed_id = CLASSIFICATIONS[level]
    if fixed_id is None:
        raise ValueError(
            f"Set CLASSIFICATIONS[{level!r}] to its classification_fixed_id"
        )
    rates = load("pay_rates")
    rows = in_force(rates[rates["classification_fixed_id"] == fixed_id], on)
    row = exactly_one(rows, f"{level} pay rate on {on}")
    # Table 3 rows store a weekly base rate and a calculated hourly rate.
    hourly = (
        row["calculated_rate"]
        if row["base_rate_type"] == "Weekly"
        else row["base_rate"]
    )
    return money(hourly), row["base_pay_rate_id"], str(row["operative_from"])


def penalty_percent(
    employment: str, day: str, base_id: str, on: date
) -> tuple[Decimal, object]:
    """Percentage of the ordinary rate for this employment type, day and date.

    Returns (percent, FWC calculated dollar value or NaN).
    """
    pens = load("penalties")
    group = pens["clause_description"].str.lower()
    desc = pens["penalty_description"].str.lower().str.strip()
    rows = pens[
        group.str.contains(EMPLOYMENT_GROUP[employment], regex=False)
        & group.str.contains("penalty", regex=False)
        & ~group.str.contains("overtime|casino|apprentice", regex=True)
        & desc.str.contains(DAY_PATTERN[day], regex=True)
    ]
    rows = in_force(rows, on)
    what = f"{employment} {day} penalty on {on}"

    # Usually there is one row per classification, linked by base_pay_rate_id.
    linked = rows[rows["base_pay_rate_id"] == base_id]
    if len(linked):
        row = exactly_one(linked, what)
        return Decimal(str(row["rate"])), row["penalty_calculated_value"]

    # Some older rows aren't linked. Their percentage is the same for every
    # level, so use it, but skip the dollar cross-check.
    percents = rows["rate"].dropna().unique()
    if len(percents) == 0:
        raise ValueError(f"No row found for {what}")
    if len(percents) > 1:
        raise ValueError(f"Different percentages found for {what}: {sorted(percents)}")
    return Decimal(str(percents[0])), float("nan")


def minimum_hours(employment: str, day: str) -> tuple[Decimal, str] | None:
    return MIN_HOURS.get((employment, day)) or MIN_HOURS.get((employment, "any"))


def calculate(
    level: str, employment: str, day: str, hours, on: date | str | None = None
) -> PayResult:
    if employment not in EMPLOYMENT_GROUP:
        raise ValueError(f"employment must be one of {', '.join(EMPLOYMENT_GROUP)}")
    if day not in DAY_PATTERN:
        raise ValueError(f"day must be one of {', '.join(DAY_PATTERN)}")
    on = date.fromisoformat(on) if isinstance(on, str) else (on or date.today())
    hours = Decimal(str(hours))
    if hours <= 0:
        raise ValueError("hours must be more than 0")
    if employment == "casual" and hours > MAX_CASUAL_SHIFT:
        raise ValueError(
            "Casual shifts over 12 hours include overtime (clause 11.4), "
            "which v1 doesn't calculate"
        )

    notes: list[str] = []
    base, base_id, rates_from = ordinary_rate(level, on)
    percent, fwc_value = penalty_percent(employment, day, base_id, on)
    hourly = money(base * percent / 100)

    # Cross-check against the FWC's own calculated dollar rate, if it gave one.
    if pd.notna(fwc_value) and money(fwc_value) != hourly:
        raise ValueError(
            f"Our rate ${hourly} doesn't match the FWC's ${money(fwc_value)}"
        )

    paid = hours    # start with hours actually worked
    minimum = minimum_hours(employment, day)
    if minimum and hours < minimum[0]:  # worked less than the minimum?
        paid = minimum[0]   # pay the minimum instead
        notes.append(f"Paid the minimum {minimum[0]} hours (clause {minimum[1]})")

    return PayResult(
        level,
        employment,
        day,
        on,
        rates_from,
        hours,
        paid,
        base,
        percent,
        hourly,
        money(hourly * paid),
        notes,
    )


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(
            'Usage: python app/pay_calculator.py "Level 2" casual sunday 6 [YYYY-MM-DD]'
        )
    r = calculate(*sys.argv[1:])
    print(
        f"{r.level}, {r.employment}, {r.day}, {r.hours_worked} hours on {r.shift_date}"
    )
    print(f"  Using rates in force from {r.rates_from}")
    print(f"  Ordinary rate: ${r.ordinary_rate}/hour (clause 18.1, Table 3)")
    print(
        f"  Rate for this shift: {r.percent}% = ${r.hourly_rate}/hour (clause 29.2, Table 14)"
    )
    for note in r.notes:
        print(f"  Note: {note}")
    print(f"  Total: ${r.hourly_rate} x {r.hours_paid} hours = ${r.total}")