from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import subprocess
import sys

if __name__ == "__main__" and "--refresh" in sys.argv:
    for name in [
        "position_cio_advisory.json", "position_alias_actions.json",
        "portfolio_allocation_v2.json", "portfolio_allocation_advisory.json",
        "cio_advisory.json", "cio_advisory.csv",
    ]:
        (Path("output") / name).unlink(missing_ok=True)
    for script in ["risk_regime.py", "global_alignment_v2.py", "entry_plan_run_v2.py"]:
        subprocess.run([sys.executable, script], check=True)
    subprocess.run([sys.executable, __file__], check=True)
    subprocess.run([sys.executable, "entry_action_board_v2.py"], check=True)
    result = subprocess.run([sys.executable, "entry_plan_trace_v2.py"], check=False)
    if result.returncode:
        print("WARNING: optional entry trace failed; daily action board is intact")
    raise SystemExit(0)

from canonical_evidence import assert_output_lineage

OUT = Path("output")
run_id = assert_output_lineage(["decision_packet.json", "risk_regime.json"])


def load(name: str) -> dict:
    path = OUT / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(name: str) -> pd.DataFrame:
    path = OUT / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype={"taiwan_code": str, "code": str})
    except Exception:
        return pd.DataFrame()


def md(value) -> str:
    return str(value if value is not None else "UNKNOWN").replace("|", "/").replace("\n", " ")


def _valid_entry_tickers() -> set[str]:
    entries = load("entry_plans_v2.json")
    if str(entries.get("source_run_id") or "") != run_id:
        return set()
    valid: set[str] = set()
    for bucket in ("fresh", "pullback", "continuation"):
        for row in entries.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if bool(row.get("entry_structure_valid")) and bool(row.get("risk_v2_pass", True)):
                ticker = str(row.get("ticker") or "")
                if ticker:
                    valid.add(ticker)
    return valid


def _driver_states() -> dict[str, str]:
    a = read_csv("driver_activation_v3.csv")
    if a.empty or "driver_id" not in a.columns:
        return {}
    if "research_run_id" in a.columns:
        a = a[a["research_run_id"].astype(str) == run_id]
    states: dict[str, str] = {}
    for row in a.itertuples():
        driver_id = str(getattr(row, "driver_id", ""))
        state = str(getattr(row, "activation_state", "UNKNOWN")).upper()
        if driver_id:
            states[driver_id] = state
    return states


def _driver_status(driver_id: str, states: dict[str, str]) -> str:
    if driver_id == "UNMAPPED_OPPORTUNITY":
        return "UNCLEAR"
    state = states.get(driver_id, "UNKNOWN")
    if state == "ACTIVE":
        return "CONFIRMED"
    if state == "INACTIVE":
        return "REJECTED"
    return "UNCLEAR"


def _relative_state(row: pd.Series) -> str:
    if str(row.get("driver_id", "")) == "UNMAPPED_OPPORTUNITY":
        return "UNMAPPED / WHY?"
    try:
        global_strength = float(row.get("global_theme_strength_v2"))
    except (TypeError, ValueError):
        global_strength = float("nan")
    if pd.isna(global_strength) or global_strength < 0.55:
        return "NO GLOBAL SUPPORT"
    try:
        gap = float(row.get("transmission_gap_proxy"))
    except (TypeError, ValueError):
        gap = float("nan")
    if pd.isna(gap):
        return "TOGETHER"
    if gap > 0.08:
        return "GLOBAL AHEAD"
    if gap < -0.08:
        return "TAIWAN AHEAD"
    return "TOGETHER"


def _simple_action(row: pd.Series, driver_status: str, relative_state: str, valid_entries: set[str]) -> str:
    ticker = str(row.get("ticker", ""))
    reaction = str(row.get("reaction_state", "UNKNOWN")).upper()
    if driver_status == "REJECTED":
        return "PASS"
    if relative_state in {"TAIWAN AHEAD", "NO GLOBAL SUPPORT"} or reaction == "EXTENDED":
        return "PASS" if driver_status != "CONFIRMED" else "WAIT"
    if driver_status == "CONFIRMED" and ticker in valid_entries:
        return "BUY SETUP"
    return "WAIT"


