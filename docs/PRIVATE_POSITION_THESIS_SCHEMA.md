# Alpha Hunter v2.8 — Private Position Thesis Schema

This document contains schema only. Never place real holdings, balances, cost basis, P/L, or position weights in the public repository.

`ALPHA_HUNTER_PORTFOLIO_JSON` remains the private source of truth. Existing fields continue to work. For more precise HOLD / REDUCE / EXIT decisions, each private position may optionally add:

```json
{
  "ticker": "SYNTHETIC_EXAMPLE",
  "market_value_twd": 1000000,
  "risk_groups": ["AI_CAPEX"],
  "thesis_driver_ids": ["AI_SERVER_SHIPMENTS"],
  "thesis_status": "ACTIVE",
  "cost_basis_twd": 950000,
  "unrealized_pnl_pct": 5.26
}
```

## Fields

- `thesis_driver_ids`: preferred explicit mapping from the holding to one or more canonical causal drivers. If omitted, v2.8 falls back to `risk_groups` where a conservative mapping exists.
- `thesis_status`: optional manual override. `INVALIDATED` or `BROKEN` creates `EXIT_THESIS`; otherwise the engine relies on live causal/provenance/reaction gates.
- `cost_basis_twd`: optional. Used only in-memory to derive position P/L when `unrealized_pnl_pct` is absent.
- `unrealized_pnl_pct`: optional. Enables the existing `max_position_loss_pct` policy to create `EXIT_RISK`.

## Decision precedence

1. Explicit private thesis invalidation -> `EXIT_THESIS`.
2. Position loss beyond private risk policy -> `EXIT_RISK`.
3. Source-backed active driver with broken expected transmission and no healthy thesis driver -> `EXIT_THESIS`.
4. Mixed healthy/broken thesis drivers -> `REDUCE_REVIEW`.
5. Healthy source-backed thesis -> `HOLD`.
6. Missing or unresolved thesis evidence -> `REVIEW_THESIS`; missing evidence never invents a sell signal.
7. If portfolio gross exposure is above policy, weakest non-exit positions are nominated first as `REDUCE_RISK` until enough gross exposure is covered.

## Privacy contract

Per-position actions are computed in-memory. Tickers, balances, weights, cost basis and P/L are not written to canonical public outputs or logs. The public decision packet contains only aggregate status/counts.
