# Alpha Hunter v2.3

A zero-infrastructure-cost market sensing pipeline for:

**Global Sensor → Taiwan Full-Market Sensor → Transmission Hypotheses → Gemini Research → ChatGPT Final Decision**

## What changed in v2.3

### 1. Taiwan Full-Market Sensor
At each scheduled run, the scanner obtains the current TWSE and TPEX security universe from the public TWSE ISIN pages and filters to ordinary four-digit common-stock codes. Yahoo Finance symbols are mapped to `.TW` (TWSE) and `.TWO` (TPEX).

The full universe is scanned in memory using:
- 1D / 5D / 20D / 60D returns
- RS vs `^TWII`
- acceleration
- Keynes Legacy
- Keynes v2
- Efficiency Ratio
- MA structure / slope
- volume ratio
- 20D turnover
- 20D / 52W position
- drawdown / volatility

Only the top discovery funnel is persisted as `taiwan_candidates.csv`. This prevents the Git repository from accumulating a full 1,500–2,000-row market snapshot every day.

### 2. Taiwan Candidate Score v1
A transparent, deliberately non-optimized discovery heuristic. It emphasizes improving RS/acceleration/trend quality rather than simply ranking the strongest already-extended stocks. It is **not a buy signal**.

### 3. Global → Taiwan Transmission Watchlist
`transmission_watchlist.csv` maps strong Global themes to plausible Taiwan industries and combines Global theme strength with Taiwan quantitative candidate quality.

Every row is explicitly `HYPOTHESIS_ONLY`. Gemini must validate the actual economic linkage and fundamentals before downstream use.

### 4. Canonical Data Contract
`output/manifest.json` is the first file every research agent must read. It contains:
- repository identity
- branch
- scanner/schema version
- timestamps
- Global/Taiwan coverage
- Taiwan universe source status
- required file list
- raw canonical URLs
- SHA-256 hashes
- hard-gate instructions

This prevents an agent from searching for a similarly named GitHub repository or silently substituting stale/external data.

## Scheduled flow

GitHub Actions runs at approximately **06:55 Asia/Taipei, Monday–Friday**:

1. Run Global Sensor.
2. Refresh TWSE/TPEX common-stock universe.
3. Scan Taiwan full market.
4. Produce top Taiwan candidates and industry breadth.
5. Produce `HYPOTHESIS_ONLY` Global → Taiwan transmission candidates.
6. Write `manifest.json` last.
7. Commit only canonical research outputs back to the public repository.

No Streamlit page needs to be opened to trigger scanning.

## Canonical files

- `output/manifest.json` — **read first**
- `output/market_snapshot.csv`
- `output/theme_breadth.csv`
- `output/leader_registry.csv`
- `output/feature_history.csv`
- `output/market_snapshot.json`
- `output/taiwan_candidates.csv`
- `output/taiwan_candidate_history.csv`
- `output/taiwan_industry_breadth.csv`
- `output/taiwan_universe.csv`
- `output/transmission_watchlist.csv`

## Cost design

The workflow uses standard GitHub-hosted runners on a public repository and does not upload Actions artifacts or use pip cache. It commits compact research outputs rather than the full Taiwan market matrix.

## Research separation

- **Python**: observable market structure and deterministic candidate funnels.
- **Gemini Spark**: causal/fundamental/counter-evidence research.
- **ChatGPT**: Global regime, ETF-vs-stock decision, portfolio fit, entry/risk/exit, and system audit.
