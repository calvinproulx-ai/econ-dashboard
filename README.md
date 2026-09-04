# Economic Indicators Dashboard

US macro and rates dashboard for **The Plantation at Ponte Vedra**, published at
<https://calvinproulx-ai.github.io/econ-dashboard/>.

All data comes from [FRED](https://fred.stlouisfed.org/) (Federal Reserve Bank of St. Louis).

---

## How it updates

```
GitHub Action (daily, 13:17 UTC)
      │
      ├─ scripts/fetch_fred.py  ──► api.stlouisfed.org   (server side, no CORS involved)
      │
      └─ commits data.json to this repo
                  │
                  └─ index.html fetches ./data.json  (same origin, always works)
```

The page **never calls the FRED API from the browser.** That was the bug in the
previous version: `api.stlouisfed.org` sends no `Access-Control-Allow-Origin`
header, so a browser `fetch()` from `github.io` is blocked by the same-origin
policy. The old page tried a `corsproxy.io` fallback; that service now requires
a registered key, so both legs failed and the page silently fell back to data
baked in at build time. It looked like it was working. It was showing June 2025.

Moving the fetch into a scheduled Action removes the problem entirely — a
server-side request has no CORS restriction, and the API key never reaches a
browser.

## First-time setup

1. **Add the API key as a repository secret**
   `Settings → Secrets and variables → Actions → New repository secret`
   * Name: `FRED_API_KEY`
   * Value: your FRED key — get one free at
     <https://fredaccount.stlouisfed.org/apikeys>

   > ⚠️ The key that was hardcoded in the old `index.html` is public — it is in
   > this repo's git history and on every page load. **Revoke it and issue a new
   > one**, then use the new key here.

2. **Allow Actions to commit**
   `Settings → Actions → General → Workflow permissions` → *Read and write permissions*

3. **Generate the first `data.json`**
   `Actions → Update FRED data → Run workflow`

   Until that runs the page shows a red "No data" banner telling you exactly this.

4. Confirm GitHub Pages is serving from the branch root
   (`Settings → Pages`).

## Running it locally

```bash
FRED_API_KEY=your_key python scripts/fetch_fred.py
python -m http.server 8000        # then open http://localhost:8000
```

`file://` will not work — `fetch()` cannot read a local file from a `file://`
page. Use a local server.

## Layout

| Section | Contents |
|---|---|
| Latest Highlights | Six plain-language reads: staffing cost, dues/inflation, F&B, capital escalation, reserve yield, financing |
| KPI strip | Twelve headline numbers with year-over-year change |
| Labor & Wages | FL vs US unemployment, payrolls, hourly earnings vs CPI |
| Prices & Cost Inputs | Headline vs core CPI, food away from home, construction inputs |
| Rates | Fed funds, SOFR, 3-mo bill, 2/5/10-yr, prime |
| Consumer, Housing & Commodities | Real income, PCE services, housing starts, WTI, USD index |

## Series tracked

| ID | Series | Why it's here |
|---|---|---|
| `UNRATE` / `FLUR` | Unemployment, US and Florida | Local hiring conditions for club staffing |
| `PAYEMS` | Non-farm payrolls | National labor momentum |
| `CES7000000003` | Avg hourly earnings, leisure & hospitality | Closest public benchmark to club payroll |
| `CES0500000003` | Avg hourly earnings, all private | Comparison baseline |
| `CPIAUCSL` / `CPILFESL` | CPI headline and core | Dues escalation anchor |
| `CUSR0000SEFV` | CPI, food away from home | Clubhouse F&B cost proxy |
| `WPUSI012011` | PPI, inputs to construction | Reserve study / capital plan escalation |
| `TB3MS`, `SOFR`, `FEDFUNDS` | Short rates | What reserve cash earns |
| `DGS2`, `DGS5`, `DGS10`, `MPRIME` | Curve and prime | Capital project financing cost |
| `DSPIC96`, `PCESC96` | Real income, PCE services | Member discretionary spending backdrop |
| `HOUST` | Housing starts | Residential construction activity |
| `MCOILWTICO` | WTI crude | Energy and transport cost input |
| `DTWEXBGS` | Broad USD index | General market context |

Daily series (2/5/10-yr, SOFR, USD index) are averaged to monthly in
`fetch_fred.py`. CPI, PPI and wage series are converted to year-over-year
percent change. Payrolls are the month-over-month change in the level.

## If it stops updating

The page tells you. A yellow **"Stale"** pill appears once `data.json` is more
than four days old, with a pointer to the Actions tab. Most likely causes:

* `FRED_API_KEY` secret expired, revoked, or never added
* Workflow permissions reverted to read-only
* Actions disabled on the repo after a period of inactivity — GitHub pauses
  scheduled workflows in repos with no commits for 60 days; pushing any commit
  re-enables them

`fetch_fred.py` refuses to write a partial file: if any series fails, it exits
non-zero and leaves the previous `data.json` in place, so a FRED outage shows
you slightly old data rather than a half-blank dashboard.

