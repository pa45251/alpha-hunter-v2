# Alpha Hunter — CIO Advisory Contract v1.1

## Purpose

The CIO Advisory Layer exists to answer the portfolio decision question under uncertainty without weakening frozen execution controls.

Canonical sequence:

`Scanner -> Causal Research -> Structural Transmission -> Trend -> Risk Regime -> Entry Location -> CIO Advisory -> Human Decision`

The advisory output is directional decision support. It is never a brokerage order and never changes `auto_trade_allowed`.

## Core philosophy

**FOLLOW THE TREND. BUY WEAKNESS ONLY WHEN THE REGIME STILL SUPPORTS THE TREND.**

The system should not predict crashes merely to justify de-risking, and it should not treat every pullback as a bargain.

The highest-level decision matrix is:

| Trend | Regime | Default CIO stance |
| --- | --- | --- |
| Uptrend | Supportive | HOLD / BUY PULLBACK / ADD |
| Uptrend | Adverse | HOLD / WAIT; fresh dip buying is vetoed |
| Downtrend or broken | Supportive | WAIT FOR RECOVERY |
| Downtrend or broken | Adverse | REDUCE / EXIT / CASH |

This matrix is a decision framework, not an automatic execution rule.

## What each layer is allowed to answer

### Trend

Trend answers whether the asset or relevant market exposure is persistently moving in the desired direction. It may use price structure, relative strength and breadth, but **trend cannot create causality**.

### Macro / risk regime

The regime layer answers whether the wider environment supports taking fresh risk. Volatility, US trend, breadth, credit and global breadth are portfolio-level risk evidence.

An adverse regime does **not** prove that a crash is coming. It means the expected reward for buying weakness is lower and the value of cash/risk reduction is higher.

### Entry location

Entry location answers whether the current setup is extended, confirming or a controlled pullback.

A pullback is not automatically bullish. A pullback becomes a buy candidate only when the trend remains intact and the regime remains supportive.

## Core separation

**RECOMMENDATION IS NOT EXECUTION PERMISSION.**

The system must not confuse these two questions:

1. What is the best directional decision given the current evidence?
2. Is the system validated and authorized to execute that decision automatically?

The CIO Advisory Layer answers the first question. Frozen Decision / Risk / Launch layers answer the second.

## Causal discipline remains intact

**PRICE CANNOT CREATE CAUSALITY.**

- An `INACTIVE_RESEARCH_VALIDATED` driver -> `AVOID`.
- An unresolved driver -> `RESEARCH_FIRST` regardless of price strength.
- A `BROKEN` transmission state -> `AVOID` for new exposure.
- An `EXTENDED` state -> `WAIT_PULLBACK`; do not chase merely to force a decision.
- A `PULLBACK` state may support a fresh risk bias only if the broader regime is supportive.

Price strength can nominate research and describe trend. It cannot manufacture a causal story.

## Regime veto

The regime layer is a veto on **fresh risk**, not a mechanical liquidation trigger.

- `RISK_ON` / `NORMAL` are treated as supportive for fresh pullback entries.
- `CAUTION` / `DEFENSIVE` / `CRISIS` veto fresh dip-buying and shift the default stance toward waiting, holding less risk, or cash.
- `UNKNOWN` fails closed for fresh risk.

Existing positions may remain held if their trend and thesis are intact, but an adverse regime lowers tolerance for deterioration.

## Stock vs ETF fallback

Company-level provenance is a stock-alpha gate, not a global-theme gate.

- If the global causal driver is active but Taiwan stock alpha is weak or not source-backed, a mapped ETF may remain the cleaner exposure.
- `SOURCE_BACKED` company evidence is required for a high-confidence stock advisory.
- Strong direct/structural linkage without source-backed company evidence may produce only a provisional stock bias.
- Weak Taiwan stock evidence should fall back to ETF or cash rather than causing an endless research loop.

## Entry state interpretation

- `PRE_CONFIRMATION` can prepare a future entry but not force one.
- `CONFIRMING` can support a current entry bias only when the regime is supportive.
- `PULLBACK` can support `BUY_PULLBACK_CANDIDATE` only when the trend is intact and the regime is supportive.
- `PERSISTENT` generally favors hold or waiting for a better entry.
- `EXTENDED` -> `WAIT_PULLBACK`.
- `BROKEN` -> `AVOID` for new exposure.

## Avoid overfitting

Do not encode one-off technical anecdotes such as “gap filled = sell” or “below 20DMA = exit” as universal rules.

The framework should remain deliberately simple:

`Trend -> Regime -> Entry Location -> Risk stance`

Causal research remains an independent validation layer. Macro events such as CPI/PPI are evidence updates, not hard-coded event-specific trade rules.

## Confidence is evidence confidence, not a fake win probability

Confidence measures completeness and consistency of evidence. It is not an uncalibrated probability of profit.

## Frozen execution lane remains unchanged

The CIO Advisory Layer does not alter the frozen shadow execution strategy, launch gate, portfolio risk gate, or brokerage authorization.

The following remain true:

- `auto_trade_allowed = false`;
- live execution is disabled;
- execution rules remain subject to shadow validation and acceptance review;
- advisory logic may improve without silently rewriting frozen execution history.
