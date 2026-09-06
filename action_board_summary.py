from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

OUT = Path("output")
packet = json.loads((OUT / "decision_packet.json").read_text(encoding="utf-8"))
with (OUT / "decision_board.csv").open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

run_id = packet.get("run_id", "UNKNOWN")
activation = packet.get("activation_layer") or {}
risk = packet.get("risk_layer") or {}
pos = packet.get("existing_position_layer") or {}

focus = [r for r in rows if r.get("candidate_action") != "WATCH_RESEARCH"]
now = [r for r in focus if r.get("portfolio_action") in {"BUY", "ADD", "REDUCE", "EXIT", "HOLD"}]
near = [r for r in focus if r.get("candidate_action") == "WATCH_ENTRY"]
stage_rank = {"GATE_5_ENTRY": 0, "GATE_4_REACTION": 1, "GATE_3_POSITIVE_EDGE": 2, "GATE_2_TRANSMISSION": 3}
near.sort(key=lambda r: (stage_rank.get(r.get("decision_stage", ""), 9), -float(r.get("research_priority_score") or 0)))

blockers = Counter()
for r in rows:
    b = (r.get("decision_blockers") or "").strip()
    if b:
        for item in b.split("|"):
            if item:
                blockers[item] += 1

mapping_counts = pos.get("system_mapping_counts") or {}
ticker_count = int(mapping_counts.get("SYSTEM_TICKER_EXPOSURE", 0) or 0)
risk_group_count = int(mapping_counts.get("SYSTEM_RISK_GROUP", 0) or 0)
missing_count = int(mapping_counts.get("SYSTEM_MAPPING_MISSING", 0) or 0)
position_count = ticker_count + risk_group_count + missing_count
if not pos.get("position_inputs_valid", False):
    system_readiness = "BLOCKED_PRIVATE_INPUTS"
elif missing_count > 0:
    system_readiness = "PARTIAL"
elif position_count == 0:
    system_readiness = "NO_POSITIONS"
elif risk_group_count > 0:
    system_readiness = "COMPLETE_WITH_SYSTEM_INFERENCE"
else:
    system_readiness = "COMPLETE_EXACT_EXPOSURE"

lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Causal source: `{activation.get('source', 'UNKNOWN')}`",
    f"- Same snapshot: `{activation.get('same_snapshot_v3', False)}`",
    f"- Active drivers: {', '.join(activation.get('active_driver_ids') or []) or 'NONE'}",
    f"- Private risk inputs valid: `{risk.get('risk_inputs_valid', False)}`",
    f"- Auto order execution: `{packet.get('auto_order_execution', False)}`", "",
    "## 1. Actionable now",
]

if now:
    lines += ["", "| Ticker | Name | Action | Driver | Stage |", "|---|---|---|---|---|"]
    for r in now[:12]:
        lines.append(f"| {r.get('ticker')} | {r.get('name')} | {r.get('portfolio_action')} | {r.get('driver_id')} | {r.get('decision_stage')} |")
else:
    lines.append("\nNo validated BUY/ADD/REDUCE/EXIT/HOLD action is currently emitted by the public decision board.")

lines += ["", "## 2. Closest to action"]
if near:
    lines += ["", "| Ticker | Name | Driver | Reaction | Stage | Blocker |", "|---|---|---|---|---|---|"]
    for r in near[:15]:
        lines.append(f"| {r.get('ticker')} | {r.get('name')} | {r.get('driver_id')} | {r.get('reaction_state')} | {r.get('decision_stage')} | {r.get('decision_blockers')} |")
else:
    lines.append("\nNo WATCH_ENTRY candidates.")

lines += ["", "## 3. Main blockers"]
for blocker, count in blockers.most_common(8):
    lines.append(f"- `{blocker}`: {count}")
if not blockers:
    lines.append("- None")

lines += [
    "", "## 4. Existing-position layer (privacy-safe aggregate)",
    f"- Inputs valid: `{pos.get('position_inputs_valid', False)}`",
    f"- System thesis primary: `{pos.get('system_thesis_primary', False)}`",
    f"- System mapping readiness: `{system_readiness}`",
    f"- Position count (aggregate only): `{position_count}`",
    f"- Position action counts: `{json.dumps(pos.get('position_action_counts') or {}, ensure_ascii=False, sort_keys=True)}`",
    f"- System mapping counts: `{json.dumps(mapping_counts, ensure_ascii=False, sort_keys=True)}`",
    f"- Optional user-thesis overlay: `{pos.get('user_thesis_overlay_status', 'NOT_CONFIGURED')}`",
    f"- User/system disagreement count (aggregate only): `{pos.get('user_thesis_disagreement_count', 0)}`",
    "- Per-position holdings, balances, weights, P/L and actions are intentionally not written to this public artifact.",
    "", "## 5. Interpretation",
    "- Existing-position HOLD/REDUCE/EXIT is driven by the system-inferred economic exposure, not by the user's stated purchase reason.",
    "- `SYSTEM_TICKER_EXPOSURE` is preferred; risk-group mapping is a fallback. Missing system mapping fails closed to `REVIEW_RESEARCH`.",
    "- User thesis is optional challenger metadata only; it cannot force HOLD or EXIT.",
    "- `GATE_5_ENTRY` is closest to an executable entry but still requires the defined state-transition trigger and private risk pass.",
    "- `GATE_4_REACTION` means causality and structural transmission passed, but price reaction is already persistent/extended or otherwise not an early entry state.",
    "- This board is decision support only; automatic brokerage execution remains disabled.", "",
]

(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote output/action_board.md: focus={len(focus)} near={len(near)} now={len(now)} system_readiness={system_readiness}")
