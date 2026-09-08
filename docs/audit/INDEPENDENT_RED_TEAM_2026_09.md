# Independent red-team audit — implementation integrity

Audited starting commit: `83da50290462c69eff24293c401c5efcf5468b62`.
Branch: `audit/astra-red-team-v2`. PR: https://github.com/pa45251/alpha-hunter-v2/pull/28

This report separates reproduced defects, operational containment, and remaining certification.
A successful fixture run is not a claim that external research is correct or that production met its SLA.
No trading parameter, weight, score calibration, sizing rule, causal philosophy, or exit rule was tuned.
All Frozen V1/V2 registered files and all checked-in historical output files remain unchanged in the PR.

## Reproduced defects and dispositions

| Priority | Reproduction | Disposition |
|---|---|---|
| P0 | `NaN` gross exposure passes the frozen legacy risk function, producing `risk_gate_pass=True` and `BUY_STOCK` on an otherwise triggered fixture. Frozen Decision V2 imports that legacy risk function. | Formal workflow entrypoints now validate finite, nonnegative, non-boolean private numeric inputs before calling the immutable algorithms. Raw frozen function retained for reproducibility; its result alone is never publication authority. |
| P1 | A 2099 daily-bar sentinel survives scanner download. Current-day Japan/Korea rows existed in the 2026-09-07 08:36 scanner artifact before those sessions closed. | Scanner/Taiwan/risk download boundaries clip by exchange calendars. Covers Taiwan, US-listed instruments (including ADRs), Japan, Korea, holidays, DST, and early closes. Unsupported venues fail closed. |
| P1 | Delete `market_snapshot.csv` from manifest declarations, then corrupt its price: original canonical gate still says PASS. A null run row also hides behind `dropna()`. | Require all 14 original authoritative files, reject duplicate/path-like names, and reject any missing row run ID. |
| P1 | A persisted research PASS with another run ID, mismatched per-driver run, or absent manifest passes the decision-source gate. | Check research contract, manifest/run identities, unique driver identities, and source-count types. Other downstream gates may also block these cases; this is not claimed as an observed executed trade. |
| P1 | Research activation bridge accepts NaN or boolean confidence. Research validator accepts a publication in 2099; a future model research clock can launder future publication dates. | Finite numeric confidence and validator-clock/time-order checks. Infinities were already rejected by the original bridge; tests retain them as controls. |
| P1 | Risk and Exact Entry independently fetch prices after research; same calendar date does not establish identical data provenance. | Capture public risk/entry histories into a hash-bound canonical price bundle. Risk loads the bundle; the guarded entry adapter supplies these frames to the unchanged entry algorithm. No downstream live-price fallback. |
| P1 | Frozen rotation joins candidate and entry plan only by ticker, so a different driver's entry levels can be borrowed. | Publication checks the exact selected driver and all canonical price levels, blocking mismatched rotation. Frozen implementation remains unchanged. |
| P1 | Change a plan's action/status on the same session; frozen trace creates another observation. Its cleanup path can also remove later-dated historical records without testing a freeze boundary. | Publication rejects repeated session/ticker/driver/style samples and historical prefix changes. It does not erase or relabel the existing ledger. This is containment; a versioned append-only trace implementation remains a candidate item. |
| P1 | In two Git clones, publish A's computed board after scanner B advances main: original disjoint-file rebase succeeds, combining board A and manifest B. | Remove artifact rebases. Fast-forward push rejects competing writes atomically. Failed publication requires full recomputation against current inputs, never force push. |
| P1 | Action Board workflow does not subscribe to completion of Autonomous Research. | Add the direct completion dependency, retain success/main/repository checks, and keep the chain within three workflows. |
| P1 | Streamlit trusts persisted PASS/age windows and can still show decision CSV after packet mismatch. | Read-time sealed-artifact hash and current-session verification; NOT_READY stops rendering downstream decision content. A saved READY string alone is insufficient. |

Regression commands:

```bash
python -m pytest -q
python v2_freeze_guard.py
python scripts/runtime_acceptance.py
```

The original suite had 148 passing tests. New adversarial suites include research, closed bars,
canonical manifests, publication, private input guards, real Git races, canonical price bundles,
and live-runner fail-closed/privacy behavior. `test_frozen_v1_integrity.py` verifies all 14 V1 SHA-256
entries, rather than merely checking that the registry exists. V2 verifies all 17 registered blob hashes.

Red-to-green observations were recorded for NaN/boolean bridge inputs, three stale-source cases,
future publications/research clocks, future scanner bars, missing workflow dependency, artifact rebase,
omitted manifest hashes, and null run rows. Tests documenting frozen defects explicitly reproduce
old behavior and then test external containment; they do not pretend the original frozen function changed.

## Runtime acceptance

`scripts/runtime_acceptance.py` runs real production Python entrypoints in a disposable process:

