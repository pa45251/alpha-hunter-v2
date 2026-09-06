# Alpha Hunter — Existing Position System Thesis Contract

This contract governs the private bridge from the public causal decision system to existing-position HOLD / REDUCE / EXIT decisions.

## Core principle

The user is **not required** to provide the original investment logic.

Existing positions are evaluated from an independently inferred **System Thesis**:

1. exact ticker structural exposure from the full enabled canonical graph (including outside the opportunity filter);
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

- `HOLD`: exact position exposure, complete mapped-driver coverage, and healthy source-backed positive transmission with a known non-broken position reaction.
- `EXIT_THESIS`: complete mapped-driver coverage and no healthy transmission remains; source-backed causal INACTIVE and exact-position price BROKEN remain separate reasons.
- `EXIT_RISK`: configured maximum position-loss policy is breached, including when research is missing.
- `REDUCE_REVIEW`: complete driver coverage contains both healthy and broken/inactive evidence.
- `REDUCE_RISK`: portfolio gross exposure exceeds policy; already nominated exits count toward the required reduction.
- `REVIEW_RESEARCH`: missing/partial driver research, missing exact exposure provenance or price reaction, or risk-group-only inference.

Maintenance research rows carry causal states only. They cannot create structural provenance, polarity, or a price reaction. A peer's price break cannot invalidate the held ticker. Group-only research still runs, but does not authorize HOLD/EXIT until the position's exposure is verified.

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

## Maintenance lane coverage

The maintenance handoff reads the full canonical graph after rechecking canonical hashes/freshness, independently of Top-5 opportunity ranking. The existing 12-driver maintenance workload cap remains; truncation is reported and unresolved drivers cannot be treated as complete coverage. Graph-only positions with no current reaction stay under review. Public artifacts contain aggregate maintenance status only.
