# Alpha Hunter V4 — Automated Evidence + OpenAI Frontier Architecture

## Objective

Alpha Hunter must produce a fresh weekday morning decision package without requiring a manual GitHub button press, while keeping market evidence, causal reasoning, policy gates, portfolio privacy and prospective validation auditable and separable.

The architecture is evidence-centric rather than agent-centric. GitHub Copilot is no longer the sole reasoning ceiling. OpenAI/ChatGPT can improve independently without changing the scanner, evidence transport or risk authority.

## System of record

1. **Canonical scanner snapshot** — market and Taiwan data, candidate discovery, theme breadth and structural matches.
2. **Deterministic evidence transport** — support/counter source discovery with exact URLs and timestamps.
3. **Reasoning providers** — bounded interpretation only; they cannot create causality from price.
4. **Deterministic policy** — provenance, causal, reaction, entry, risk, privacy and same-snapshot gates.
5. **Prospective shadow ledger** — the validation authority for future promotion.

The evidence layer, not any model, is the truth layer.

## Morning automation

`Alpha Hunter Daily Scan` uses three staggered weekday triggers in Asia/Taipei:

- 06:20 primary
- 06:40 backup
- 07:00 final backup

`automation_guard_v4.py` makes these triggers idempotent. Once a PASS canonical snapshot has been generated on the current Taipei date, later backup triggers intentionally perform no new scan. Manual workflow dispatch remains an emergency path and defaults to `force=true`.

Downstream reasoning additionally verifies that a `workflow_run` trigger actually produced the current canonical snapshot. A successful no-op backup must never consume reasoning credits or masquerade as a new snapshot.

### Independent ChatGPT watchdog

GitHub cron is not treated as a timing SLA. A separate scheduled ChatGPT watchdog checks the canonical manifest before the morning report. If a current Taipei-date PASS snapshot is absent, it updates only `.alpha-hunter/scan_watchdog.json`. That harmless push is an external trigger for `Alpha Hunter Daily Scan`; the same deterministic freshness guard still decides whether a scan is actually needed.

This creates two independent orchestration paths:

1. GitHub scheduled workflow;
2. ChatGPT scheduled watchdog -> guarded trigger-file push.

Neither path can bypass the canonical freshness guard, and duplicate/no-op Daily Scan completions are rejected by downstream research trigger gates.

## Reasoning lanes

### Baseline lane

The existing V3 autonomous research lane remains a fail-closed baseline during migration. Its output is not considered unquestionable truth; it is one bounded interpretation of the deterministic evidence packet.

### OpenAI frontier lane

`Alpha Hunter V4 OpenAI Frontier Research` is an independent challenger lane.

- Trigger: a successful Daily Scan that produced a new canonical snapshot.
- Provider: OpenAI Responses API.
- Model: repository variable `OPENAI_FRONTIER_MODEL`, default `gpt-5.6`.
- Reasoning effort: repository variable `OPENAI_FRONTIER_REASONING_EFFORT`, default `high`.
- Secret: `OPENAI_API_KEY`.
- Input: exact same canonical handoff plus deterministic source prefetch.
- Output: `output/frontier_research_v4.json` only after contract validation.
- The model may not cite a URL absent from the deterministic prefetch packet.
- ACTIVE/INACTIVE without a source fails validation.
- run_id mismatch fails validation.
- Frontier output does not bypass downstream deterministic policy.

If `OPENAI_API_KEY` is absent, this lane is safely inactive; the baseline pipeline continues.

## ChatGPT product frontier lane

A scheduled ChatGPT task reads the latest GitHub canonical outputs and acts as the user-facing frontier CIO/challenger. This lane benefits directly from ChatGPT model improvements without coupling the repository to a fixed model release.

Before producing a report it verifies:

- manifest status = PASS;
- canonical snapshot is fresh for the current Taipei morning;
- decision_packet run_id matches manifest run_id;
- research source is same-snapshot;
- no stale Action Board is presented as today's conclusion.

It then challenges causal reasoning with current public evidence, explicitly separates evidence from inference, and reports portfolio aliases plus new opportunities. It is advisory and must not create brokerage orders.

## Promotion policy

The newest frontier model is not automatically promoted to production policy authority.

A frontier provider may become the primary reasoning provider only after prospective comparison against the current production lane on:

- source integrity;
- causal consistency;
- contradiction detection;
- false-positive rate;
- decision stability;
- forward shadow outcomes;
- cost/latency.

Model upgrades therefore improve intelligence without silently changing frozen policy or invalidating prospective tests.

## Target end-state

```text
GitHub cron ---------+
                     |
ChatGPT watchdog ----+--> Canonical scanner
                          |
                          v
                Deterministic evidence factory
                          |
              +-----------+-----------+
              |                       |
              v                       v
       Baseline reasoner        OpenAI frontier reasoner
              |                       |
              +-----------+-----------+
                          v
                bounded adjudication
                          |
                          v
              deterministic policy gates
                          |
                          v
             Entry / Hold / Reduce / Exit
                          |
                          v
                prospective validation
                          |
                          v
              ChatGPT morning CIO report
```

## Non-negotiable invariants

- Price cannot create causality.
- A model cannot invent evidence.
- Evidence URLs must be traceable to deterministic discovery.
- Same-snapshot lineage is mandatory.
- Missing or stale evidence fails closed.
- Existing-position privacy remains in-memory/alias-only.
- Repeated same-session automation cannot manufacture a new entry trigger.
- No model can override deterministic risk/entry policy.
- No automatic brokerage execution is introduced by V4.
