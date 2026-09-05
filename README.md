# Alpha Hunter v2.5.1 — Dynamic Causal Transmission Sensor

Alpha Hunter v2.5 separates market observation, causal research, structural economic exposure, Taiwan price confirmation, and final investment decisions.

## Architecture

```text
Global Sensor (what moved)
        ↓
Causal Research Queue (which exact driver needs investigation)
        ↓
Research Layer (why / ACTIVE vs INACTIVE vs UNKNOWN)
        ↓
Structural Exposure Graph (who economically benefits if active)
        ↓
Taiwan Full-Market Sensor (pre-confirmation / confirming / extended / broken)
        ↓
Downstream Final Audit (ETF / stock / cash + risk / entry / exit)
```

## v2.5 hard rules

- Price cannot create causality.
- Broad-industry causal fallback is disabled.
- Structural matching is built from the **full Taiwan scan**, not only top candidates.
- The Taiwan candidate funnel reserves room for early/pre-confirmation stocks and caps extended names.
- A structural match is not an active transmission.
- Dynamic driver activation requires external research evidence.
- Scanner/research layers cannot make trade decisions.

## New canonical files

- `config/causal_driver_taxonomy.csv`
- `config/structural_exposure_graph.csv`
- `input/driver_activation.csv` (optional future research write-back bridge)
- `output/causal_research_queue.csv`
- `output/structural_matches.csv`
- `output/causal_graph_audit.csv`
- `V2_5_DESIGN_REVIEW.md`

The legacy v2.4 `economic_linkage_graph.csv` may remain in the repository for history, but v2.5 does not use it as the production causal engine.

## Daily automation

GitHub Actions runs at approximately 06:55 Asia/Taipei on weekdays. No manual Streamlit trigger is required.

## Optional driver activation bridge

`input/driver_activation.csv` is optional. It is intentionally empty by default. A future research agent can populate known canonical `driver_id` values with evidence, timestamps and confidence. Unknown drivers, stale activations, malformed rows and unsourced activations are ignored.

## Model risk

Read `V2_5_DESIGN_REVIEW.md`. v2.5 is designed to expose uncertainty rather than hide it.


## v2.5.1 Integration hardening
- Keeps schema `2.5` for compatibility, bumps scanner implementation to `2.5.1`.
- Adds a unique `run_id` to each run and to causal queue / structural matches / graph audit.
- Manifest now includes `pipeline_checks` proving those causal artifacts were rebuilt in the current run.
- Gemini canonical source is the exact raw manifest URL; it must not search for similarly named repositories.
- `linkage_confidence` is explicitly a seed prior, not a probability. Unsourced edges remain weak provenance.
