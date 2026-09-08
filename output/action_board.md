# Alpha Hunter — Action Board

<!-- ENTRY_V2_START -->
## Alpha Hunter V2 — Global Alignment + Exact Entry
- Rule: alignment/edge scores are relative evidence ranks, **not win probabilities**.
- Rule: EOD output never claims BUY_NOW without a fresh executable quote inside the buy zone.

### A. Strongest Global-Aligned Trend
- **2617.TW 台航** — alignment `0.9067` / global `Shipping` / reaction `PERSISTENT` / action `HOLD_DONT_CHASE`

### B. Best Fresh Entry
- **8996.TW 高力** — `AVOID` / `WATCHLIST`
- Entry style: `FRESH_BREAKOUT`
- Trigger: **—**
- Buy zone: **— – —**
- Invalidation: **—**
- Why now: 
- Why not now: CAUSAL_DRIVER_NOT_ACTIVE;COMPANY_EDGE_NOT_SOURCE_BACKED;GLOBAL_ALIGNMENT_NOT_ELIGIBLE

### C. Best Pullback Entry
- **2603.TW 長榮** — `PREPARE` / `WATCHLIST`
- Entry style: `PULLBACK_RECOVERY`
- Trigger: **—**
- Buy zone: **— – —**
- Invalidation: **—**
- Why now: 
- Why not now: CAUSAL_DRIVER_NOT_ACTIVE;GLOBAL_ALIGNMENT_NOT_ELIGIBLE

### D. Best Continuation Entry
- **2617.TW 台航** — `WAIT_BREAKOUT` / `NO_VALID_CONTINUATION_BASE`
- Entry style: `CONTINUATION_BASE`
- Trigger: **—**
- Buy zone: **— – —**
- Invalidation: **—**
- Why now: 
- Why not now: CONTINUATION_BASE_QUALITY_NOT_COMPLETE

### E. Rotation / Exact Execution
- **NO ROTATION NOW** — no destination simultaneously passes the canonical V2 opportunity + entry gate.

V2 is shadow/advisory only. Exact levels are structure-derived conditional plans, not brokerage orders.
<!-- ENTRY_V2_END -->

## 0. Portfolio allocation / cash regime
- Global risk regime: `RISK_ON` / score `16`
- Target cash / dry-powder buffer: **0.0%**
- For leveraged portfolios, a higher buffer should generally be implemented by reducing gross exposure before accumulating idle cash.
- Best new opportunity: **2606.TW 裕民** — `HOLD_BIAS` / edge `0.6363` / reaction `PERSISTENT`

| Source alias | Destination | Rotation state | Edge spread | Trim now | Trim on trigger | Entry trigger | Redeploy on trigger | Buffer on trigger |
|---|---|---|---:|---:|---:|---|---:|---:|
| 標的D | 2606.TW 裕民 | WAIT_BETTER_ENTRY | 0.2237 | 0% | 30% | DESTINATION_ENTRY_STATE_NOT_CONFIRMING | 100% | 0% |

PREPARE_ROTATION means the edge is strong enough to nominate the switch, but the destination has not reached the required entry-confirmation state; current trim remains zero.
Rotation and cash outputs are CIO advisories only. They do not authorize brokerage orders.

## 0.5 Global Alignment Leaderboard
- Purpose: find Taiwan stocks whose own trend quality is supported by the corresponding international market and an ACTIVE causal driver.
- Alignment score is a relative opportunity/evidence score, **not a calibrated win probability**.
- Strongest aligned trend now: **2617.TW 台航** — score `0.9017` / `HOLD_DONT_CHASE` / global `Shipping` / reaction `PERSISTENT`
- Best fresh aligned setup now: **NONE** — current alignment leaders are already persistent or no early/confirming setup passes every hard gate.

| Rank | Taiwan stock | Global theme | Alignment | Global | Taiwan | Breadth | Keynes | State |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | 2617.TW 台航 | Shipping | 0.9017 | 0.9656 | 0.7127 | 1.0 | 0.9091 | HOLD_DONT_CHASE |
| 2 | 2637.TW 慧洋-KY | Shipping | 0.8895 | 0.9656 | 0.7491 | 1.0 | 0.7636 | HOLD_DONT_CHASE |
| 3 | 2606.TW 裕民 | Shipping | 0.8672 | 0.9656 | 0.6382 | 1.0 | 0.8 | HOLD_DONT_CHASE |
| 4 | 2605.TW 新興 | Shipping | 0.8572 | 0.9656 | 0.6327 | 1.0 | 0.7455 | HOLD_DONT_CHASE |

