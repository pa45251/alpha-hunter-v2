# Alpha Hunter v2.3 — Daily Research Layer

## Canonical data contract

Always start with this exact file and no substitute:

`https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/manifest.json`

Before research, verify in the manifest:
- `contract == ALPHA_HUNTER_CANONICAL_DATA_CONTRACT`
- `repository == pa45251/alpha-hunter-v2`
- `branch == main`
- `schema_version == 2.3`
- `status == PASS`
- required authoritative files are present
- timestamps are fresh for the market context

If any identity/freshness/contract check fails: output `DATA ACCESS FAILED` or `DATA QUALITY WARNING` and STOP. Do not search for similarly named repositories and do not substitute Streamlit/search/news data for Scanner outputs.

## Official research inputs
Read only the authoritative URLs listed inside `manifest.json`. Prioritize:
- Global market snapshot / breadth / leader registry
- Taiwan full-market candidate funnel / compact candidate history / industry breadth
- Global → Taiwan `HYPOTHESIS_ONLY` transmission watchlist

The Taiwan Sensor scans the full TWSE/TPEX ordinary-common-stock universe, but publishes the candidate funnel rather than every row to avoid Git history bloat.

## Research job
Use the existing `alpha-hunter-market-research-layer` Skill to:
1. Validate important Global leadership changes.
2. Explain primary causal drivers.
3. Check fundamental confirmation: revenue/EPS/guidance/orders/demand/pricing.
4. Separate company-specific vs industry-wide vs macro/factor events.
5. Find counter-evidence.
6. Validate or reject Global → Taiwan transmission hypotheses.
7. Treat `taiwan_candidates.csv` as discovery candidates, NOT buys.
8. Treat `transmission_watchlist.csv` as hypotheses, NOT causal confirmation.
9. Flag missing Global leaders as `UNIVERSE CANDIDATE` without editing the Quant universe.
10. Never give Buy/Sell/position-size recommendations.

Every material catalyst should include source + publication/event date. Use UNKNOWN / CONFLICTING EVIDENCE / HYPOTHESIS when evidence is insufficient.
