# Alpha Hunter — Action Board

## 0. Portfolio allocation / cash regime
- Global risk regime: `RISK_ON` / score `11`
- Target cash / dry-powder buffer: **0.0%**
- For leveraged portfolios, a higher buffer should generally be implemented by reducing gross exposure before accumulating idle cash.
- Best new opportunity: **2317.TW 鴻海** — `BUY_BIAS_STOCK` / edge `0.9888` / reaction `PRE_CONFIRMATION`

| Source alias | Destination | Rotation state | Edge spread | Trim now | Trim on trigger | Entry trigger | Redeploy on trigger | Buffer on trigger |
|---|---|---|---:|---:|---:|---|---:|---:|
| 標的D | 2317.TW 鴻海 | PREPARE_ROTATION_STRONG | 0.5762 | 0% | 50% | DESTINATION_REACTION_CONFIRMING | 100% | 0% |

PREPARE_ROTATION means the edge is strong enough to nominate the switch, but the destination has not reached the required entry-confirmation state; current trim remains zero.
Rotation and cash outputs are CIO advisories only. They do not authorize brokerage orders.

## 0.5 Global Alignment Leaderboard
- Purpose: find Taiwan stocks whose own trend quality is supported by the corresponding international market and an ACTIVE causal driver.
- Alignment score is a relative opportunity/evidence score, **not a calibrated win probability**.
- Highest alignment now: **2606.TW 裕民** — score `0.9027` / `HOLD_DONT_CHASE` / global `Shipping` / reaction `PERSISTENT`

| Rank | Taiwan stock | Global theme | Alignment | Global | Taiwan | Breadth | Keynes | State |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | 2606.TW 裕民 | Shipping | 0.9027 | 0.9656 | 0.7909 | 1.0 | 0.7818 | HOLD_DONT_CHASE |
| 2 | 2615.TW 萬海 | Shipping | 0.9002 | 0.9656 | 0.68 | 1.0 | 0.9455 | HOLD_DONT_CHASE |
| 3 | 2637.TW 慧洋-KY | Shipping | 0.8949 | 0.9656 | 0.7927 | 1.0 | 0.7273 | HOLD_DONT_CHASE |
| 4 | 2617.TW 台航 | Shipping | 0.8922 | 0.9656 | 0.7073 | 1.0 | 0.8545 | HOLD_DONT_CHASE |
| 5 | 2609.TW 陽明 | Shipping | 0.8666 | 0.9656 | 0.6873 | 1.0 | 0.7091 | HOLD_DONT_CHASE |
| 6 | 2603.TW 長榮 | Shipping | 0.8489 | 0.9656 | 0.5836 | 1.0 | 0.7636 | HOLD_DONT_CHASE |
| 7 | 2605.TW 新興 | Shipping | 0.8408 | 0.9656 | 0.6327 | 1.0 | 0.6364 | HOLD_DONT_CHASE |
| 8 | 6669.TW 緯穎 | AI_Server | 0.8138 | 0.8765 | 0.8418 | 0.55 | 0.8727 | HOLD_DONT_CHASE |
| 9 | 3231.TW 緯創 | AI_Server | 0.7435 | 0.8765 | 0.7273 | 0.55 | 0.6 | HOLD_DONT_CHASE |

Global Alignment is advisory only; BROKEN/EXTENDED names cannot become fresh entries through this leaderboard.

- Run: `20260906T130002+0800-dd80dd63`
- Causal source: `CHATGPT_CHALLENGER_ADJUDICATION`
- Same snapshot: `True`
- Active opportunity drivers: AI_SERVER_SHIPMENTS, CONTAINER_FREIGHT, DRY_BULK_FREIGHT, POWER_ELECTRONICS_CAPEX
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
| 1 | 2317.TW | 鴻海 | BUY_BIAS_STOCK | MEDIUM | AI_SERVER_SHIPMENTS | Active driver, source-backed company edge, and a non-extended reaction state support a positive stock bias. |
| 2 | BOAT | Mapped ETF | PREFER_ETF | HIGH | CONTAINER_FREIGHT | Global driver is active; ETF is the cleaner exposure because stock alpha is not clearly superior or is not source-backed. |
| 3 | QQQ | Mapped ETF | PREFER_ETF | MEDIUM | AI_SERVER_SHIPMENTS | Global driver is active; ETF is the cleaner exposure because stock alpha is not clearly superior or is not source-backed. |
| 4 | XLI | Mapped ETF | PREFER_ETF | MEDIUM | POWER_ELECTRONICS_CAPEX | The global driver is active but the stock case is not sufficiently verified; prefer the mapped ETF exposure. |
| 5 | 2606.TW | 裕民 | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 6 | 2637.TW | 慧洋-KY | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 7 | 2605.TW | 新興 | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 8 | 2617.TW | 台航 | HOLD_BIAS | MEDIUM | DRY_BULK_FREIGHT | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 9 | 6669.TW | 緯穎 | HOLD_BIAS | MEDIUM | AI_SERVER_SHIPMENTS | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 10 | 3231.TW | 緯創 | HOLD_BIAS | MEDIUM | AI_SERVER_SHIPMENTS | The thesis is confirmed, but more information may already be priced; prefer hold or a better entry over chasing. |
| 11 | 3006.TW | 晶豪科 | RESEARCH_FIRST | INSUFFICIENT | MEMORY_IC_CYCLE | The causal driver is not validated active; price strength cannot substitute for causality. |
| 12 | 2882.TW | 國泰金 | RESEARCH_FIRST | INSUFFICIENT | FINANCIALS_RATE_CREDIT_CYCLE | The causal driver is not validated active; price strength cannot substitute for causality. |
| 13 | 2881.TW | 富邦金 | RESEARCH_FIRST | INSUFFICIENT | FINANCIALS_RATE_CREDIT_CYCLE | The causal driver is not validated active; price strength cannot substitute for causality. |
| 14 | 2408.TW | 南亞科 | RESEARCH_FIRST | INSUFFICIENT | DRAM_PRICING | The causal driver is not validated active; price strength cannot substitute for causality. |
| 15 | 3017.TW | 奇鋐 | RESEARCH_FIRST | INSUFFICIENT | AI_SERVER_THERMAL_DENSITY | The causal driver is not validated active; price strength cannot substitute for causality. |

Advisory counts: `{"BUY_BIAS_STOCK": 1, "HOLD_BIAS": 6, "PREFER_ETF": 3, "RESEARCH_FIRST": 40}`
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
| 2317.TW | 鴻海 | AI_SERVER_SHIPMENTS | PRE_CONFIRMATION | GATE_5_ENTRY | WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER |
| 2615.TW | 萬海 | CONTAINER_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2603.TW | 長榮 | CONTAINER_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2609.TW | 陽明 | CONTAINER_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2606.TW | 裕民 | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2637.TW | 慧洋-KY | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2605.TW | 新興 | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 2617.TW | 台航 | DRY_BULK_FREIGHT | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 6669.TW | 緯穎 | AI_SERVER_SHIPMENTS | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |
| 3231.TW | 緯創 | AI_SERVER_SHIPMENTS | PERSISTENT | GATE_4_REACTION | INFORMATION_MAY_BE_PRICED |

## 5. Main execution blockers
- `DRIVER_NOT_ACTIVE_RESEARCH_VALIDATED`: 40
- `EDGE_PROVENANCE_NOT_SOURCE_BACKED`: 40
- `INFORMATION_MAY_BE_PRICED`: 9
- `REACTION_STATE_NOT_ENTRY_READY`: 3
- `WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER`: 1

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
