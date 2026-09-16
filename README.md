# Alpha Hunter — Scanner + Manual Research System

Alpha Hunter now has one production responsibility: **find and structure market opportunities cheaply and reproducibly**. It scans global markets and the full Taiwan market, ranks price/trend candidates, preserves causal/structural context, and prepares a manual research handoff.

**It does not autonomously choose the final stock and it does not require paid AI credits.** Final BUY / EARLY BUY / WAIT / PASS research is performed manually after the scan, currently by bringing the shortlist to ChatGPT for company-by-company deep research.

## Production flow

```text
Global market scan + Taiwan full-market scan
        ↓
Trend / RS / acceleration / liquidity candidate funnel
        ↓
Deterministic industry + international-peer context
        ↓
output/manual_research_queue.csv
        ↓
Manual ChatGPT deep research
        ↓
Human investment decision
```

The weekday scheduled scan remains 06:20, 06:40 and 07:00 Asia/Taipei with the existing freshness guard. `daily_scan.py` remains the canonical scanner. After it finishes, `manual_research_queue.py` adds the manual research context. Neither step calls Copilot, OpenAI API, Gemini, or another paid model API.

The previous Copilot autonomous-research workflow, OpenAI frontier-research workflow, and AI-dependent decision-refresh workflow are retired from production. Historical Python research/decision modules may remain in the repository for audit or possible future reuse, but no scheduled workflow invokes them and they are not authoritative outputs in manual-research mode.

## Industry ontology and international peers

Official TWSE/TPEX industries are retained because they are useful for broad market breadth, but they are too coarse for causal investment research. For example, `半導體業`, `電子零組件業`, and `光電業` contain businesses with very different economic drivers.

`config/manual_industry_map.csv` therefore adds an auditable investment sub-industry layer for important Taiwan supply chains. Current priority coverage includes:

- Mobile / automotive / XR optics
- Diode and discrete semiconductors
- Power MOSFET / power semiconductor
- PCB and package substrates
- High-speed / low-loss CCL
- High-speed connectors and cable interconnect
- MLCC
- Non-MLCC capacitors

`config/manual_global_peers.csv` assigns explicit international peer baskets to each driver. Examples include Sunny Optical / LG Innotek for optics, Diodes / Vishay / onsemi / Infineon / STMicroelectronics for discrete power, TTM / IBIDEN / Shinko for PCB and substrates, Amphenol / TE Connectivity / Hirose for connectors, and Japanese/Korean passive-component leaders for MLCC and capacitors.

These mappings are **research priors, not causal proof**. A rising peer basket cannot create a company thesis. Company product mix, customer exposure, order transmission, expectations, counter-evidence and entry risk must still be checked manually.

## Manual research outputs

After each successful scan, the production workflow writes:

- `output/manual_global_peer_snapshot.csv` — 5/20/60-day price context, MA20/MA60 and local-benchmark RS for the explicit international peers.
- `output/manual_driver_breadth.csv` — transparent peer-basket breadth for each economic driver. `BROADLY_POSITIVE`, `MIXED`, and `BROADLY_WEAK` are context labels only, never trade actions.
- `output/manual_research_queue.csv` — Taiwan candidate shortlist enriched with economic sub-industry, primary/secondary driver, peer basket and peer breadth.
- `output/manual_research_handoff.json` — compact contract stating that model research and automated trade selection are disabled.

Candidates not yet covered by the manual ontology are kept as `UNMAPPED`; they are never silently discarded. This makes missing coverage visible so the mapping can be expanded only when a real candidate makes the work worthwhile.

## First-principles rules

Price may discover an anomaly but may not invent causality. International peers validate an economic chain only when their business exposure matches the Taiwan company. Broad official-industry breadth is context, not proof. Company-specific evidence can veto a seemingly attractive global theme. If the global trend has no edge, the company transmission is weak, or the entry is poor, doing nothing remains valid.

The scanner score is a ranking heuristic, not a probability and not expected return. Automatic brokerage execution remains disabled.

## Cost policy

Production must remain usable with **zero Copilot credits and zero OpenAI API balance**. A future paid-model lane must be explicitly reintroduced in a separate change; it must never silently become a dependency of the daily scanner.
