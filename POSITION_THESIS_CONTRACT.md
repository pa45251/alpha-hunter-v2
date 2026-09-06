# Alpha Hunter — Private Position Thesis Contract

This contract is the private bridge from the public market/causal decision system to existing-position HOLD / REDUCE / EXIT decisions.

## Privacy boundary

Private holdings and thesis data MUST be supplied only through GitHub Actions secrets. Do not commit real tickers, weights, balances, cost basis, P/L, or per-position thesis text to this public repository.

The existing-position engine consumes private data in memory. Public artifacts may contain aggregate counts only; they must not contain per-position holdings or actions.

## Secret

Use repository secret `ALPHA_HUNTER_POSITION_THESIS_JSON`.

Schema:

```json
{
  "positions": [
    {
      "ticker": "<same ticker used in ALPHA_HUNTER_PORTFOLIO_JSON>",
      "thesis_driver_ids": ["<canonical driver id>"],
      "thesis_status": "ACTIVE"
    }
  ]
}
```

`ticker` is used only as an in-memory join key. `.TW` / `.TWO` suffixes are normalized.

`thesis_driver_ids` should contain the smallest set of canonical economic drivers that would actually invalidate or sustain the position thesis. Do not list every correlated theme.

`thesis_status` may be `ACTIVE`, `INVALIDATED`, or `BROKEN`. `INVALIDATED` / `BROKEN` is an explicit private hard-invalidation instruction and therefore has priority over market inference.

## Decision semantics

- `HOLD`: at least one mapped thesis driver is ACTIVE_RESEARCH_VALIDATED, SOURCE_BACKED, POSITIVE, and not BROKEN.
- `EXIT_THESIS`: private thesis is explicitly INVALIDATED/BROKEN, or all validated mapped transmission is BROKEN.
- `EXIT_RISK`: the configured maximum position loss is breached.
- `REDUCE_REVIEW`: mapped thesis signals are mixed between healthy and broken.
- `REDUCE_RISK`: portfolio gross exposure exceeds policy and this position is selected by the deterministic risk reduction rule.
- `REVIEW_THESIS`: mapping is missing, the mapped driver is absent from the current decision board, or the thesis is not research validated.

`REVIEW_THESIS` is deliberately fail-closed: missing research must never be converted into an invented HOLD or EXIT.

## Mapping precedence

1. Explicit `ALPHA_HUNTER_POSITION_THESIS_JSON` mapping.
2. Existing private `risk_groups` inference when no explicit mapping exists.
3. Missing mapping -> `REVIEW_THESIS`.

The separate thesis secret is preferred over embedding thesis directly in the portfolio snapshot because holdings/weights change more frequently than the original investment thesis.

## Public readiness signal

`output/action_board.md` exposes only aggregate readiness:

- `COMPLETE_EXPLICIT`: every private position has an explicit thesis mapping.
- `COMPLETE_WITH_INFERENCE`: every position is mapped, but at least one relies on risk-group inference.
- `PARTIAL`: one or more positions have no thesis mapping.
- `NOT_CONFIGURED`: the thesis secret is absent.

No per-position ticker or action is written to the public Action Board.
