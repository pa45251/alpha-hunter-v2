# Alpha Hunter v2

A durable **Global Trend Sensor** for the user's Global Regime → ETF Core → Taiwan Alpha workflow.

## Architecture

1. **Fixed market skeleton** — stable factor/industry ETFs and macro proxies.
2. **Broad global universe** — stocks grouped by theme; expandable without changing the decision rules.
3. **Dynamic Leader Engine** — calculates raw return, relative strength, acceleration, trend, volume, drawdown, 52-week position and two Keynes variants.
4. **Breadth Engine** — measures whether a theme is broad or only held up by a few names.
5. **Leader Registry** — uses confirmation streaks/hysteresis to reduce one-day ranking churn.
6. **Gemini Spark** — adds causes, fundamentals, catalysts, counter-evidence and missing-universe candidates.
7. **ChatGPT** — performs the final causal audit, ETF-vs-stock decision, risk budget, entry/exit and weekly shadow audit.

## Keynes indicators

### Legacy
Retains the original idea:
`8 * 20D momentum - 1.5 * (90D std(price) / 90D EMA(price))`

### v2 (experimental)
`(20D return / 20D realized return volatility) * Efficiency Ratio(20D)`

v2 is intended to measure **trend quality**: clean persistent movement scores better than a choppy path with the same endpoint return.
Neither is a calibrated buy/sell rule. Both are written to `feature_history.csv` for forward testing.

## Leader Score v1
The code includes a deliberately simple, non-optimized provisional score. Raw features are always saved so weekly audits can test whether the score or any component actually predicts future excess return / drawdown.

## Run locally

```bash
pip install -r requirements.txt
python daily_scan.py
streamlit run app.py
```

Outputs:
- `output/market_snapshot.csv`
- `output/market_snapshot.json`
- `output/theme_breadth.csv`
- `output/leader_registry.csv`
- `output/feature_history.csv`

## GitHub Actions (GitHub Free compatible)
Push this folder to a repository. The included workflow runs at 06:55 Asia/Taipei on weekdays (GitHub schedules can be delayed slightly) and can also be run manually.

Repository Settings → Actions → General must allow workflows to write repository contents if you want automatic snapshot commits.

## Optional Google Drive upload
Create a Google Cloud service account, enable Google Drive API, and share one Drive folder with the service-account email.
Then add repository secrets:

- `GDRIVE_SERVICE_ACCOUNT_JSON` — the complete service account JSON (never commit it)
- `GDRIVE_FOLDER_ID` — the destination Drive folder ID

The Action then updates the five output files in that folder. If the secrets do not exist, the scan still runs and saves artifacts/repo snapshots.

## Gemini schedule
Use the provided `GEMINI_SPARK_PROMPT.md` as a weekday Spark task after the scanner has run. Use `GEMINI_WEEKLY_DISCOVERY_PROMPT.md` once per week to propose missing companies/themes.

## Important design rule
**Fixed observation framework; dynamic leaders.** Gemini may propose candidates, but it must not directly rewrite the official universe. This prevents narrative chasing and creates a clean audit trail.
