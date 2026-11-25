"""Build the small, fixed test data in tests/fixtures/ from the real CSVs.

The tests use these files instead of data/processed/, so they run anywhere
(your friend's machine, GitHub Actions) without an API key or a download.

Run from the paycheck-au folder, after sync_rates.py has downloaded the data:
    python -m tests.fixtures.make_fixtures

Only rerun this when you mean to refresh the test data (e.g. after a new Annual
Wage Review), and then update the expected values in the tests to match.

Source: Fair Work Commission, Modern Awards Pay Database.
"""

from pathlib import Path

import pandas as pd

from app.pay_calculator import AWARD, CLASSIFICATIONS

SOURCE = Path("data/processed")
OUT = Path(__file__).parent
YEARS_TO_KEEP = 2  # this year plus last year, so the "older rates" test has data
CASINO_LEVEL_2 = 294  # also called "Level 2"; kept to prove it's never picked


def keep_recent_years(df: pd.DataFrame) -> pd.DataFrame:
    dates = sorted(df["operative_from"].dropna().unique(), reverse=True)
    return df[df["operative_from"].isin(dates[:YEARS_TO_KEEP])]


def main() -> None:
    # Pay rates: our 7 levels, plus the casino look-alike.
    pay = pd.read_csv(SOURCE / f"{AWARD}_pay_rates.csv")
    ids = [*CLASSIFICATIONS.values(), CASINO_LEVEL_2]
    pay = keep_recent_years(pay[pay["classification_fixed_id"].isin(ids)])

    # Penalties: adult ordinary and penalty rates, including casino rows
    # (to prove the filter excludes them). Duplicates are kept on purpose,
    # because the real file has them too.
    pen = pd.read_csv(SOURCE / f"{AWARD}_penalties.csv")
    group = pen["clause_description"].str.lower()
    pen = pen[group.str.startswith("adult") & group.str.contains("ordinary and penalty")]
    pen = keep_recent_years(pen)

    pay.to_csv(OUT / f"{AWARD}_pay_rates.csv", index=False)
    pen.to_csv(OUT / f"{AWARD}_penalties.csv", index=False)
    print(f"pay_rates: {len(pay)} rows, years {sorted(pay['operative_from'].unique())}")
    print(f"penalties: {len(pen)} rows, years {sorted(pen['operative_from'].unique())}")
    print(f"saved to {OUT}")


if __name__ == "__main__":
    main()