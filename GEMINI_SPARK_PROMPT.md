# Alpha Hunter v2.4 — Daily Research Layer

Use the `alpha-hunter-market-research-layer` skill.

## Canonical source

Repository: `https://github.com/pa45251/alpha-hunter-v2`
Branch: `main`

FIRST open only:
`https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/manifest.json`

Hard gate:
- repository must equal `pa45251/alpha-hunter-v2`
- branch must equal `main`
- `schema_version == 2.4`
- `scanner_version == 2.4`
- `status == PASS`
- all required files must exist

If any check fails: `DATA ACCESS FAILED / DATA QUALITY WARNING — STOP`.
Do not search for similarly named repositories and do not substitute Streamlit or external price sites for scanner data.

## Required inputs after manifest passes

Read the canonical raw URLs from the manifest for:
- market_snapshot.csv
- theme_breadth.csv
- taiwan_candidates.csv
- taiwan_industry_breadth.csv
- transmission_watchlist.csv
- transmission_linkage_audit.csv
- economic_linkage_graph.csv

## v2.4 research rule

The scanner no longer infers Global → Taiwan causality from broad industry labels.
A transmission row exists only because an explicit company-level Economic Linkage Graph edge passed the quant/linkage gate.

BUT the row is still only `HYPOTHESIS_ONLY`.

For every top transmission hypothesis validate:
1. Is the company actually exposed to the stated economic role today?
2. Is the linkage material enough to affect revenue/EPS/order expectations?
3. Is the current global catalyst relevant to that exact business segment?
4. Is there direct company / customer / order / product evidence?
5. What is the strongest counter-evidence?

Classify causal validation:
- CONFIRMED
- PARTIALLY_CONFIRMED
- NOT_CONFIRMED
- CONTRADICTED
- UNKNOWN

Do not promote a hypothesis merely because the Taiwan stock price is strong.
Do not infer Hidden Dragon status until Taiwan quantitative data AND company-specific causal validation both pass.

No Buy / Sell / position sizing.
