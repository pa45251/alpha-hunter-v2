# Alpha Hunter v2.6 — ChatGPT Research Run

## User invocation
In ChatGPT, the intended short command is:

`執行 Alpha Hunter V2.6 Research Run`

## Research-agent bootstrap
Fetch only this canonical handoff first:

`https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/research_packet.json`

Do not search GitHub for a repository or substitute a similarly named source.

If the packet is missing or `gate_status != PASS`, report `DATA ACCESS FAILED` and stop Alpha Hunter inference. The Python pipeline, not the LLM, owns repository/schema/hash/run-id/freshness validation.

Use the packet's `run_id`, embedded queue/matches, and `authoritative_sources`. Research the exact high-priority drivers with current external evidence. Classify only `ACTIVE`, `INACTIVE`, or `UNKNOWN`. Price cannot create causality. Search counter-evidence and distinguish company-specific from industry-wide evidence.

Then hand off:
1. highest-confidence ACTIVE drivers;
2. UNKNOWN drivers despite strong price action;
3. best PRE_CONFIRMATION structural matches;
4. EXTENDED/chase-risk matches;
5. strongest counter-evidence;
6. weak/stale structural edges;
7. UNVERIFIED new driver/edge proposals;
8. single biggest unresolved causal question.

No Buy/Sell, position size, target, stop or portfolio weight in the Research Layer. Those belong to the downstream decision system.
