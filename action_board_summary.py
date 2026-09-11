from __future__ import annotations

import json
from pathlib import Path

import sys
import subprocess

if __name__ == "__main__" and "--refresh" in sys.argv:
    for name in ["position_cio_advisory.json", "position_alias_actions.json", "portfolio_allocation_v2.json", "portfolio_allocation_advisory.json", "cio_advisory.json", "cio_advisory.csv"]:
        (Path("output") / name).unlink(missing_ok=True)
    for script in ["risk_regime.py", "global_alignment_v2.py", "entry_plan_run_v2.py"]:
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
    "decision_packet.json", "risk_regime.json"
])


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def md(value):
    return str(value if value is not None else "UNKNOWN").replace("|", "/").replace("\n", " ")


packet = load("decision_packet.json")
regime = load("risk_regime.json")
activation = packet.get("activation_layer") or {}
launch = packet.get("launch_layer") or {}
lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Global risk session: `{regime.get('risk_snapshot_date', 'UNKNOWN')}`",
    f"- Risk regime: **{regime.get('regime', 'UNKNOWN')}**",
    f"- Causal evidence: `{activation.get('source', 'UNKNOWN')}`",
    "- Follow evidence-supported trends; use a valid entry; reduce risk when the thesis fails; otherwise WAIT / CASH.",
    "",
]
lines += [
    "", "## Evidence and execution boundary", "",
    f"- Current validated drivers: {', '.join(activation.get('active_driver_ids') or []) or 'NONE — WAIT / CASH'}",
    f"- Frozen release integrity: `{launch.get('freeze_integrity_pass', False)}`",
    "- Entry plans use the same canonical market evidence. No personal allocation or position management is performed.",
    "- Automatic order execution is disabled. Frozen release drift never grants live permission.", "",
]
(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote canonical action board: run_id={run_id}")
