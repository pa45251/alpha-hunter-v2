# Alpha Hunter v2.4

Global-first quantitative market sensor with a Taiwan full-market discovery layer and a company-level Economic Linkage Graph.

## What changed in v2.4

v2.3 proved that full-market Taiwan scanning works, but its Global → Taiwan transmission layer was too coarse because it mapped broad global themes to broad TWSE industry labels. That could incorrectly classify a semiconductor stock as a Memory beneficiary or a cooling stock as a Nuclear Power beneficiary simply because both sat inside broad industry buckets.

v2.4 fixes that.

### 1. Economic Linkage Graph

`config/economic_linkage_graph.csv` defines explicit company-level edges:

- `global_theme`
- `taiwan_code`
- `economic_role`
- `linkage_tier` = DIRECT / STRONG / SECOND_ORDER / SPECULATIVE
- `linkage_confidence`
- `link_mechanism`
- `evidence_required`

Broad-industry fallback is disabled by default.

A transmission hypothesis is promoted only if:

1. the global theme is quantitatively strong enough;
2. the Taiwan stock is already inside the Taiwan quantitative candidate funnel;
3. an explicit company-level linkage edge exists;
4. the edge is not SPECULATIVE;
5. linkage confidence is at least 0.55.

Even then the result remains `HYPOTHESIS_ONLY` until research validates company-specific causality and fundamentals.

### 2. Transmission score v2

The hypothesis score combines:

- 35% global theme strength
- 25% Taiwan candidate strength
- 25% economic linkage score
- 15% Taiwan industry breadth support

A simultaneous negative RS20 and negative acceleration applies a contradiction penalty.

The weights are provisional and intentionally non-optimized.

### 3. Linkage audit

`output/transmission_linkage_audit.csv` records every curated linkage edge and explains why it was or was not promoted:

- `PROMOTED`
- `NO_GLOBAL_CONFIRMATION`
- `NOT_IN_TAIWAN_FUNNEL`
- `LINKAGE_TOO_WEAK`

This makes the transmission layer auditable rather than narrative-driven.

### 4. Canonical data contract

`output/manifest.json` is schema/scanner version 2.4 and includes the Economic Linkage Graph outputs in the required-file contract.

Research agents must read `manifest.json` first.

## Pipeline

```text
Global Sensor
    ↓
Global Theme Strength
    ↓
Economic Linkage Graph  ← explicit Taiwan company / role edges
    ↓
Taiwan Full-Market Quant Funnel
    ↓
Breadth + Linkage Hard Gates
    ↓
HYPOTHESIS_ONLY watchlist
    ↓
Gemini causal / fundamental validation
    ↓
ChatGPT final ETF vs stock / risk / entry / exit audit
```

## Important limitations

The linkage graph is a curated seed, not a complete supply-chain database. A missing edge means `NOT EVALUATED`, not `NO ECONOMIC LINKAGE`.

Company business mixes change. Gemini weekly discovery should propose new or revised edges, but should never silently modify the graph without review.

The scanner does not issue buy/sell recommendations.