Global Alignment is advisory only; BROKEN/EXTENDED names cannot become fresh entries through this leaderboard.

- Run: `20260908T080641+0800-3df4fce0`
- Causal source: `V3_AUTONOMOUS_RESEARCH`
- Same snapshot: `True`
- Active opportunity drivers: DRY_BULK_FREIGHT
- Private risk inputs valid: `True`
- Auto order execution: `False`

## Deployment status
- SHADOW ONLY: all BUY/SELL/HOLD signals are research outputs; no live order is authorized.
- Frozen strategy: `ALPHA_HUNTER_SHADOW_V1`
- Freeze integrity: `True`
- CIO Advisory is deliberately separate from execution permission: it must express the best directional decision under uncertainty, while the frozen execution lane may still block an order.
- Existing-position identities are published only as user-defined aliases; ticker-to-alias mapping remains private.
- First review: 2026-11-29. Review does not automatically enable trading.
- Existing shadow statistics are gross signal outcomes, not validated strategy performance.

## 1. CIO advisory — new opportunities, directional decision not an order

| Rank | Exposure | Name | Advisory | Confidence | Driver | Why |
|---:|---|---|---|---|---|---|
| 1 | 2606.TW | 裕民 | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 2 | 2637.TW | 慧洋-KY | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 3 | 2605.TW | 新興 | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 4 | 2617.TW | 台航 | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 5 | 2609.TW | 陽明 | RESEARCH_FIRST | INSUFFICIENT | CONTAINER_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 6 | 2615.TW | 萬海 | RESEARCH_FIRST | INSUFFICIENT | CONTAINER_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 7 | 2408.TW | 南亞科 | RESEARCH_FIRST | INSUFFICIENT | DRAM_PRICING | The causal driver is not validated active; price strength cannot substitute for causality. |
| 8 | 6669.TW | 緯穎 | RESEARCH_FIRST | INSUFFICIENT | AI_SERVER_SHIPMENTS | The causal driver is not validated active; price strength cannot substitute for causality. |
| 9 | 2344.TW | 華邦電 | RESEARCH_FIRST | INSUFFICIENT | SPECIALTY_MEMORY_PRICING | The causal driver is not validated active; price strength cannot substitute for causality. |
| 10 | 3231.TW | 緯創 | RESEARCH_FIRST | INSUFFICIENT | AI_SERVER_SHIPMENTS | The causal driver is not validated active; price strength cannot substitute for causality. |
| 11 | 3006.TW | 晶豪科 | RESEARCH_FIRST | INSUFFICIENT | MEMORY_IC_CYCLE | The causal driver is not validated active; price strength cannot substitute for causality. |
| 12 | 2882.TW | 國泰金 | RESEARCH_FIRST | INSUFFICIENT | FINANCIALS_RATE_CREDIT_CYCLE | The causal driver is not validated active; price strength cannot substitute for causality. |
| 13 | 2881.TW | 富邦金 | RESEARCH_FIRST | INSUFFICIENT | FINANCIALS_RATE_CREDIT_CYCLE | The causal driver is not validated active; price strength cannot substitute for causality. |
| 14 | 2303.TW | 聯電 | RESEARCH_FIRST | INSUFFICIENT | MATURE_NODE_FOUNDRY_UTILIZATION | The causal driver is not validated active; price strength cannot substitute for causality. |
| 15 | 2603.TW | 長榮 | RESEARCH_FIRST | INSUFFICIENT | CONTAINER_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |

Advisory counts: `{"HOLD_BIAS": 4, "RESEARCH_FIRST": 51}`
The advisory lane may say BUY_BIAS/PREFER_ETF/WAIT_PULLBACK/AVOID even when execution remains blocked. That is intentional.

## 2. Existing-position CIO advisory — alias only

