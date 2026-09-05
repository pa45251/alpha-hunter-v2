# Alpha Hunter v2.5 — Design Review

## Why v2.5 exists

v2.4 solved broad-industry overmatching by adding explicit company-level economic edges. Its remaining weakness was that a fixed theme such as `Memory`, `AI_Server`, or `Shipping` could still be too coarse and could silently assume the market was trading the same driver every day.

v2.5 separates four things that must not be collapsed into one score:

1. **Observed market structure** — what is moving.
2. **Dynamic causal driver** — why it is moving now.
3. **Structural economic exposure** — who would benefit if that driver is truly active.
4. **Taiwan price confirmation** — whether Taiwan is already confirming, not reacting yet, extended, or broken.

## Main weaknesses identified before implementation

### 1. Narrative hallucination / causal overreach
A research agent can invent a plausible story after seeing price. v2.5 makes every fine-grained driver start as `UNRESOLVED_RESEARCH_REQUIRED`. Price is prohibited from activating a driver.

### 2. Fixed taxonomy drift
Even a fine taxonomy can become stale. Structural edges now carry `edge_status`, `provenance_status`, and `review_after`. The graph audit exposes overdue or weakly sourced edges.

### 3. Candidate-funnel confirmation bias
If structural matching only looks at the top-150 momentum candidates, the system can miss true lead-lag beneficiaries before they have moved. v2.5 builds structural matches from the full Taiwan scan, not only the candidate funnel.

### 4. Chasing / post-reaction bias
Taiwan stocks now have an explicit `reaction_state`: `PRE_CONFIRMATION`, `CONFIRMING`, `PERSISTENT`, `PULLBACK`, `EXTENDED`, `BROKEN`, or `UNKNOWN`. The top candidate list reserves space for early/pre-confirmation names and caps extended names.

### 5. Correlated evidence double counting
Global theme strength, Taiwan RS, and Taiwan breadth are all partly price-derived. v2.5 no longer presents a combined transmission score as expected return. `research_priority_score` only triages research workload and its ingredients remain visible.

### 6. Market-time mismatch
Global and Taiwan market dates can differ. Every structural match records `causal_time_state` and the calendar-day difference. A newer US close is not automatically interpreted as stale Taiwan data.

### 7. Multiple simultaneous drivers
A company can have several exposures. v2.5 preserves driver-level rows rather than forcing one permanent theme label.

### 8. Positive/negative exposure
Structural edges include `polarity`. The seed graph is mostly positive exposure today, but the schema can represent negative or offsetting exposures later.

### 9. Research write-back risk
An optional `input/driver_activation.csv` is supported, but it cannot create new structural edges or unknown driver IDs. Stale, unsourced, malformed, or low-quality activations are rejected.

### 10. False precision
Scanner/research layers are not allowed to set `decision_eligible=True`. Final ETF vs stock, position sizing, entry, stop, target and exit remain downstream.

## Remaining weaknesses after v2.5

v2.5 is deliberately not a finished causal model.

- The seed structural graph still needs source-backed provenance for many edges.
- Driver taxonomy can still miss a new market narrative; weekly discovery remains necessary.
- A research agent may classify the wrong driver despite the guardrails.
- Revenue exposure percentages are not yet modeled.
- Customer concentration and supplier substitution are not yet modeled.
- Causal lags differ by industry and are not yet calibrated.
- Research priority weights are heuristic and not optimized.
- No feature/edge should be promoted based on one successful historical example.

These weaknesses are intentional audit targets rather than reasons to hide uncertainty.
