from __future__ import annotations

import json
from pathlib import Path

import sys
import subprocess

if __name__ == "__main__" and "--refresh" in sys.argv:
    for script in ["risk_regime.py", "cio_advisory.py", "position_cio_advisory.py",
                   "global_alignment_v2.py", "entry_plan_run_v2.py", "portfolio_allocation_v2.py"]:
        subprocess.run([sys.executable, script], check=True)
    subprocess.run([sys.executable, __file__], check=True)
    subprocess.run([sys.executable, "entry_action_board_v2.py"], check=True)
    # Prospective trace is diagnostic, not permission to publish market evidence.
    result = subprocess.run([sys.executable, "entry_plan_trace_v2.py"], check=False)
    if result.returncode:
        print("WARNING: optional entry trace failed; daily action board is intact")
    raise SystemExit(0)

from canonical_evidence import assert_output_lineage

OUT = Path("output")
run_id = assert_output_lineage([
    "decision_packet.json", "cio_advisory.json", "position_cio_advisory.json", "risk_regime.json"
])


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def md(value):
    return str(value if value is not None else "UNKNOWN").replace("|", "/").replace("\n", " ")


packet = load("decision_packet.json")
regime = load("risk_regime.json")
positions = load("position_cio_advisory.json")
activation = packet.get("activation_layer") or {}
launch = packet.get("launch_layer") or {}
strict = {}
alias_path = OUT / "position_alias_actions.json"
if alias_path.exists():
    aliases = load("position_alias_actions.json")
    if aliases.get("run_id") != run_id:
        raise RuntimeError("OUTPUT_LINEAGE_MISMATCH:position_alias_actions.json")
    strict = {r["alias"]: r for r in aliases.get("positions", [])}

lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Market session: `{regime.get('risk_snapshot_date', 'UNKNOWN')}`",
    f"- Risk regime: **{regime.get('regime', 'UNKNOWN')}**; target cash: **{md(regime.get('target_cash_pct'))}%**",
    f"- Causal evidence: `{activation.get('source', 'UNKNOWN')}`",
    "- Follow evidence-supported trends; use a valid entry; reduce risk when the thesis fails; otherwise WAIT / CASH.",
    "",
    "## Existing positions", "",
]
rows = positions.get("positions") or []
if rows:
    lines += ["| Position | Instrument trend | Underlying support | Advisory | Risk control |",
              "|---|---|---|---|---|"]
    for row in rows:
        control = strict.get(row["alias"], {})
        # Surface existing mandatory reductions/exits without presenting a second hold/buy list.
        risk_control = control.get("action") if control.get("action") in {"REDUCE", "EXIT"} else "—"
        lines.append("| " + " | ".join(md(v) for v in [row["alias"], row.get("trend_state"),
                     row.get("macro_support"), row.get("advisory_action"), risk_control]) + " |")
    lines += ["", "Instrument trend uses the held instrument's sealed closed-session prices. Theme breadth supplies context and never replaces instrument trend."]
else:
    lines += [f"Position assessment unavailable: `{positions.get('status', 'UNKNOWN')}`. No position action is inferred."]
lines += [
    "", "## Evidence and execution boundary", "",
    f"- Current validated drivers: {', '.join(activation.get('active_driver_ids') or []) or 'NONE — WAIT / CASH'}",
    f"- Private risk inputs valid: `{(packet.get('risk_layer') or {}).get('risk_inputs_valid', False)}`",
    f"- Frozen release integrity: `{launch.get('freeze_integrity_pass', False)}`",
    "- Exact entry and rotation use the single canonical V2 plan shown above; independent legacy action lists are not published.",
    "- Automatic order execution is disabled. Frozen release drift never grants live permission.", "",
]
(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote canonical action board: run_id={run_id}; positions={len(rows)}")
