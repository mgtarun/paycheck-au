import os
import sys
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
headers = {"Ocp-Apim-Subscription-Key": os.getenv("FWC_API_KEY")}
BASE = "https://api.fwc.gov.au/api/v1"
OUT = "data/processed"

ENDPOINTS = {
    "pay_rates": "pay-rates",
    "penalties": "penalties",
    "wage_allowances": "wage-allowances",
}


def fetch_all(path):
    rows, page = [], 1
    while True:
        for attempt in range(3):
            r = requests.get(f"{BASE}{path}", headers=headers,
                             params={"page": page, "limit": 100})
            if r.status_code == 200:
                break
            print(f"  {path} page {page} -> {r.status_code}, retrying")
            time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"Failed: {path} page {page}")

        data = r.json()
        rows += data["results"]
        if not data["_meta"]["has_more_results"]:
            break
        page += 1
        time.sleep(1)
    return pd.DataFrame(rows)


def sync_award(code):
    os.makedirs(OUT, exist_ok=True)
    for name, ep in ENDPOINTS.items():
        print(f"{code}: fetching {name}...")
        df = fetch_all(f"/awards/{code}/{ep}")
        df["award_code"] = code
        df.to_csv(f"{OUT}/{code}_{name}.csv", index=False)
        print(f"  saved {len(df)} rows")
        time.sleep(2)


if __name__ == "__main__":
    awards = sys.argv[1:] or ["MA000009"]
    for code in awards:
        sync_award(code)
    print("Done")