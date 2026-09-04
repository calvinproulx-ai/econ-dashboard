#!/usr/bin/env python3
"""
Pull every FRED series the dashboard needs and write ./data.json.

Runs in GitHub Actions (see .github/workflows/update-data.yml), where there is
no CORS restriction and the API key lives in a repo secret. The dashboard page
then loads data.json same-origin, so the browser never talks to FRED directly.

Usage:  FRED_API_KEY=... python scripts/fetch_fred.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

API = "https://api.stlouisfed.org/fred/series/observations"
START = "2003-01-01"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.json")

KEY = os.environ.get("FRED_API_KEY", "").strip()
if not KEY:
    sys.exit("FRED_API_KEY is not set. Add it as a repository secret.")

# series id -> aggregate daily observations to a monthly average?
SERIES = {
    # labor
    "UNRATE": False,          # US unemployment rate, %
    "FLUR": False,            # Florida unemployment rate, %
    "PAYEMS": False,          # total nonfarm employment, thousands
    "CES7000000003": False,   # avg hourly earnings, leisure & hospitality, $
    "CES0500000003": False,   # avg hourly earnings, total private, $
    # prices
    "CPIAUCSL": False,        # CPI all items, index
    "CPILFESL": False,        # CPI less food & energy, index
    "CUSR0000SEFV": False,    # CPI food away from home, index
    "WPUSI012011": False,     # PPI inputs to construction industries, index
    # rates
    "DGS2": True,             # 2-year treasury, daily
    "DGS5": True,             # 5-year treasury, daily
    "DGS10": True,            # 10-year treasury, daily
    "SOFR": True,             # secured overnight financing rate, daily
    "TB3MS": False,           # 3-month t-bill, monthly
    "MPRIME": False,          # bank prime loan rate, monthly
    "FEDFUNDS": False,        # fed funds effective rate, monthly
    # consumer, housing, commodities
    "DSPIC96": False,         # real disposable personal income, bil chained 2017$
    "PCESC96": False,         # real PCE services, bil chained 2017$
    "HOUST": False,           # housing starts, thousands of units
    "MCOILWTICO": False,      # WTI crude, $/bbl
    "DTWEXBGS": True,         # nominal broad USD index, daily
}


def fetch(series_id, aggregate):
    params = {
        "series_id": series_id,
        "api_key": KEY,
        "file_type": "json",
        "observation_start": START,
        "sort_order": "asc",
    }
    if aggregate:
        params["frequency"] = "m"
        params["aggregation_method"] = "avg"
    url = API + "?" + urllib.parse.urlencode(params)

    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "econ-dashboard/2.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.load(resp)
            if "observations" not in payload:
                raise RuntimeError(payload.get("error_message", "no observations in response"))
            return [
                {"d": o["date"][:7], "v": float(o["value"])}
                for o in payload["observations"]
                if o["value"] not in (".", "")
            ]
        except Exception as exc:  # noqa: BLE001 - retry on anything transient
            last_err = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"{series_id}: {last_err}")


def shift_month(d, n):
    """Return the month string n months before d ('2026-08' -> '2025-08' for n=12)."""
    year, month = int(d[:4]), int(d[5:7])
    month -= n
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    return f"{year:04d}-{month:02d}"


def yoy(series, digits=2):
    """Percent change vs the same month a year earlier."""
    by_date = {x["d"]: x["v"] for x in series}
    out = []
    for x in series:
        prior = by_date.get(shift_month(x["d"], 12))
        if prior:
            out.append({"d": x["d"], "v": round((x["v"] - prior) / prior * 100, digits)})
    return out


def with_yoy(series, digits=2):
    """Keep the level and attach a year-over-year percent change."""
    by_date = {x["d"]: x["v"] for x in series}
    out = []
    for x in series:
        prior = by_date.get(shift_month(x["d"], 12))
        out.append({
            "d": x["d"],
            "v": round(x["v"], 1),
            "yoy": round((x["v"] - prior) / prior * 100, digits) if prior else None,
        })
    return out


def mom_change(series):
    """Month-over-month level change, skipping any gap in the monthly sequence."""
    out = []
    for prev, cur in zip(series, series[1:]):
        if cur["d"] == shift_month(prev["d"], -1):
            out.append({"d": cur["d"], "v": round(cur["v"] - prev["v"])})
    return out


def rounded(series, digits):
    return [{"d": x["d"], "v": round(x["v"], digits)} for x in series]


def main():
    raw = {}
    failures = []
    for series_id, aggregate in SERIES.items():
        try:
            raw[series_id] = fetch(series_id, aggregate)
            print(f"  ok   {series_id:<14} {len(raw[series_id]):>4} obs, "
                  f"last {raw[series_id][-1]['d']}={raw[series_id][-1]['v']}")
        except Exception as exc:  # noqa: BLE001
            failures.append(str(exc))
            print(f"  FAIL {series_id:<14} {exc}", file=sys.stderr)

    # A partial refresh would silently blank out charts, so refuse to write one.
    if failures:
        sys.exit("Aborting without writing data.json:\n  " + "\n  ".join(failures))

    rate_rows = defaultdict(dict)
    for key, series_id in [
        ("tb3ms", "TB3MS"), ("two_yr", "DGS2"), ("five_yr", "DGS5"),
        ("ten_yr", "DGS10"), ("prime", "MPRIME"), ("sofr", "SOFR"),
        ("fedfunds", "FEDFUNDS"),
    ]:
        for obs in raw[series_id]:
            rate_rows[obs["d"]][key] = round(obs["v"], 2)

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start": START,
        "series": {
            # labor
            "unemployment": rounded(raw["UNRATE"], 1),
            "fl_unemployment": rounded(raw["FLUR"], 1),
            "nonfarm": mom_change(raw["PAYEMS"]),
            "wages_lh": with_yoy(raw["CES7000000003"]),
            "wages_total": with_yoy(raw["CES0500000003"]),
            # prices (year-over-year percent)
            "cpi": yoy(raw["CPIAUCSL"]),
            "core_cpi": yoy(raw["CPILFESL"]),
            "food_away": yoy(raw["CUSR0000SEFV"]),
            "construction_ppi": yoy(raw["WPUSI012011"]),
            # rates
            "rates": [dict(d=month, **vals) for month, vals in sorted(rate_rows.items())],
            # consumer, housing, commodities
            "disposable": with_yoy(raw["DSPIC96"]),
            "consumer_services": with_yoy(raw["PCESC96"]),
            "housing": rounded(raw["HOUST"], 0),
            "crude": rounded(raw["MCOILWTICO"], 2),
            "usd": rounded(raw["DTWEXBGS"], 2),
        },
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"), sort_keys=False)
        fh.write("\n")

    size_kb = os.path.getsize(OUT) / 1024
    print(f"\nwrote {OUT} ({size_kb:.0f} KB), generated {data['generated']}")


if __name__ == "__main__":
    main()