def _select_opportunities(limit: int = 5) -> list[dict]:
    reverse = read_csv("reverse_transmission_candidates.csv")
    if reverse.empty or "ticker" not in reverse.columns:
        return []
    if "run_id" in reverse.columns:
        reverse = reverse[reverse["run_id"].astype(str) == run_id]
    if reverse.empty:
        return []

    reverse["reverse_research_priority"] = pd.to_numeric(
        reverse.get("reverse_research_priority"), errors="coerce"
    ).fillna(0.0)
    reverse = reverse.sort_values("reverse_research_priority", ascending=False)
    reverse = reverse.drop_duplicates("ticker", keep="first")

    top = reverse.head(limit).copy()
    unmapped = reverse[reverse["driver_id"].astype(str).eq("UNMAPPED_OPPORTUNITY")]
    if not unmapped.empty and not top["driver_id"].astype(str).eq("UNMAPPED_OPPORTUNITY").any():
        top = pd.concat([top.head(max(0, limit - 1)), unmapped.head(1)], ignore_index=True)
        top = top.sort_values("reverse_research_priority", ascending=False).head(limit)

    states = _driver_states()
    valid_entries = _valid_entry_tickers()
    rows: list[dict] = []
    for _, row in top.iterrows():
        driver_id = str(row.get("driver_id", ""))
        status = _driver_status(driver_id, states)
        relative = _relative_state(row)
        rows.append({
            "ticker": str(row.get("ticker", "")),
            "name": str(row.get("name", "")),
            "driver": str(row.get("driver_label", driver_id)),
            "driver_status": status,
            "relative": relative,
            "action": _simple_action(row, status, relative, valid_entries),
        })
    return rows


packet = load("decision_packet.json")
regime = load("risk_regime.json")
activation = packet.get("activation_layer") or {}
launch = packet.get("launch_layer") or {}
opportunities = _select_opportunities(5)

lines = [
    "# Alpha Hunter — Action Board", "",
    f"- Run: `{run_id}`",
    f"- Market session: `{regime.get('risk_snapshot_date', 'UNKNOWN')}`",
    f"- Risk regime: **{regime.get('regime', 'UNKNOWN')}**",
    f"- Causal evidence: `{activation.get('source', 'UNKNOWN')}`",
    "- Core rule: find the anomaly -> understand WHY -> validate the same driver globally -> act only if price still offers a setup.",
    "",
    "## Simple Opportunity Brief", "",
]

if opportunities:
    lines += [
        "| Stock | Bottom-up driver | Driver status | Relative position | Action |",
        "|---|---|---|---|---|",
    ]
    for row in opportunities:
        stock = f"{md(row['ticker'])} {md(row['name'])}".strip()
        lines.append(
            f"| {stock} | {md(row['driver'])} | **{row['driver_status']}** | {row['relative']} | **{row['action']}** |"
        )
else:
    lines.append("- **NONE** — no reverse-discovery opportunity is available for this snapshot.")

lines += [
    "",
    "- `CONFIRMED / UNCLEAR / REJECTED` is the only user-facing causal verdict; raw confidence scores remain background diagnostics.",
    "- `UNMAPPED / WHY?` means the stock is unusually strong but the system has no pre-existing economic edge; research comes before any thesis.",
    "- `BUY SETUP` is allowed only when the driver is CONFIRMED and the canonical V2 entry/risk plan is valid. Otherwise WAIT or PASS.",
    "",
    "## Evidence and execution boundary", "",
    f"- Current validated drivers: {', '.join(activation.get('active_driver_ids') or []) or 'NONE — WAIT / CASH'}",
    f"- Frozen release integrity: `{launch.get('freeze_integrity_pass', False)}`",
    "- Engineering gates, hashes, lineage, frontier/challenger and shadow validation remain background safety plumbing.",
    "- Automatic order execution is disabled.", "",
]

(OUT / "action_board.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote simplified canonical action board: run_id={run_id} opportunities={len(opportunities)}")
