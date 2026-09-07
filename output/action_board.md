# Alpha Hunter — Action Board

<!-- ENTRY_V2_START -->
## Alpha Hunter V2 — Global Alignment + Exact Entry
- Rule: alignment/edge scores are relative evidence ranks, **not win probabilities**.
- Rule: EOD output never claims BUY_NOW without a fresh executable quote inside the buy zone.

### A. Strongest Global-Aligned Trend
- **6669.TW 緯穎** — alignment `0.8179` / global `AI_Server` / reaction `PERSISTENT` / action `HOLD_DONT_CHASE`

### B. Best Fresh Entry
- **2376.TW 技嘉** — `WAIT_BREAKOUT` / `WAITING_FOR_TRIGGER`
- Entry style: `FRESH_BREAKOUT`
- Trigger: **405.00**
- Buy zone: **405.00 – 410.00**
- Invalidation: **332.50**
- Why now: 
- Why not now: CLOSE_BELOW_FROZEN_BREAKOUT_TRIGGER

### C. Best Pullback Entry
- **6446.TW 藥華藥** — `PREPARE` / `WATCHLIST`
- Entry style: `PULLBACK_RECOVERY`
- Trigger: **—**
- Buy zone: **— – —**
- Invalidation: **—**
- Why now: 
- Why not now: CAUSAL_DRIVER_NOT_ACTIVE;COMPANY_EDGE_NOT_SOURCE_BACKED;GLOBAL_ALIGNMENT_NOT_ELIGIBLE

### D. Best Continuation Entry
- **3231.TW 緯創** — `WAIT_BREAKOUT` / `CONTINUATION_BASE_WAITING_FOR_TRIGGER`
- Entry style: `CONTINUATION_BASE`
- Trigger: **208.00**
- Buy zone: **208.00 – 211.50**
- Invalidation: **170.50**
- Why now: 
- Why not now: VALID_CONTINUATION_BASE_EXISTS_BUT_BREAKOUT_NOT_CONFIRMED

### E. Rotation / Exact Execution
- Source: **標的D** → Destination: **4967.TW 十銓**
- State: `PREPARE_ROTATION_STRONG`; trim now **0%**
- Trigger: **294.50**; Buy zone **294.50 – 299.00**; Invalidation **245.00**
- Required before rotation: `ENTRY_PLAN_TRIGGER_AND_LIVE_QUOTE`

V2 is shadow/advisory only. Exact levels are structure-derived conditional plans, not brokerage orders.
<!-- ENTRY_V2_END -->

## 0. Portfolio allocation / cash regime
- Global risk regime: `RISK_ON` / score `11`
- Target cash / dry-powder buffer: **0.0%**
- For leveraged portfolios, a higher buffer should generally be implemented by reducing gross exposure before accumulating idle cash.
- Best new opportunity: **4967.TW 十銓** — `BUY_BIAS_STOCK` / edge `0.9905` / reaction `PRE_CONFIRMATION`

| Source alias | Destination | Rotation state | Edge spread | Trim now | Trim on trigger | Entry trigger | Redeploy on trigger | Buffer on trigger |
|---|---|---|---:|---:|---:|---|---:|---:|
| 標的D | 4967.TW 十銓 | PREPARE_ROTATION_STRONG | 0.5779 | 0% | 50% | DESTINATION_REACTION_CONFIRMING | 100% | 0% |

PREPARE_ROTATION means the edge is strong enough to nominate the switch, but the destination has not reached the required entry-confirmation state; current trim remains zero.
Rotation and cash outputs are CIO advisories only. They do not authorize brokerage orders.

## 0.5 Global Alignment Leaderboard
- Purpose: find Taiwan stocks whose own trend quality is supported by the corresponding international market and an ACTIVE causal driver.
- Alignment score is a relative opportunity/evidence score, **not a calibrated win probability**.
- Strongest aligned trend now: **6669.TW 緯穎** — score `0.8138` / `HOLD_DONT_CHASE` / global `AI_Server` / reaction `PERSISTENT`
- Best fresh aligned setup now: **2376.TW 技嘉** — score `0.663` / `PREPARE` / reaction `PRE_CONFIRMATION`

| Rank | Taiwan stock | Global theme | Alignment | Global | Taiwan | Breadth | Keynes | State |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | 6669.TW 緯穎 | AI_Server | 0.8138 | 0.8765 | 0.8418 | 0.55 | 0.8727 | HOLD_DONT_CHASE |
| 2 | 3231.TW 緯創 | AI_Server | 0.7435 | 0.8765 | 0.7273 | 0.55 | 0.6 | HOLD_DONT_CHASE |
| 3 | 2376.TW 技嘉 | AI_Server | 0.663 | 0.8765 | 0.56 | 0.55 | 0.3636 | PREPARE |
| 4 | 4967.TW 十銓 | Memory | 0.589 | 0.7124 | 0.4455 | 0.6167 | 0.2909 | PREPARE |

