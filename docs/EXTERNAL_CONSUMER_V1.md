# External 08:40 consumer contract

Reference implementation: `external_consumer.py`. Existing schedule remains 05:17 Asia/Taipei
Daily Scan → Autonomous Research → Decision → Publish. Consumer remains 08:40 Asia/Taipei.

## Mandatory procedure

1. Resolve `pa45251/alpha-hunter-v2` main to commit S using the GitHub API. Do not search history for
   a prior successful publication. Fetch all bytes from immutable S URLs, never mixed main URLs.
2. Fetch `output/publication_readiness.json`, then every named artifact in its hash map. Validate
   safe filenames and independently compute SHA-256 over raw bytes. Missing/unavailable bytes fail.
3. Require the complete canonical manifest file set and independently validate its SHA-256 entries.
4. Recompute today's Taipei date and latest closed exchange sessions using the verifier's clock and
   exchange calendars. Today's scan generation must not be in the future; Taiwan, each candidate's
   exchange, and US risk session must match the expected closed sessions. A calendar holiday does
   not make yesterday's scan current. This is a current-snapshot contract, not a BUY authorization.
5. Check decision/position run IDs and manifest digest. Check Action Board's embedded `- Run:` ID.
   Check entry source run, selected alignment/decision driver, exact canonical entry levels and
   rotation destination/levels. Reject explicit downstream run IDs that disagree.
6. Recompute the seal's `external_lineage`: manifest digest, decision/board/entry/rotation artifact
   run identities and byte digests, plus canonical sorted selected-entry identity digest. This
   metadata contains only IDs and hashes, no private holdings, amounts, secrets or source text.
   The producer binds outputs only after stable-input and fresh-output publication checks.
7. Resolve main again. If it advanced from S during the read, return NOT_READY; do not stitch runs.

`python external_consumer.py` performs this process over public GitHub HTTP endpoints.
`python external_consumer.py --output /path/to/downloaded/output` verifies an already coherent bundle.
Success JSON contains `contract=ALPHA_HUNTER_EXTERNAL_CONSUMER_1`,
`status=READY_CURRENT_SNAPSHOT`, `source_run_id`, checked time, Taiwan/risk sessions,
`auto_trade_allowed=false`, and (remote mode) repository commit. Any failure returns NOT_READY and
nonzero exit without advisory content. STALE, FAILED, network errors, partial pipelines, unsupported
calendars and missing seals are all conservative NOT_READY results. Never infer READY from a saved
string, CI success, timestamp alone, or an LLM's visual inspection of hashes.

If the scheduled ChatGPT runtime cannot download exact bytes, compute hashes or execute this
verifier/equivalent, it must report NOT_READY / VERIFICATION_UNAVAILABLE. It must not output prior
Alpha Hunter trade instructions, fabricate current entry prices, or substitute yesterday's research.
Independent current market commentary may be labelled separately; it is not Frozen V2 output.

## SLA and acceptance

05:17 to 08:40 is 203 minutes. Existing production timeout budgets total 100 minutes, leaving
103 minutes for aggregate cron/queue/setup delays. Actual prior scan ~231s, capture ~5s, research
~200s plus bounded retry ~29s demonstrate normal compute fits that budget, but do not bound GitHub
cron or provider latency. SLA is reliable read-time READY or NOT_READY, never guaranteed success.

Automated public-transport integration tests cover complete-today and all-current success, today's
scan with research pending, yesterday's board, differing decision/entry/rotation runs, seal mismatch,
yesterday fallback rejection, and main advancing during fetch. Live acceptance must additionally
validate the actual completed live artifact bytes with this consumer. PR testing does not publish
those bytes to main or certify that an unmerged branch is deployed. Historical outputs stay intact.
