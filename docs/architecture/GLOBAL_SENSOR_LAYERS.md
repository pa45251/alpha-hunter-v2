# Global sensor layers

Core remains the 221 reviewed tickers in `config/universe.csv`. Its existing themes,
economic graph, exact-driver taxonomy and trading thresholds are preserved. Core
alone feeds ranks, registry, breadth, risk histories and reverse/causal research.
Labelled non-Core rows are rejected at those global aggregation boundaries.

`broad_discovery.py` refreshes generated S&P 500 membership from DataHub's maintained
constituent source. The snapshot records source, acquisition timestamp and hash.
Daily scan refreshes after 30 days; failed refresh retains a verified cache for at
most 90 days. Schema/size failures do not replace the cache. Core overlap is removed.
A source outage disables Discovery only. No Nasdaq 100 list is hardcoded.

Discovery is separate: `discovery_snapshot.csv`, `discovery_research_queue.csv`.
GICS sub-industry groups require at least three distinct issuers with positive
20/60-session RS and MA20/60 participation; these are research nominations only.
Same-issuer share classes count once. No driver ID, Taiwan candidate or BUY is
created. Promotion requires separately reviewed economic evidence and explicit
Core/taxonomy/exposure-graph changes. Discovery is not automatically ingested by the
existing exact-driver research activation bridge.

Local RS uses listing-market indices (ADR listing, not issuer domicile). Existing
`rs_*_vs_bench` fields now mean Local RS; explicit local and global fields are
retained in the snapshot and feature history. Global RS compares local-currency
asset returns with SPY USD returns; it is a price diagnostic, not an FX-neutral
investment return. Swiss/Danish/UK listings use native-currency indices to avoid
comparing CHF/DKK/GBP securities directly to an EUR index. Regional closes use
local time with a conservative post-close buffer; this is not a full exchange
holiday/early-close calendar. Missing or materially stale local benchmarks do not
fall back to SPY. Helper indices never count toward Core breadth.

`MarketDataProvider` accepts daily OHLCV histories; `YFinanceProvider` is the current
adapter. Downloads deduplicate, batch, retry missing tickers only, reduce retry
batch size, tolerate invalid/empty OHLCV and report missing data. Scheduling budgets
are 300 seconds for Core and 180 for Discovery, checked between provider calls;
in-flight calls can exceed that budget by their provider timeout. Core benchmark
loss still fails closed. Core coverage below 90% cannot pass the daily manifest
(the original minimum count and all downstream causal/risk gates also remain).

`global_scan_quality.json` records requested/scanned counts, missing tickers, local
RS availability, membership provenance and provider timings. All three new outputs
are sealed in the daily manifest. Frozen strategy registries are not rewritten to
conceal drift; this scanner change needs normal review before main deployment.
