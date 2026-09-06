# Alpha Hunter — Existing Position System Thesis Contract

This contract governs the private bridge from the public causal decision system to existing-position HOLD / REDUCE / EXIT decisions.

## Core principle

The user is **not required** to provide the original investment logic.

Existing positions are evaluated from an independently inferred **System Thesis**:

1. exact ticker structural exposure already present in the current decision board;
2. otherwise private risk-group to canonical-driver mapping;
3. otherwise `SYSTEM_MAPPING_MISSING` -> `REVIEW_RESEARCH`.

The engine therefore asks: **if the system did not know why the position was bought, does current causal evidence still justify allocating capital to this exposure?**

Price cannot create causality, and the user's stated purchase reason cannot create causality either.

## Optional user thesis challenger

`ALPHA_HUNTER_POSITION_THESIS_JSON` is optional. When present, it is challenger metadata only. It may expose a disagreement between the user's thesis and the system thesis, but it cannot force HOLD or EXIT.

Schema:

```json
{
  "positions": [
    {
      "ticker": "<same private ticker>",
      "thesis_driver_ids": ["<canonical driver id>"],
      "thesis_status": "ACTIVE|INVALIDATED|BROKEN"
    }
  ]
}
```

The public Action Board reports only an aggregate disagreement count. It never writes the ticker-level user thesis.

## System decision semantics

- `HOLD`: at least one system-mapped driver is `ACTIVE_RESEARCH_VALIDATED`, `SOURCE_BACKED`, `POSITIVE`, and not `BROKEN`.
- `EXIT_THESIS`: validated system transmission is broken and no healthy mapped transmission remains.
- `EXIT_RISK`: configured maximum position-loss policy is breached.
- `REDUCE_REVIEW`: system-mapped drivers contain both healthy and broken validated evidence.
- `REDUCE_RISK`: portfolio gross exposure exceeds policy and the deterministic risk-reduction rule selects the position.
- `REVIEW_RESEARCH`: system exposure mapping is missing, mapped drivers are absent from the current decision board, or current evidence is not research validated.

Missing research is fail-closed: it must never become an invented HOLD or EXIT.

## Privacy boundary

Private holdings, tickers, weights, balances, cost basis, P/L, per-position actions, and optional user thesis stay in GitHub Actions secrets / process memory only. They must not be committed to this public repository.

Public artifacts may contain aggregate counts such as action counts, system-mapping counts, and user/system disagreement count.

## Public readiness signal

`output/action_board.md` reports system mapping readiness only:

- `COMPLETE_EXACT_EXPOSURE`: every private position maps by exact ticker to current structural exposure.
- `COMPLETE_WITH_SYSTEM_INFERENCE`: all positions map, with at least one using risk-group inference.
- `PARTIAL`: at least one position still lacks a system exposure map.
- `BLOCKED_PRIVATE_INPUTS`: private risk/portfolio input validation failed.

The optional user thesis secret is never a prerequisite for system readiness.
