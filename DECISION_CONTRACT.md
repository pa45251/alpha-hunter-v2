# Alpha Hunter v2.7 — Decision Contract

## Purpose
The Decision Layer converts validated research into an auditable portfolio decision. It is downstream of the deterministic scanner, Research Layer, structural exposure graph, and Taiwan price-reaction sensor.

Canonical sequence:

`Global Scanner -> Causal Research -> Structural Transmission -> Decision Gate -> ETF / Stock / Cash -> Entry -> Risk -> Exit -> Shadow Audit`

The Decision Layer may make portfolio decisions. Upstream layers may not.

## Non-negotiable hierarchy
**GATE FIRST, SCORE SECOND.**

No weighted score may compensate for a failed hard gate. Price cannot create causality. A strong stock cannot rescue an UNKNOWN driver. A strong driver cannot rescue an unverified company edge. A correct thesis does not justify chasing an EXTENDED price state.

## Gate 0 — Data integrity
The current deterministic hard gate must be PASS. The Decision Layer must consume outputs from the same canonical `run_id`. Mixed snapshots stop the run.

## Gate 1 — Global causal edge
New long exposure requires the exact driver to be `ACTIVE` and research-valid.

- `ACTIVE` -> may continue.
- `UNKNOWN` -> no new buy; research/watch only.
- `INACTIVE` -> no new buy; existing positions require thesis review.

Price action is never evidence for activation.

## Gate 2 — Company economic transmission
A Taiwan stock may proceed only when the driver-to-company edge is economically current and `provenance_status == SOURCE_BACKED`.

`NEEDS_SOURCE_BACKFILL`, stale provenance, speculative edges, or unsupported broad-industry substitution are hard blockers for a stock BUY decision.

Required company-level audit should cover, when relevant:
- revenue/product exposure;
- order/backlog/shipment exposure;
- customer/program exposure;
- ASP or earnings sensitivity;
- capacity constraints;
- margin dilution / offsetting risks.

Do not backfill the entire graph merely to increase coverage. Prioritize ACTIVE-driver edges attached to PRE_CONFIRMATION, early CONFIRMING, or controlled PULLBACK candidates.

## Gate 3 — ETF vs Stock vs Cash
The system is Global-first and Core-Satellite.

- `STOCK` only when a source-backed Taiwan edge offers a clear incremental alpha case over the cleanest available ETF exposure.
- `ETF_ONLY` when the global driver/theme is attractive but the Taiwan stock edge is weak, unverified, already overextended, or not clearly superior to ETF exposure.
- `KEEP_CASH` when the global edge itself is insufficient, contradictory, or there is no acceptable executable exposure.

The system must never choose a stock merely because a stock candidate exists.

## Gate 4 — Information transmission / reaction state
After causality and structural exposure are independently validated, price may be used as confirmation or falsification evidence.

Interpretation:
- `PRE_CONFIRMATION` -> potential information-transmission opportunity; not yet a BUY by itself.
- `EARLY_CONFIRMATION` / early `CONFIRMING` -> eligible for entry-trigger evaluation.
- controlled `PULLBACK` -> eligible for pullback-entry evaluation if causal thesis remains intact.
- `PERSISTENT` -> thesis confirmed but more information may already be priced; require stronger stock-vs-ETF edge.
- `EXTENDED` -> new-buy chase blocker.
- `BROKEN` -> transmission contradiction; no new buy and review existing position.
- `UNKNOWN` -> wait.

**Price cannot create causality, but price may falsify an expected transmission.**

## Gate 5 — Entry
Passing Gates 0-4 creates `ENTRY_RESEARCH_READY`, not an automatic BUY.

A BUY requires a separately defined, point-in-time executable setup. Entry rules must be deterministic, versioned, and validated with no-lookahead / walk-forward / shadow audit before they are allowed to control real capital.

Until an entry rule is explicitly validated, the engine must return `WATCH_ENTRY` rather than inventing a threshold.

## Gate 6 — Risk and exit
Exit reasons are hierarchical and must preserve the original thesis.

1. `CAUSAL_EXIT`: original driver becomes INACTIVE or materially contradicted.
2. `TRANSMISSION_EXIT`: driver remains ACTIVE but the company-level economic edge fails.
3. `MARKET_FALSIFICATION_EXIT`: driver remains ACTIVE but the stock persistently fails expected transmission relative to relevant peers/exposure; BROKEN is a warning state, not proof by itself.
4. `PORTFOLIO_RISK_EXIT`: concentration, drawdown, liquidity, gap risk, or portfolio risk budget requires reduction even if the thesis is not fully invalidated.

Research truth is not portfolio permission.

## Existing-position actions
Existing holdings are evaluated against their locked original thesis and may output only:

`ADD`, `HOLD`, `REDUCE`, `EXIT`, `ROTATE`, `REVIEW_REQUIRED`

New-candidate actions may output only:

`BUY_STOCK`, `BUY_ETF`, `WATCH_ENTRY`, `WATCH_RESEARCH`, `NO_BUY_EXTENDED`, `AVOID_BROKEN`, `KEEP_CASH`

Until ETF mapping, entry trigger, and risk budget modules are validated, deterministic code must not emit `BUY_STOCK`, `BUY_ETF`, `ADD`, `REDUCE`, `EXIT`, or `ROTATE` automatically.

## Anti-overfitting / anti-hindsight rules
- Point-in-time data only; no lookahead.
- Do not change a rule because of one recent winner or loser.
- Validate new thresholds with walk-forward / out-of-sample tests, parameter sensitivity, ablation, and shadow trading where feasible.
- Preserve the rule/version and information set used at decision time.
- Do not rewrite the original thesis after the outcome is known.
- Prefer simple hard gates over an opaque composite trade score.

## Shadow audit
Every decision snapshot must retain:
- canonical `run_id`;
- decision-contract version;
- driver state and research timestamp;
- edge provenance state;
- reaction state;
- stock-vs-ETF conclusion when available;
- entry state when available;
- action and blockers;
- original thesis identifier for existing positions.

The audit exists to evaluate the decision process as it was known at the time, not to optimize history after the fact.
