# Alpha Hunter — Action Board (Retired)

This repository is currently in **scanner-only manual research mode**.

`output/action_board.md` is intentionally not a live production decision artifact. Automated model research and automated trade selection are disabled. Do not treat historical BUY / EARLY BUY / WAIT / RESEARCH states from older runs as current.

Use the current canonical scanner outputs instead:

- `output/manifest.json` — canonical run and sealed output hashes
- `output/taiwan_candidates.csv` — current Taiwan candidate shortlist
- `output/manual_research_queue.csv` — same-run mapping and international peer context
- `output/manual_research_handoff.json` — same-run manual deep-research handoff

Any future Action Board must be rebuilt from a validated same-snapshot research/adjudication result; it must not silently reuse an older decision snapshot.
