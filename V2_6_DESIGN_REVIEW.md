# Alpha Hunter v2.6 — Deterministic Data Plane + Probabilistic Research Plane

## Why v2.6 exists
v2.5 correctly separated price observation, causal drivers, structural exposure and Taiwan reaction, but still asked an LLM to perform deterministic data-contract checks. That is an architectural error: repository identity, schema, run consistency, file hashes and freshness are machine-verifiable facts and must not depend on language-model interpretation.

## v2.6 architecture
1. Global/Taiwan scanners: observable market structure.
2. Causal queue: unresolved exact-driver research tasks.
3. Structural graph: slow-moving economic exposure hypotheses.
4. **Deterministic Hard Gate (Python):** identity, schema, pipeline, cryptographic file integrity, run consistency, cross-file causal integrity, freshness and no-trade invariants.
5. Research Packet: emitted only after the hard gate passes.
6. Research Agent: external evidence, exact-driver ACTIVE/INACTIVE/UNKNOWN, counter-evidence.
7. Challenger Agent: adversarial review only.
8. Downstream Decision System: ETF/stock/cash + entry/risk/exit.

## New protections
- LLMs no longer validate manifest/schema/hash/run-id/freshness.
- SHA-256 is verified for every authoritative file.
- `run_id` is cross-checked across queue, structural matches and graph audit.
- Driver IDs are checked across taxonomy, graph, queue and live matches.
- Queue rows must remain unresolved at scanner time.
- Scanner outputs are forbidden from setting `decision_eligible=True`.
- Candidate ticker duplication is a gate failure.
- Market-date staleness uses holiday-safe bounds designed to catch genuinely stale snapshots without failing ordinary weekends/holidays.
- `research_packet.json` exists only for a gate-passing snapshot.

## Remaining weaknesses
v2.6 still does not solve causal truth. External research can be wrong, late, correlated or narrative-driven. Structural graph edges still need source-backed provenance, exposure magnitude, customer concentration, substitution risk and industry-specific lag calibration. The taxonomy can miss new drivers. Heuristic ranking weights remain uncalibrated. These are research/model-risk problems, not data-integrity problems, and should be handled separately rather than hidden inside one score.
