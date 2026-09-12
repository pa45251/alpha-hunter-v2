# Alpha Hunter — Market Opportunity System

Global Evidence → Trend + Underlying Support → Entry + Risk → Action.

Follow evidence-supported trends at a reasonable entry. When trend or support fails, avoid new risk; without edge, WAIT / PASS.

Daily Core runs `daily_scan.py`, `decision_run_v2.py`, then `action_board_summary.py --refresh`. It publishes the complete canonical snapshot, decision and action board atomically. Downstream readers use sealed prices; research may update causal evidence only for that snapshot. Entry and alignment bind to the exact decision lineage.

Personal holdings, costs, quantities, weights and allocation do not affect market judgments. Portfolio maintenance and separate action-publishing workflows have been removed. Legacy portfolio modules remain historical code, outside production; their outputs are retired on refresh.

The action board is `output/action_board.md`. Valid conditional entry plans require causal support, instrument price confirmation and observed liquidity. Price strength cannot create causality. Company alpha must justify stock exposure over ETF exposure. EOD plans never authorize immediate orders; automatic execution remains disabled.

Risk regime retains the existing volatility, trend, breadth and credit heuristic. Treasury evidence uses FRED DGS2 for 2Y and the existing 10Y series. Missing evidence stays UNKNOWN. No personal cash target or rotation recommendation is produced.

Daily Core validates canonical integrity and its own contracts. Full regression tests run in PR CI. Historical outcome evaluation is offline and does not download prices during market publication. Frozen release registries remain historical acceptance records and never authorize live execution.

Scheduled scans: weekdays 06:20, 06:40 and 07:00 Asia/Taipei, with a freshness guard. Manual Daily Scan defaults to a forced scan. Research and decision refresh rebuild the complete action output before publication; computed artifacts are never rebased over another run.

The daily brief ranks up to five opportunities after causal and price assessment. Its only actions are BUY, EARLY BUY, WAIT and PASS. EARLY BUY means an advisory starter of 35% of a planned position: a measured company fundamental, defensible transmission, independent same-driver international evidence when applicable, compatible regime, and a nonextended entry with at least 2R to an observed resistance or disclosed base-height scenario. Further operating or breakout confirmation can promote BUY; neither action enables brokerage execution.

Unmapped companies enter the existing research handoff with official MOPS revenue observations and company WHY searches. A supported local mechanism may remain provisional without a taxonomy edge. Missing company evidence remains unresolved, with a specific research reason. Broad equity weakness alone does not veto a company or sector thesis; systemic stress and relevant adverse rates do.

`output/opportunity_advisory.json` preserves every assessed candidate, source evidence and policy version for prospective evaluation. Reproduce the six-case point-in-time audit with `python historical_early_audit.py`; see `docs/audit/early_detection_audit.md`. The historical archive does not establish actionable early-entry performance, and heuristic reward/risk is not calibrated expected value.