| Alias | CIO bias | Confidence | State | Lane | Strict lane | Why |
|---|---|---|---|---|---|---|
| 零碎部位 | IGNORE_RESIDUAL | HIGH | DE_MINIMIS | RESIDUAL | REVIEW_RESEARCH | POSITION_BELOW_DE_MINIMIS_WEIGHT |
| 標的A | HOLD_BIAS | HIGH | POSITIVE | ETF_THEME | REVIEW_RESEARCH | ETF_THEME_POSITIVE_MARKET_BREADTH |
| 標的B | HOLD_BIAS | MEDIUM | STRONG | ETF_THEME | REVIEW_RESEARCH | ETF_THEME_STRONG_MARKET_BREADTH |
| 標的C | HOLD_BIAS | HIGH | STRONG | ETF_THEME | REVIEW_RESEARCH | ETF_THEME_STRONG_MARKET_BREADTH |
| 標的D | REVIEW_HOLD | MEDIUM | MIXED | STOCK_THEME_PROXY | REVIEW_RESEARCH | STOCK_THEME_PROXY_MIXED_MARKET_BREADTH_COMPANY_TRANSMISSION_NOT_EXACT |

ETF holdings use global theme breadth; stocks use a theme proxy until company-level transmission is exact. This is advisory, not execution authorization.

## 3. Execution-lane research signals (not executable orders)

No validated BUY/ADD/REDUCE/EXIT/HOLD action is currently emitted by the frozen execution lane.

## 4. Closest to execution action

| Ticker | Name | Driver | Reaction | Stage | Blocker |
|---|---|---|---|---|---|
| 2606.TW | 裕民 | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2637.TW | 慧洋-KY | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2605.TW | 新興 | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2617.TW | 台航 | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |

## 5. Main execution blockers
- `DRIVER_NOT_ACTIVE_RESEARCH_VALIDATED`: 51
- `EDGE_PROVENANCE_NOT_SOURCE_BACKED`: 40
- `INFORMATION_MAY_BE_PRICED`: 4

## 6. Existing-position strict layer — privacy-safe alias view

| Alias | Action | Reason | Thesis mapping |
|---|---|---|---|
| 零碎部位 | REVIEW_RESEARCH | SYSTEM_EXPOSURE_MAPPING_MISSING | SYSTEM_MAPPING_MISSING |
| 標的A | REVIEW_RESEARCH | SYSTEM_EXPOSURE_MAPPING_MISSING | SYSTEM_MAPPING_MISSING |
| 標的B | REVIEW_RESEARCH | SYSTEM_GROUP_RESEARCH_REQUIRES_POSITION_EXPOSURE_VALIDATION | SYSTEM_RISK_GROUP |
| 標的C | REVIEW_RESEARCH | SYSTEM_GROUP_RESEARCH_REQUIRES_POSITION_EXPOSURE_VALIDATION | SYSTEM_RISK_GROUP |
| 標的D | REVIEW_RESEARCH | SYSTEM_GROUP_RESEARCH_REQUIRES_POSITION_EXPOSURE_VALIDATION | SYSTEM_RISK_GROUP |

- Inputs valid: `True`
- System thesis primary: `True`
- System mapping readiness: `PARTIAL`
- Position count: `5`
- Position action counts: `{"REVIEW_RESEARCH": 5}`
- System mapping counts: `{"SYSTEM_MAPPING_MISSING": 2, "SYSTEM_RISK_GROUP": 2, "SYSTEM_TICKER_EXPOSURE": 1}`
- Portfolio-maintenance research lane: `PASS`
- Maintenance drivers researched/targeted: `4/4`
- Maintenance driver states (aggregate only): `{"UNKNOWN": 4}`
- Maintenance targets truncated by safety cap: `0`
- Optional user-thesis overlay: `NOT_CONFIGURED`
- User/system disagreement count: `0`
- Public alias outputs contain no ticker, company name, market value, weight, cost, P/L, cash or financing data.
- The ticker-to-alias map remains inside GitHub Secrets/private runtime and is never committed.

## 7. Interpretation
- Opportunity discovery, existing-position advisory, execution permission, and portfolio maintenance are separate layers.
- Existing-position CIO advisory is forced to express a directional bias from market evidence even when the frozen strict lane remains REVIEW_RESEARCH.
- ETF holdings are judged by global theme breadth; single stocks require more company-specific transmission before strict HOLD/EXIT can be validated.
- Weak or unverified Taiwan stock alpha should fall back to a mapped ETF or cash instead of forcing endless research.
- Existing-position strict HOLD/REDUCE/EXIT is driven by system-inferred economic exposure, not by the user's stated purchase reason.
- `SYSTEM_TICKER_EXPOSURE` is preferred; risk-group mapping is a fallback. Missing system mapping fails closed to `REVIEW_RESEARCH`.
- Alias-level existing-position actions may be public, but the underlying instrument mapping stays private.
- Automatic brokerage execution remains disabled.
