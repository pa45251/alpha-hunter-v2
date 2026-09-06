from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from causal_engine import CausalConfig, apply_driver_activation, validate_driver_activation_file
from decision_engine import apply_edge_provenance, apply_exposure_map, write_decision_outputs
from existing_position import apply_existing_position_engine
from portfolio_risk import apply_portfolio_risk_gate
from shadow_audit import append_shadow_audit


OUT = Path("output")


def main() -> None:
    gate_path = OUT / "gate_report.json"
    manifest_path = OUT / "manifest.json"
    queue_path = OUT / "causal_research_queue.csv"
    structural_path = OUT / "structural_matches.csv"

    required = [gate_path, manifest_path, queue_path, structural_path]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"Decision bridge missing canonical inputs: {missing}")

    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if gate.get("gate_status") != "PASS":
        raise RuntimeError(f"Decision bridge blocked by hard gate: {gate.get('failure_code')}")

    run_id = str(manifest.get("run_id", ""))
    if not run_id or str(gate.get("run_id", "")) != run_id:
        raise RuntimeError("Decision bridge MIXED_SNAPSHOT_DATA: manifest/gate run_id mismatch")

    queue = pd.read_csv(queue_path)
    structural = pd.read_csv(structural_path, dtype={"taiwan_code": str})
    for name, df in [("causal_research_queue", queue), ("structural_matches", structural)]:
        if "run_id" not in df.columns or df.empty or not df["run_id"].astype(str).eq(run_id).all():
            raise RuntimeError(f"Decision bridge MIXED_SNAPSHOT_DATA: {name} run_id mismatch")

    activations = validate_driver_activation_file(Path("input/driver_activation.csv"), queue, CausalConfig())
    if "activation_valid" not in structural.columns:
        structural = apply_driver_activation(structural, activations)

    structural = apply_edge_provenance(structural, Path("input/edge_provenance.csv"))
    structural = apply_exposure_map(structural, Path("config/decision_exposure_map.csv"))

    board, packet = write_decision_outputs(structural, run_id, "output")

    # Private risk and existing-position evaluation consume Secrets in-memory only.
    # Per-position holdings/actions are never committed or printed in this public repository.
    board, risk_meta = apply_portfolio_risk_gate(board)
    board.to_csv(OUT / "decision_board.csv", index=False)
    _private_position_actions, position_meta = apply_existing_position_engine(board)

    packet["risk_layer"] = risk_meta
    packet["existing_position_layer"] = position_meta
    packet["current_capability"] = "ETF_VS_STOCK_ENTRY_PLUS_PRIVATE_RISK_PLUS_EXISTING_POSITION_EXIT"
    packet["missing_downstream_modules"] = ["SHADOW_AUDIT_VALIDATION"]
    if not risk_meta.get("risk_inputs_valid") or not position_meta.get("position_inputs_valid"):
        packet["missing_downstream_modules"] = ["PRIVATE_RISK_INPUTS_IF_NOT_CONFIGURED", "SHADOW_AUDIT_VALIDATION"]
    packet["portfolio_action_counts"] = {
        str(k): int(v) for k, v in board["portfolio_action"].value_counts(dropna=False).to_dict().items()
    } if "portfolio_action" in board.columns else {}
    packet["auto_order_execution"] = False
    (OUT / "decision_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    audit = append_shadow_audit(board, "output/shadow_audit.csv")

    accepted = int(activations.get("activation_valid", pd.Series(dtype=bool)).fillna(False).sum()) if not activations.empty else 0
    edge_backed = int(board.get("gate_edge_source_backed", pd.Series(dtype=bool)).fillna(False).sum()) if not board.empty else 0
    risk_pass = int(board.get("risk_gate_pass", pd.Series(dtype=bool)).fillna(False).sum()) if not board.empty else 0
    print(f"Decision bridge run_id: {run_id}")
    print(f"Research activations accepted: {accepted}")
    print(f"Source-backed live structural rows: {edge_backed}")
    print(f"Decision board rows: {len(board)}")
    print(f"Risk-gate PASS rows: {risk_pass}")
    print(f"Action counts: {packet.get('action_counts', {})}")
    print(f"Portfolio action counts: {packet.get('portfolio_action_counts', {})}")
    print(f"Existing-position engine status: {'PASS' if position_meta.get('position_inputs_valid') else 'BLOCKED'}")
    print(f"Shadow audit rows retained: {len(audit)}")
    print("No brokerage/order execution exists. BUY/REDUCE/EXIT decisions require their respective gates; private position details are never logged.")


if __name__ == "__main__":
    main()
