# Alpha Hunter — CIO Advisory Contract v1.0

## Purpose

The CIO Advisory Layer exists to answer the portfolio decision question under uncertainty without weakening the frozen execution controls.

Canonical sequence:

`Scanner -> Causal Research -> Structural Transmission -> Frozen Execution Decision Board -> CIO Advisory -> Human Decision`

The advisory output is a directional research decision. It is never a brokerage order and never changes `auto_trade_allowed`.

## Core separation

**RECOMMENDATION IS NOT EXECUTION PERMISSION.**

The system must not confuse these two questions:

1. **What is the best directional decision given the current evidence?**
2. **Is the system validated and authorized to execute that decision automatically?**

The CIO Advisory Layer answers the first question.
The frozen Decision / Risk / Launch layers answer the second.

A blocked execution lane therefore does not justify an empty or endlessly deferred advisory answer.

## Advisory obligation

When canonical data integrity is valid, every opportunity row should be reduced to one directional advisory state:

- `BUY_BIAS_STOCK`
- `PROVISIONAL_BUY_BIAS_STOCK`
- `PREFER_ETF`
- `HOLD_BIAS`
- `WAIT_PULLBACK`
- `RESEARCH_FIRST`
- `PASS`
- `AVOID`

The advisory must also emit:

- confidence: `HIGH`, `MEDIUM`, `LOW`, or `INSUFFICIENT`;
- preferred exposure: stock, ETF, cash, or cash-until-entry;
- the evidence gap that prevents higher confidence;
- a short rationale;
- `advisory_is_order = false`;
- `auto_trade_allowed = false`.

## Causal discipline remains intact

**PRICE CANNOT CREATE CAUSALITY.**

- An `INACTIVE_RESEARCH_VALIDATED` driver -> `AVOID`.
- An unresolved driver -> `RESEARCH_FIRST` regardless of price strength.
- A `BROKEN` transmission state -> `AVOID` for new exposure.
- An `EXTENDED` state -> `WAIT_PULLBACK`; do not chase merely to force a decision.

The advisory lane is allowed to express uncertainty. It is not allowed to manufacture causality.

## Stock vs ETF fallback

Company-level provenance is a **stock-alpha gate**, not a global-theme gate.

Therefore:

- If the global causal driver is active but Taiwan stock alpha is weak or not source-backed, a mapped ETF may still be the preferred advisory exposure.
- `SOURCE_BACKED` company evidence is required for a high-confidence stock advisory.
- Strong direct/structural linkage without source-backed company evidence may produce only `PROVISIONAL_BUY_BIAS_STOCK`, never an executable stock order.
- Weak Taiwan stock evidence should fall back to `PREFER_ETF` or cash rather than causing an endless research loop.

This fixes the architecture error where missing company provenance could implicitly block the cleaner ETF route.

## Entry state interpretation

For stock advisories:

- `PRE_CONFIRMATION` / `EARLY_CONFIRMATION` / `CONFIRMING` / controlled `PULLBACK` may support a positive stock bias when causality and company transmission are credible.
- `PERSISTENT` may support `HOLD_BIAS`, but it is not treated as an automatic fresh entry because information may already be priced.
- `EXTENDED` -> `WAIT_PULLBACK`.
- `BROKEN` -> `AVOID`.

ETF advisory does not pretend that Taiwan-stock reaction state is an ETF timing signal. The advisory may prefer the ETF exposure while leaving exact ETF entry timing to a future ETF-specific timing module.

## Confidence is evidence confidence, not a fake win probability

The advisory confidence field measures completeness and consistency of the current evidence. It is not an uncalibrated probability of profit.

- `HIGH`: active driver plus source-backed economic transmission with a coherent non-broken state, or a clean ETF-core route.
- `MEDIUM`: direction is supported but timing, route, or incremental stock alpha remains incomplete.
- `LOW`: favorable causal/structural hypothesis exists but company-level evidence is incomplete.
- `INSUFFICIENT`: the causal driver itself is unresolved.

Win probabilities must not be emitted until they are empirically calibrated out-of-sample.

## Ranking

Advisory ranking is a decision-priority ordering, not an opaque predictive score.

Priority favors:

1. validated positive stock bias;
2. clean ETF fallback;
3. provisional stock hypotheses;
4. hold / wait states;
5. research-first / pass / avoid states.

`research_priority_score` may be used only as a tie-breaker inside the advisory class. It cannot override causal, transmission, or chase-risk rules.

## Frozen execution lane remains unchanged

The CIO Advisory Layer does **not** alter the frozen shadow execution strategy, launch gate, portfolio risk gate, or brokerage authorization.

The following remain true:

- `auto_trade_allowed = false`;
- live execution is disabled;
- execution rules remain subject to shadow validation and acceptance review;
- the advisory layer may be improved without silently rewriting frozen execution history.

This separation lets Alpha Hunter answer the user's real question today while preserving the integrity of future systematic validation.
