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

lines = [
    "# Alpha Hunter — Action Board",
    "",
    f"- Run: `{run_id}`",
    f"- Causal source: `{activation.get('source', 'UNKNOWN')}`",
    f"- Same snapshot: `{activation.get('same_snapshot_v3', False)}`",
    f"- Active drivers: {', '.join(activation.get('active_driver_ids') or []) or 'NONE'}",
    f"- Private risk inputs valid: `{risk.get('risk_inputs_valid', False)}`",
    f"- Auto order execution: `{packet.get('auto_order_execution', False)}`",
    "",
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
        lines.append(
            f"| {r.get('ticker')} | {r.get('name')} | {r.get('driver_id')} | {r.get('reaction_state')} | "
            f"{r.get('decision_stage')} | {r.get('decision_blockers')} |"
        )
else:
    lines.append("\nNo WATCH_ENTRY candidates.")

lines += ["", "## 3. Main blockers"]
for blocker, count in blockers.most_common(8):
    lines.append(f"- `{blocker}`: {count}")
if not blockers:
    lines.append("- None")

lines += [
    "",
    "## 4. Existing-position layer (privacy-safe aggregate)",
    f"- Inputs valid: `{pos.get('position_inputs_valid', False)}`",
    f"- Thesis overlay: `{pos.get('thesis_overlay_status', 'UNKNOWN')}`",
    f"- Position action counts: `{json.dumps(pos.get('position_action_counts') or {}, ensure_ascii=False, sort_keys=True)}`",
    f"- Thesis mapping counts: `{json.dumps(pos.get('thesis_mapping_counts') or {}, ensure_ascii=False, sort_keys=True)}`",
    "- Per-position holdings, balances, weights and P/L are intentionally not written to this public artifact.",
    "",
    "## 5. Interpretation",
    "- `GATE_5_ENTRY` is closest to an executable entry but still requires the defined state-transition trigger and private risk pass.",
    "- `GATE_4_REACTION` means causality and structural transmission passed, but price reaction is already persistent/extended or otherwise not an early entry state.",
    "- `WATCH_RESEARCH` means an earlier causal/provenance/reaction gate blocked the candidate.",
    "- This board is decision support only; automatic brokerage execution remains disabled.",
    "",
]

(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote output/action_board.md: focus={len(focus)} near={len(near)} now={len(now)}")
