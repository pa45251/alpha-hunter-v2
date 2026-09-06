from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

OUT = Path("output")
packet = json.loads((OUT / "decision_packet.json").read_text(encoding="utf-8"))
with (OUT / "decision_board.csv").open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

advisory_rows = []
advisory_packet = {}
advisory_csv = OUT / "cio_advisory.csv"
advisory_json = OUT / "cio_advisory.json"
if advisory_csv.exists():
    with advisory_csv.open(encoding="utf-8", newline="") as f:
        advisory_rows = list(csv.DictReader(f))
if advisory_json.exists():
    try:
        advisory_packet = json.loads(advisory_json.read_text(encoding="utf-8"))
    except Exception:
        advisory_packet = {}

run_id = packet.get("run_id", "UNKNOWN")
activation = packet.get("activation_layer") or {}
risk = packet.get("risk_layer") or {}
pos = packet.get("existing_position_layer") or {}
maintenance = pos.get("maintenance_research") or {}
alias_meta = pos.get("alias_output") or {}
alias_rows = []
alias_path = OUT / "position_alias_actions.json"
if alias_meta.get("status") == "READY" and alias_path.exists():
    try:
        alias_payload = json.loads(alias_path.read_text(encoding="utf-8"))
        if (
            alias_payload.get("contract") == "ALPHA_HUNTER_POSITION_ALIAS_ACTIONS"
            and str(alias_payload.get("run_id", "")) == str(run_id)
        ):
            alias_rows = [r for r in (alias_payload.get("positions") or []) if isinstance(r, dict)]
    except Exception:
        alias_rows = []

focus = [r for r in rows if r.get("candidate_action") != "WATCH_RESEARCH"]
now = [r for r in focus if r.get("portfolio_action") in {"BUY", "BUY_STOCK", "ADD", "REDUCE", "EXIT", "HOLD"}]
near = [r for r in focus if r.get("candidate_action") == "WATCH_ENTRY"]
stage_rank = {"GATE_5_ENTRY": 0, "GATE_4_REACTION": 1, "GATE_3_POSITIVE_EDGE": 2, "GATE_2_TRANSMISSION": 3}
near.sort(key=lambda r: (stage_rank.get(r.get("decision_stage", ""), 9), -float(r.get("research_priority_score") or 0)))

blockers = Counter()
for r in rows:
    b = (r.get("decision_blockers") or "").strip()
    if b:
        for item in b.replace("|", ";").split(";"):
            item = item.strip()
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


def _md(v) -> str:
    return str(v or "").replace("|", "/").replace("\n", " ").strip()


lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Causal source: `{activation.get('source', 'UNKNOWN')}`",
    f"- Same snapshot: `{activation.get('same_snapshot_v3', False)}`",
    f"- Active opportunity drivers: {', '.join(activation.get('active_driver_ids') or []) or 'NONE'}",
    f"- Private risk inputs valid: `{risk.get('risk_inputs_valid', False)}`",
    f"- Auto order execution: `{packet.get('auto_order_execution', False)}`", "",
    "## Deployment status",
    "- SHADOW ONLY: all BUY/SELL/HOLD signals are research outputs; no live order is authorized.",
    f"- Frozen strategy: `{(packet.get('launch_layer') or {}).get('strategy_version', 'NOT_VERIFIED')}`",
    f"- Freeze integrity: `{(packet.get('launch_layer') or {}).get('freeze_integrity_pass', False)}`",
    "- CIO Advisory is deliberately separate from execution permission: it must express the best directional decision under uncertainty, while the frozen execution lane may still block an order.",
    "- Existing-position identities are published only as user-defined aliases; ticker-to-alias mapping remains private.",
    "- First review: 2026-11-29. Review does not automatically enable trading.",
    "- Existing shadow statistics are gross signal outcomes, not validated strategy performance.",
    "", "## 1. CIO advisory — directional decision, not an order",
]

if advisory_rows:
    advisory_rows.sort(key=lambda r: int(float(r.get("advisory_rank") or 9999)))
    lines += ["", "| Rank | Exposure | Name | Advisory | Confidence | Driver | Why |", "|---:|---|---|---|---|---|---|"]
    for r in advisory_rows[:15]:
        preferred = (r.get("preferred_exposure") or "").upper()
        exposure = r.get("etf_ticker") if preferred == "ETF" else r.get("ticker")
        name = "Mapped ETF" if preferred == "ETF" else r.get("name")
        lines.append(
            f"| {r.get('advisory_rank')} | {_md(exposure)} | {_md(name)} | {_md(r.get('advisory_action'))} | "
            f"{_md(r.get('advisory_confidence'))} | {_md(r.get('driver_id'))} | {_md(r.get('advisory_rationale'))} |"
        )
    lines += [
        "",
        f"Advisory counts: `{json.dumps(advisory_packet.get('action_counts') or {}, ensure_ascii=False, sort_keys=True)}`",
        "The advisory lane may say BUY_BIAS/PREFER_ETF/WAIT_PULLBACK/AVOID even when execution remains blocked. That is intentional.",
    ]
else:
    lines.append("\nCIO advisory artifact is not available for this run.")

