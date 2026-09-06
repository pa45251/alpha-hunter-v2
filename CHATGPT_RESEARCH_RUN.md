# Alpha Hunter v2.6.1 — ChatGPT Research Run

## User invocation
In ChatGPT, the intended short command is:

`執行 Alpha Hunter V2.6 Research Run`

## Research-agent bootstrap

Use the terminal handoff first:

`output/research_handoff.json`

Canonical source identity is always:

- repository: `pa45251/alpha-hunter-v2`
- branch: `main`

Preferred transport is the connected GitHub connector fetching that exact repository/path. Raw GitHub is only a fallback transport for the same canonical object:

`https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/research_handoff.json`

Do not search GitHub for a repository or substitute a similarly named source, fork, alternate branch, Streamlit table, search snippet, cached copy, or reconstructed scanner output.

If the handoff is missing, `handoff_status != PASS`, or `gate_status != PASS`, report `DATA ACCESS FAILED` and stop Alpha Hunter inference. The Python pipeline, not the LLM, owns repository/schema/hash/run-id/freshness validation.

Fetch the exact `research_packet` identified by the handoff. When the transport exposes file bytes, verify its SHA256 against the handoff before research. The packet `run_id` must equal the handoff `run_id`. If integrity cannot be established, stop rather than substituting another source.

Use the packet's embedded queue/matches and authoritative sources. Research the exact high-priority drivers with current external evidence. Classify only `ACTIVE`, `INACTIVE`, or `UNKNOWN`. Price cannot create causality. Search counter-evidence and distinguish company-specific from industry-wide evidence.

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