Daily Scan → canonical price capture → handoff → research ingest/source gate → activation bridge
→ guarded Decision with maintenance adapter → existing-position alias/CIO → Global Alignment
→ canonical Exact Entry → Portfolio Risk → Rotation → Action Board → prospective trace/seal.

Only external price, research-response, and private-input boundaries use synthetic fixtures.
No causal/risk/publication gate is mocked. After canonical capture, any new `yf.download` call raises.
The run compares same-session decision reruns, verifies byte-identical repeated trace output,
checks a current READY publication, and removes an entry output to prove NOT_READY.
The synthetic scenario legitimately produces no eligible aligned entry; the existing positive-entry
and rotation fixtures separately exercise valid conditional-plan paths. It does not fabricate a BUY.
Private portfolio-maintenance *model* research is not exercised by this deterministic fixture.

`scripts/live_runtime_acceptance.py` additionally runs the production workflow's live research and
private maintenance steps with repository secrets in trusted same-repository PR CI. It executes no
Git commit/push steps, uploads only aggregate status, and deletes ephemeral private/model artifacts.
The actual PR SHA is recorded. Both acceptance sandboxes simulate the post-merge `main` manifest
identity; this is explicit in the live report and is not a claim that the branch has been deployed.
The latest GitHub `live-runtime-acceptance-status` artifact is the authority for that run's result.
Do not call live acceptance passed if that job is failed, canceled, incomplete, or missing.

## 08:40 Asia/Taipei operational contract

Observed Daily Scan run 34070203882 started on 2026-09-07 at 08:33:52 Taipei and ended at 08:37:14:
https://github.com/pa45251/alpha-hunter-v2/actions/runs/34070203882
The then-configured 06:55 start was delayed approximately 99 minutes, leaving almost no time for research.

New scheduled start: 05:17 Taipei weekdays (`17 21 * * 0-4` UTC), after the US regular close even
in standard time. Existing job caps are 40m scanner, 45m research, 15m publication: 100m compute
budget and 103m combined queue/setup slack before 08:40. This is a planning budget, not a guarantee
that GitHub cron dispatch latency is bounded. Canonical price capture is inside the scanner budget.

At read time:

- READY_CURRENT_SNAPSHOT requires today's successful scan, the expected closed sessions per exchange,
  identical sealed input/output hashes, matched decision/position run IDs, canonical driver/levels,
  current risk session, and no historical trace rewrite/duplicate observation.
- Missing seal, stale day/session, failed build, changed input/output, unsupported calendar, or missing
  mandatory data returns NOT_READY. There is no fallback to yesterday's trading answer.
- The Streamlit consumer enforces this. Other consumers, including a separately configured 08:40
  scheduled radar, must run `python publication_guard.py check` on a coherent checkout (or implement
  the same contract). Reading `output/action_board.md` or a stored READY string alone is unsupported.
  This PR does not change the user's external scheduled task or claim its integration was verified.
- New data-integrity code merged to main triggers a fresh scan so deployment does not rely on an old
  snapshot missing the new price bundle. Main and historical artifacts were not changed during audit.
- Publication contention fails closed. No blind retry/rebase is allowed; recompute on a new checkout.
  Research's existing zero-source retry remains bounded by its workflow timeout.

## Remaining risks and versioned candidate items

1. Frozen raw rotation/risk/trace functions retain their reproduced defects for baseline integrity.
   Official workflows use the new guards; callers bypassing them are unsupported. A future V2.1
   implementation can incorporate the same checks and an append-only trace with its own registry
   and prospective namespace. Never rewrite the V2 registry to make changed algorithms appear frozen.
2. Existing ledger corruption/duplicate sessions can deliberately block publication. Quarantine and
   versioned migration require preserving original records, not deleting rows to get green checks.
3. Age of *underlying economic evidence*, circular sourcing, and correlated indicators need an explicit
   driver-specific evidence policy. No arbitrary new TTL, source weight, or score/probability mapping
   was introduced. These are strategy/data-governance proposals, not threshold bug fixes.
4. Calendar coverage is limited to the supported exchange mappings. Ad hoc exchange closures and data
   corrections remain external data-quality risks. Unknown venues fail closed rather than using US dates.
5. Canonical capture can make unavailable input visible as NOT_READY and can increase latency/storage.
   This is intentional fail-closed behavior, not a promise of daily trade generation.
6. Genuine live service acceptance and externally scheduled radar integration must be evidenced separately.
   A fixture PASS, hash-integrity PASS, or prior production run on main cannot certify this branch's live chain.
7. Audit coverage is adversarial but not a mathematical proof that no other hidden bug exists. Existing
   tests cover BROKEN versus thesis exit, EXTENDED entry blocking, driver activation, provenance,
   duplicate-driver ranking, previous-session state, and future outcome clipping. No new score tuning
   or claim of calibrated win probability is made.

Merge recommendation: require both current-head contract/runtime CI and live acceptance to pass;
resolve any reported blocking failure first. Do not auto-merge or promote live execution.
