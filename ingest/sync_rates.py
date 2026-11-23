import os
import sys
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("FWC_API_KEY", "").strip()
headers = {"Ocp-Apim-Subscription-Key": API_KEY}
BASE = "https://api.fwc.gov.au/api/v1"
OUT = "data/processed"

TIMEOUT = (10, 60)  # seconds: (connect, read)
MAX_ATTEMPTS = 3
RETRYABLE = {429, 500, 502, 503, 504}   # status codes worth trying again
MAX_WAIT = 120                          # never wait longer than 2 minutes

ENDPOINTS = {
    "pay_rates": "pay-rates",
    "penalties": "penalties",
    "wage_allowances": "wage-allowances",
}


def fetch_all(path):
    rows, page = [], 1
    while True:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                r = requests.get(f"{BASE}{path}", headers=headers,
                                 params={"page": page, "limit": 100},
                                 timeout=TIMEOUT)
            except (requests.ConnectionError, requests.Timeout) as e:
                problem = type(e).__name__
                wait = 10 * attempt
            else:
                if r.status_code == 200:
                    break
                if r.status_code in (401, 403):
                    raise RuntimeError(
                        f"HTTP {r.status_code} from {path}: check FWC_API_KEY in .env "
                        "is correct and your subscription is active.")
                if r.status_code == 404:
                    raise RuntimeError(
                        f"HTTP 404 from {path}: check the award code and endpoint name.")
                if r.status_code not in RETRYABLE:
                    raise RuntimeError(f"HTTP {r.status_code} from {path}: {r.text[:200]}")
                problem = f"HTTP {r.status_code}"
                retry_after = r.headers.get("Retry-After", "")
                wait = min(int(retry_after), MAX_WAIT) if retry_after.isdigit() else 10 * attempt

            if attempt < MAX_ATTEMPTS:
                print(f"  {path} page {page} -> {problem}, retrying in {wait}s")
                time.sleep(wait)
        else:
            raise RuntimeError(
                f"Failed: {path} page {page} after {MAX_ATTEMPTS} attempts ({problem})")

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
    if not API_KEY:
        sys.exit(
            "FWC_API_KEY is not set.\n"
            "  1. Register at https://developer.fwc.gov.au and copy your key\n"
            "     (Profile > Subscriptions).\n"
            "  2. Create a file called .env in the project folder (copy .env.example).\n"
            "  3. Add the line:  FWC_API_KEY=your-key-here"
        )
    
    awards = sys.argv[1:] or ["MA000009"]
    for code in awards:
        sync_award(code)
    print("Done")