# Alpha Hunter v2.6 — Research Contract

## Purpose
The Research Layer answers **WHY the observed market structure changed and WHICH exact causal driver is active**. It does not validate the data pipeline and it does not make portfolio decisions.

## Entry point
Use only:
`https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/research_packet.json`

The packet is created only after Python's deterministic hard gate passes. If `gate_status != PASS`, stop. Do **not** re-implement manifest/schema/hash/run-id/freshness validation with an LLM.

## Non-negotiable rule
**PRICE CANNOT CREATE CAUSALITY.**

For each high-priority driver classify only `ACTIVE`, `INACTIVE`, or `UNKNOWN`.

`ACTIVE` requires time-consistent external evidence for that exact driver. Separate industry-wide evidence from company-specific evidence and actively search for counter-evidence. Conflicting or insufficient evidence is `UNKNOWN`.

## Structural graph discipline
A structural edge means only: *if the exact driver is active, this company may have economic exposure.* It is not proof that the driver is active and not proof that the stock will rise.

Treat `linkage_confidence` as a seed prior, not a calibrated probability. `provenance_status != SOURCE_BACKED` means `EDGE_PROVENANCE_WEAK` regardless of the numeric prior.

## Hidden Dragon research candidate
Label `HIDDEN_DRAGON_RESEARCH_CANDIDATE` only if:
1. exact driver is independently `ACTIVE`;
2. structural edge is economically plausible/current;
3. Taiwan reaction is `PRE_CONFIRMATION`, early `CONFIRMING`, or controlled `PULLBACK`;
4. evidence suggests the information is not fully priced;
5. material counter-evidence is explicit.

This is not a buy recommendation.

## Required driver fields
`driver_id, state, confidence, primary_cause, industry_wide_or_company_specific, supporting_evidence, counter_evidence, source_count, event_date, source_dates`

## Final handoff
Return:
1. highest-confidence ACTIVE drivers;
2. UNKNOWN drivers despite strong price action;
3. best PRE_CONFIRMATION structural matches;
4. EXTENDED/chase-risk matches;
5. strongest counter-evidence;
6. edges needing provenance review;
7. clearly UNVERIFIED new-driver/new-edge proposals;
8. single biggest unresolved causal question.

## Prohibited
No Buy/Sell, position size, price target, stop, portfolio weight, price-created narrative, broad-industry substitution for company-level linkage, or stale-data inference.
