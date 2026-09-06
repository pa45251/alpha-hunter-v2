# Alpha Hunter v3.0 — Autonomous Research + Challenger Architecture

## Goal
Close the only remaining non-deterministic gap between scanner nomination and downstream decisioning without allowing price action to manufacture causality.

## Non-negotiable rule
**PRICE CANNOT CREATE CAUSALITY.** Scanner price structure may nominate a driver for research; it may never activate a driver.

## Pipeline

```text
Deterministic scanner
  -> canonical_gate.py
  -> research_packet.json
  -> autonomous research layer
       -> evidence collection
       -> exact-driver classification: ACTIVE / INACTIVE / UNKNOWN
       -> counter-evidence collection
       -> provenance + event-time checks
  -> challenger layer
       -> attack causal claim
       -> distinguish company-specific vs industry-wide evidence
       -> reject broad-theme substitution
       -> reject stale / circular / price-derived evidence
  -> research verdict
  -> structural Taiwan transmission
  -> downstream decision engine
  -> private risk + existing-position thesis/exit
  -> immutable shadow validation
```

## Research-agent contract
For every unresolved high-priority `driver_id` in the canonical research packet, the research layer must produce:

- `driver_id`
- `state`: `ACTIVE | INACTIVE | UNKNOWN`
- `confidence`: 0..1
- `primary_cause`
- `industry_scope`: `INDUSTRY_WIDE | COMPANY_SPECIFIC | MIXED | UNKNOWN`
- `supporting_evidence[]`
- `counter_evidence[]`
- `source_count`
- `event_date`
- `source_dates[]`
- `researched_at_utc`
- `research_run_id`

A driver is `ACTIVE` only when independent, time-consistent external evidence supports the **exact driver**. Strong theme price action is never evidence of activation.

## Evidence requirements
1. Prefer primary sources: company filings/IR, government/regulator releases, exchange/industry data, then high-quality reporting.
2. Evidence must identify publication date and, when distinct, event date.
3. Company-specific evidence cannot silently become industry-wide evidence.
4. Search for material counter-evidence before assigning `ACTIVE`.
5. Conflicting or insufficient evidence -> `UNKNOWN`.
6. Price/technical data may be used only downstream as confirmation/reaction state.
7. Every source-backed claim must retain a source URL or stable source identifier in the research artifact.

## Challenger hard gate
The challenger independently reviews every proposed `ACTIVE` driver and can return:

- `PASS`
- `DOWNGRADE_TO_UNKNOWN`
- `REJECT_INACTIVE`
- `NEEDS_MORE_EVIDENCE`

The challenger must explicitly test:

- exact-driver match;
- causal direction;
- event-time consistency;
- industry breadth;
- company-specific contamination;
- circular sourcing;
- stale evidence;
- counter-evidence;
- whether price action was improperly used as causal evidence.

Only challenger `PASS` may feed a driver as confirmed ACTIVE into downstream transmission.

## Fail-closed behavior
If research credentials, web/search provider, source retrieval, schema validation, or challenger validation fails:

- preserve the canonical scanner snapshot;
- emit `RESEARCH_UNAVAILABLE` or `UNKNOWN`;
- do **not** promote a driver to ACTIVE;
- do **not** fabricate sources;
- do **not** overwrite the last valid source-backed activation as if it were newly researched.

## Separation of public and private data
Public repository artifacts may contain market data, causal evidence, structural mappings, decisions produced from public data, and shadow-validation outputs.

Private portfolio quantities, leverage, account values, and private position thesis remain in GitHub Actions Secrets or other private storage and must never be committed to repository outputs.

## No-hindsight rule
Historical research verdicts and downstream decisions are immutable. Later outcomes are appended by the shadow validator. Validation results may motivate a future versioned design review, but the validator itself may not tune thresholds or rewrite historical states.

## v3.0 implementation phases

### Phase A — contract and deterministic validation
- Define research-result and challenger schemas.
- Validate driver IDs against canonical taxonomy/queue.
- Require source metadata for any ACTIVE verdict.
- Reject price-derived causal evidence.
- Add tests for fail-closed behavior.

### Phase B — autonomous evidence collection
- Connect a supported external research/search provider through Actions secrets.
- Research unresolved drivers only; never scan the open web without a canonical queue target.
- Cache source metadata and evidence snapshots for auditability.

### Phase C — challenger
- Independently attack proposed ACTIVE verdicts.
- Only PASS verdicts reach transmission as confirmed activation.

### Phase D — downstream integration
- Feed validated research verdicts into structural matches and decision bridge.
- Preserve UNKNOWN rather than forcing a trade.
- Record research/challenger version IDs in decision and shadow-audit artifacts.

## Current limitation
Creating this contract does **not** by itself make GitHub Actions capable of live web research. Phase B requires an explicitly configured research/search provider and credential. Until then the system must fail closed rather than pretend research occurred.
