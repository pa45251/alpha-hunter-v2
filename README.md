# Alpha Hunter v2.6 — Deterministic Data Plane + Causal Research Plane

Alpha Hunter v2.6 keeps v2.5's causal discipline and fixes the most important architecture weakness: **an LLM is no longer trusted to validate deterministic data integrity.**

```text
GitHub Actions
   ↓
Global + Taiwan scanners          = WHAT MOVED
   ↓
Causal research queue             = WHICH EXACT DRIVER NEEDS RESEARCH
   ↓
Manifest + canonical outputs
   ↓
Python deterministic hard gate    = IDENTITY / HASH / RUN_ID / FRESHNESS / INVARIANTS
   ↓ PASS only
research_packet.json
   ↓
Research Agent                     = WHY / ACTIVE vs INACTIVE vs UNKNOWN
   ↓
Structural exposure + Taiwan state = WHO COULD BENEFIT / HAS PRICE CONFIRMED?
   ↓
Challenger / Red Team
   ↓
Downstream Decision System         = ETF / STOCK / CASH + ENTRY / RISK / EXIT
```

## Hard rule
**PRICE CANNOT CREATE CAUSALITY.**

## Deterministic gate
`canonical_gate.py` validates:
- canonical repository and branch;
- schema/scanner versions;
- manifest PASS and pipeline checks;
- required-file presence;
- SHA-256 of every authoritative file;
- same `run_id` in causal queue / structural matches / graph audit;
- driver-ID consistency across taxonomy/graph/queue/matches;
- graph-audit completeness;
- unresolved scanner-time causal queue;
- scanner cannot mark a trade decision eligible;
- Taiwan candidate uniqueness;
- generated-run and market-date freshness.

A failed gate exits GitHub Actions before outputs are committed.

## Research entry point
Primary Research Layer reads only:
`https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/research_packet.json`

See `RESEARCH_CONTRACT.md`.

## Gemini
Gemini is no longer the source-of-truth research gatekeeper. If used, use `CHALLENGER_PROMPT.md` for adversarial review only.

## New v2.6 outputs
- `output/gate_report.json`
- `output/research_packet.json` (PASS snapshots only)

## Daily automation
GitHub Actions runs around 06:55 Asia/Taipei on weekdays. The workflow runs the scanner, executes the deterministic gate, and commits only a passing canonical snapshot.