Global Alignment is advisory only; BROKEN/EXTENDED names cannot become fresh entries through this leaderboard.

- Run: `20260907T083423+0800-0e24be27`
- Causal source: `LEGACY_MANUAL_FALLBACK`
- Same snapshot: `False`
- Active opportunity drivers: AI_SERVER_RACK_BUILD, AI_SERVER_SHIPMENTS, NAND_STORAGE_CYCLE
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
| 1 | 4967.TW | 十銓 | BUY_BIAS_STOCK | MEDIUM | NAND_STORAGE_CYCLE | Active driver, source-backed company edge, and a non-extended reaction state support a positive stock bias. |
| 2 | 2317.TW | 鴻海 | BUY_BIAS_STOCK | MEDIUM | AI_SERVER_SHIPMENTS | Active driver, source-backed company edge, and a non-extended reaction state support a positive stock bias. |
| 3 | 2376.TW | 技嘉 | BUY_BIAS_STOCK | MEDIUM | AI_SERVER_RACK_BUILD | Active driver, source-backed company edge, and a non-extended reaction state support a positive stock bias. |
| 4 | QQQ | Mapped ETF | PREFER_ETF | MEDIUM | AI_SERVER_SHIPMENTS | Global driver is active; ETF is the cleaner exposure because stock alpha is not clearly superior or is not source-backed. |
| 5 | QQQ | Mapped ETF | PREFER_ETF | MEDIUM | AI_SERVER_RACK_BUILD | Global driver is active; ETF is the cleaner exposure because stock alpha is not clearly superior or is not source-backed. |
| 6 | 6669.TW | 緯穎 | HOLD_BIAS | MEDIUM | AI_SERVER_SHIPMENTS | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 7 | 3231.TW | 緯創 | HOLD_BIAS | MEDIUM | AI_SERVER_SHIPMENTS | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 8 | 2615.TW | 萬海 | RESEARCH_FIRST | INSUFFICIENT | CONTAINER_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 9 | 2603.TW | 長榮 | RESEARCH_FIRST | INSUFFICIENT | CONTAINER_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 10 | 2609.TW | 陽明 | RESEARCH_FIRST | INSUFFICIENT | CONTAINER_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 11 | 2606.TW | 裕民 | RESEARCH_FIRST | INSUFFICIENT | DRY_BULK_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 12 | 2637.TW | 慧洋-KY | RESEARCH_FIRST | INSUFFICIENT | DRY_BULK_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 13 | 2605.TW | 新興 | RESEARCH_FIRST | INSUFFICIENT | DRY_BULK_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 14 | 2617.TW | 台航 | RESEARCH_FIRST | INSUFFICIENT | DRY_BULK_FREIGHT | The causal driver is not validated active; price strength cannot substitute for causality. |
| 15 | 3006.TW | 晶豪科 | RESEARCH_FIRST | INSUFFICIENT | MEMORY_IC_CYCLE | The causal driver is not validated active; price strength cannot substitute for causality. |

Advisory counts: `{"AVOID": 3, "BUY_BIAS_STOCK": 3, "HOLD_BIAS": 2, "PREFER_ETF": 2, "RESEARCH_FIRST": 44}`
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
| 4967.TW | 十銓 | NAND_STORAGE_CYCLE | PRE_CONFIRMATION | GATE_5_ENTRY | WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER |
| 2317.TW | 鴻海 | AI_SERVER_SHIPMENTS | PRE_CONFIRMATION | GATE_5_ENTRY | WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER |
| 2376.TW | 技嘉 | AI_SERVER_RACK_BUILD | PRE_CONFIRMATION | GATE_5_ENTRY | WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER |
| 6669.TW | 緯穎 | AI_SERVER_SHIPMENTS | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 3231.TW | 緯創 | AI_SERVER_SHIPMENTS | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |

## 5. Main execution blockers
- `DRIVER_NOT_ACTIVE_RESEARCH_VALIDATED`: 44
- `EDGE_PROVENANCE_NOT_SOURCE_BACKED`: 40
- `WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER`: 3
- `INFORMATION_MAY_BE_PRICED`: 2

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
- System mapping counts: `{"SYSTEM_MAPPING_MISSING": 2, "SYSTEM_RISK_GROUP": 3}`
- Portfolio-maintenance research lane: `NOT_AVAILABLE`
- Maintenance drivers researched/targeted: `0/0`
- Maintenance driver states (aggregate only): `{}`
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
