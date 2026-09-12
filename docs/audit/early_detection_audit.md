# Historical early detection audit

Source main: `01b7a9005df409c5ceec7c85cafabeab1292c36a`. Rules fixed before audit; no six-stock tuning.

Commit availability controls decision time. Missing evidence stays missing; later news and prices never establish past causality.

| Stock | First archived nomination (UTC) | Price session | Reaction | EARLY BUY / ADD |
|---|---|---|---|---|
| 6179 亞通 | 2026-09-09T00:25:27Z | 2026-09-08 | PERSISTENT | Not established from archived company evidence |
| 8227 巨有科技 | 2026-09-09T00:25:27Z | 2026-09-08 | CONFIRMING | Not established from archived company evidence |
| 6538 倉和 | 2026-09-05T22:43:12Z | 2026-09-04 | UNRECORDED | Not established from archived company evidence |
| 3055 蔚華科 | 2026-09-08T00:08:58Z | 2026-09-07 | CONFIRMING | Not established from archived company evidence |
| 3624 光頡 | 2026-09-08T00:08:58Z | 2026-09-07 | CONFIRMING | Not established from archived company evidence |
| 2305 全友 | 2026-09-05T22:43:12Z | 2026-09-04 | UNRECORDED | Not established from archived company evidence |

No defensible claim of 1–3-session early tradability can be made from these archives. Scanner nomination and executable economic evidence are different events.
Per-session metrics, extension state, missing-evidence flags, commit IDs and 1/3/5/10-session outcomes are in early_detection_observations.csv.
Outcomes unavailable at the latest snapshot remain blank (right-censored). Indicative raw-price outcomes may include corporate-action effects and exclude costs, slippage and limit-up fill risk.
Prospective validation: retain immutable Git publication time, snapshot, company evidence, policy version and all candidate actions. Evaluate future unseen candidates after 1/3/5/10 sessions; do not tune rules to these six winners. Include all nominations, rejected names, missed names and a holdout period. No calibrated expected value or success rate is claimed.
