# Alpha Hunter v2.9 — Private Position Thesis Schema

This document contains schema only. Never place real holdings, balances, cost basis, P/L, or position weights in the public repository.

`ALPHA_HUNTER_PORTFOLIO_JSON` remains the private source of truth for portfolio/risk data. Existing fields continue to work.

For more precise HOLD / REDUCE / EXIT decisions, v2.9 also supports a separate optional GitHub Actions Secret named `ALPHA_HUNTER_POSITION_THESIS_JSON`. This keeps the investment thesis ledger independent from balances and position sizing.

Synthetic schema example:

```json
{
  "positions": [
    {
      "ticker": "SYNTHETIC_EXAMPLE",
      "thesis_driver_ids": ["AI_SERVER_SHIPMENTS"],
      "thesis_status": "ACTIVE"
    }
  ]
}
```

The same `thesis_driver_ids` and `thesis_status` fields may still live directly inside `ALPHA_HUNTER_PORTFOLIO_JSON`; the separate overlay takes precedence when configured.

## Fields

- `thesis_driver_ids`: preferred explicit mapping from the holding to one or more canonical causal drivers. If omitted, the engine falls back to `risk_groups` where a conservative mapping exists.
- `thesis_status`: optional manual state. `INVALIDATED` or `BROKEN` creates `EXIT_THESIS`; otherwise the engine relies on live causal/provenance/reaction gates.
- `cost_basis_twd`: optional portfolio field. Used only in-memory to derive position P/L when `unrealized_pnl_pct` is absent.
- `unrealized_pnl_pct`: optional portfolio field. Enables the private `max_position_loss_pct` policy to create `EXIT_RISK`.

A configured but malformed thesis overlay fails closed for the existing-position engine. An absent overlay is allowed and preserves backward compatibility.

## Decision precedence

1. Explicit private thesis invalidation -> `EXIT_THESIS`.
2. Position loss beyond private risk policy -> `EXIT_RISK`.
3. Source-backed active driver with broken expected transmission and no healthy thesis driver -> `EXIT_THESIS`.
4. Mixed healthy/broken thesis drivers -> `REDUCE_REVIEW`.
5. Healthy source-backed thesis -> `HOLD`.
6. Missing or unresolved thesis evidence -> `REVIEW_THESIS`; missing evidence never invents a sell signal.
7. If portfolio gross exposure is above policy, weakest non-exit positions are nominated first as `REDUCE_RISK` until enough gross exposure is covered.

## Privacy contract

The overlay is read from environment Secrets and merged in-memory by ticker. Per-position actions are computed in-memory. Tickers, balances, weights, cost basis, P/L, and thesis contents are not written to canonical public outputs or logs. The public decision packet contains only aggregate status/counts.