lines += ["", "## 2. Execution-lane research signals (not executable orders)"]
if now:
    lines += ["", "| Ticker | Name | Action | Driver | Stage |", "|---|---|---|---|---|"]
    for r in now[:12]:
        lines.append(f"| {_md(r.get('ticker'))} | {_md(r.get('name'))} | {_md(r.get('portfolio_action'))} | {_md(r.get('driver_id'))} | {_md(r.get('decision_stage'))} |")
else:
    lines.append("\nNo validated BUY/ADD/REDUCE/EXIT/HOLD action is currently emitted by the frozen execution lane.")

lines += ["", "## 3. Closest to execution action"]
if near:
    lines += ["", "| Ticker | Name | Driver | Reaction | Stage | Blocker |", "|---|---|---|---|---|---|"]
    for r in near[:15]:
        lines.append(f"| {_md(r.get('ticker'))} | {_md(r.get('name'))} | {_md(r.get('driver_id'))} | {_md(r.get('reaction_state'))} | {_md(r.get('decision_stage'))} | {_md(r.get('decision_blockers'))} |")
else:
    lines.append("\nNo WATCH_ENTRY candidates.")

lines += ["", "## 4. Main execution blockers"]
for blocker, count in blockers.most_common(8):
    lines.append(f"- `{blocker}`: {count}")
if not blockers:
    lines.append("- None")

lines += ["", "## 5. Existing-position layer — privacy-safe alias view"]
if alias_rows:
    lines += ["", "| Alias | Action | Reason | Thesis mapping |", "|---|---|---|---|"]
    for r in alias_rows:
        lines.append(
            f"| {_md(r.get('alias'))} | {_md(r.get('action'))} | {_md(r.get('reason'))} | {_md(r.get('thesis_mapping'))} |"
        )
else:
    lines.append(f"\nAlias output unavailable: `{alias_meta.get('status', 'NOT_AVAILABLE')}`. No ticker identity is inferred or guessed.")

lines += [
    "",
    f"- Inputs valid: `{pos.get('position_inputs_valid', False)}`",
    f"- System thesis primary: `{pos.get('system_thesis_primary', False)}`",
    f"- System mapping readiness: `{system_readiness}`",
    f"- Position count: `{position_count}`",
    f"- Position action counts: `{json.dumps(pos.get('position_action_counts') or {}, ensure_ascii=False, sort_keys=True)}`",
    f"- System mapping counts: `{json.dumps(mapping_counts, ensure_ascii=False, sort_keys=True)}`",
    f"- Portfolio-maintenance research lane: `{maintenance.get('maintenance_lane_status', 'NOT_AVAILABLE')}`",
    f"- Maintenance drivers researched/targeted: `{maintenance.get('maintenance_validated_count', 0)}/{maintenance.get('maintenance_target_count', 0)}`",
    f"- Maintenance driver states (aggregate only): `{json.dumps(maintenance.get('maintenance_state_counts') or {}, ensure_ascii=False, sort_keys=True)}`",
    f"- Maintenance targets truncated by safety cap: `{maintenance.get('maintenance_target_truncated_count', 0)}`",
    f"- Optional user-thesis overlay: `{pos.get('user_thesis_overlay_status', 'NOT_CONFIGURED')}`",
    f"- User/system disagreement count: `{pos.get('user_thesis_disagreement_count', 0)}`",
    "- Public alias output contains no ticker, company name, market value, weight, cost, P/L, cash or financing data.",
    "- The ticker-to-alias map remains inside GitHub Secrets/private runtime and is never committed.",
    "", "## 6. Interpretation",
    "- Opportunity discovery, CIO advisory, execution permission, and portfolio maintenance are separate layers.",
    "- CIO advisory answers the decision question under uncertainty; it does not authorize a brokerage order.",
    "- Weak or unverified Taiwan stock alpha should fall back to a mapped ETF or cash instead of forcing endless research. Company provenance is a stock gate, not an ETF-advisory gate.",
    "- Existing-position HOLD/REDUCE/EXIT is driven by system-inferred economic exposure, not by the user's stated purchase reason.",
    "- `SYSTEM_TICKER_EXPOSURE` is preferred; risk-group mapping is a fallback. Missing system mapping fails closed to `REVIEW_RESEARCH`.",
    "- Alias-level existing-position actions may be public, but the underlying instrument mapping stays private.",
    "- User thesis is optional challenger metadata only; it cannot force HOLD or EXIT.",
    "- `GATE_5_ENTRY` is closest to an executable entry but still requires the defined state-transition trigger and private risk pass.",
    "- `GATE_4_REACTION` means causality and structural transmission passed, but price reaction is already persistent/extended or otherwise not an early entry state.",
    "- Automatic brokerage execution remains disabled.", "",
]

(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(
    f"Wrote output/action_board.md: advisory={len(advisory_rows)} alias_positions={len(alias_rows)} "
    f"focus={len(focus)} near={len(near)} now={len(now)} system_readiness={system_readiness} "
    f"maintenance={maintenance.get('maintenance_lane_status', 'NOT_AVAILABLE')}"
)
