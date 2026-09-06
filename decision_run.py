from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from causal_engine import CausalConfig, apply_driver_activation, validate_driver_activation_file
from decision_engine import apply_edge_provenance, apply_exposure_map, write_decision_outputs
from existing_position import apply_existing_position_engine
from portfolio_risk import apply_portfolio_risk_gate
from launch_gate import apply_launch_gate
from shadow_audit import append_shadow_audit, seal_public_snapshot
from shadow_validation import write_shadow_validation


OUT = Path("output")


_ACTIVATION_DERIVED_COLUMNS = {
    "activation_state",
    "activation_confidence",
    "activation_valid",
    "activation_age_hours",
    "as_of_utc",
    "source_count",
    "primary_cause",
    "counter_evidence",
    "source_summary",
}


def _same_snapshot_activation(path: Path, run_id: str, source_name: str) -> bool:
    if not path.exists():
        return False
    try:
        df = pd.read_csv(path)
    except Exception:
        return False
    return bool(
        not df.empty
        and "research_run_id" in df.columns
        and df["research_run_id"].astype(str).eq(run_id).all()
        and "activation_source" in df.columns
        and df["activation_source"].astype(str).eq(source_name).all()
    )


def _activation_source_for_run(run_id: str) -> tuple[Path, str]:
    """Prefer same-snapshot challenger adjudication, then autonomous research.

    The challenger artifact is a human-in-the-loop/ChatGPT research adjudication layer and may
    override Copilot classifications only when it matches the exact canonical scanner run_id.
    Stale adjudication and stale autonomous research are never consumed. V3_VALIDATED requires
    one of these same-snapshot validated sources and fails closed otherwise.
    """
    mode = os.getenv("ALPHA_HUNTER_ACTIVATION_SOURCE", "AUTO").strip().upper()
    adjudicated_path = OUT / "driver_activation_adjudicated_v3.csv"
    v3_path = OUT / "driver_activation_v3.csv"
    legacy_path = Path("input/driver_activation.csv")

    if mode not in {"AUTO", "V3_VALIDATED", "LEGACY_MANUAL"}:
        raise RuntimeError(f"Unknown ALPHA_HUNTER_ACTIVATION_SOURCE: {mode}")
    if mode == "LEGACY_MANUAL":
        return legacy_path, "LEGACY_MANUAL"

    if _same_snapshot_activation(adjudicated_path, run_id, "CHATGPT_CHALLENGER_ADJUDICATION"):
        return adjudicated_path, "CHATGPT_CHALLENGER_ADJUDICATION"

    if _same_snapshot_activation(v3_path, run_id, "V3_AUTONOMOUS_RESEARCH"):
        return v3_path, "V3_AUTONOMOUS_RESEARCH"

    if mode == "V3_VALIDATED":
        raise RuntimeError("Decision bridge requires same-snapshot validated adjudication or V3 research activation artifact")
    return legacy_path, "LEGACY_MANUAL_FALLBACK"


def _apply_current_activation(structural: pd.DataFrame, activations: pd.DataFrame) -> pd.DataFrame:
    """Replace any scanner-carried activation fields with the current validated activation set.

    Canonical structural_matches may contain placeholder or stale activation columns from a
    previous layer. Their mere presence must never suppress the same-snapshot write-back.
    This function strips activation-derived fields, resets causal decision state, and reapplies
    only the activation artifact selected for the current run.
    """
    x = structural.copy()
    stale_cols = [c for c in _ACTIVATION_DERIVED_COLUMNS if c in x.columns]
    if stale_cols:
        x = x.drop(columns=stale_cols)

    x["dynamic_driver_state"] = "UNRESOLVED"
    x["causal_status"] = "STRUCTURAL_MATCH_RESEARCH_REQUIRED"
    x["decision_eligible"] = False
    x["why_not_decision_eligible"] = "Dynamic causal driver has not been externally validated."

    return apply_driver_activation(x, activations)


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

    activation_path, activation_source = _activation_source_for_run(run_id)
    activations = validate_driver_activation_file(activation_path, queue, CausalConfig())
    structural = _apply_current_activation(structural, activations)

    structural = apply_edge_provenance(structural, Path("input/edge_provenance.csv"))
    structural = apply_exposure_map(structural, Path("config/decision_exposure_map.csv"))

    board, packet = write_decision_outputs(structural, run_id, "output")

    board, risk_meta = apply_portfolio_risk_gate(board)
    board, launch_meta = apply_launch_gate(board)
    board.to_csv(OUT / "decision_board.csv", index=False)
    _private_position_actions, position_meta = apply_existing_position_engine(board)

    evidence_paths = [manifest_path, activation_path, Path("input/edge_provenance.csv"), Path("config/launch_policy.json"), Path("config/frozen_strategy_v1.json")]
    sealed = seal_public_snapshot(board, run_id, launch_meta, evidence_paths)
    launch_meta["sealed_snapshot_id"] = sealed
    audit = append_shadow_audit(board, "output/shadow_audit.csv")
    validation, validation_report = write_shadow_validation(
        "output/shadow_audit.csv",
        "output/shadow_validation.csv",
        "output/shadow_validation_report.json",
    )

    accepted = int(activations.get("activation_valid", pd.Series(dtype=bool)).fillna(False).sum()) if not activations.empty else 0
    activated_driver_ids = sorted(
        activations.loc[
            activations.get("activation_valid", pd.Series(False, index=activations.index)).fillna(False)
            & activations.get("activation_state", pd.Series("UNKNOWN", index=activations.index)).astype(str).eq("ACTIVE"),
            "driver_id",
        ].astype(str).unique().tolist()
    ) if not activations.empty else []

    same_snapshot_v3 = activation_source in {"V3_AUTONOMOUS_RESEARCH", "CHATGPT_CHALLENGER_ADJUDICATION"}
    packet["activation_layer"] = {
        "source": activation_source,
        "path": str(activation_path),
        "same_snapshot_v3": same_snapshot_v3,
        "challenger_adjudicated": activation_source == "CHATGPT_CHALLENGER_ADJUDICATION",
        "accepted_activation_rows": accepted,
        "active_driver_ids": activated_driver_ids,
        "lineage_overwrite_enforced": True,
    }
    packet["launch_layer"] = launch_meta
    packet["risk_layer"] = risk_meta
    packet["existing_position_layer"] = position_meta
    packet["shadow_validation_layer"] = {
        "validation_version": validation_report.get("validation_version"),
        "matured_outcomes": validation_report.get("matured_outcomes", 0),
        "directional_scored_outcomes": validation_report.get("directional_scored_outcomes", 0),
        "directional_hit_rate": validation_report.get("directional_hit_rate"),
        "execution_assumption": validation_report.get("execution_assumption"),
        "threshold_tuning_allowed": False,
    }
    packet["current_capability"] = "V3_RESEARCH_CHALLENGER_TO_DECISION_PLUS_PRIVATE_RISK_EXIT_SHADOW_VALIDATION"
    packet["missing_downstream_modules"] = ["EXACT_PORTFOLIO_EXPOSURE_COVERAGE", "COST_ADJUSTED_OUT_OF_SAMPLE_VALIDATION", "FORWARD_ACCEPTANCE_REVIEW"]
    if not risk_meta.get("risk_inputs_valid") or not position_meta.get("position_inputs_valid"):
        packet["missing_downstream_modules"].append("PRIVATE_RISK_INPUTS_IF_NOT_CONFIGURED")
    packet["portfolio_action_counts"] = {
        str(k): int(v) for k, v in board["portfolio_action"].value_counts(dropna=False).to_dict().items()
    } if "portfolio_action" in board.columns else {}
    packet["rule"] = (
        "No score can override causal/provenance/reaction gates. Same-snapshot challenger adjudication is preferred over autonomous research; stale artifacts are never consumed. "
        "Any scanner-carried activation fields are overwritten by the selected current-run activation artifact before decisioning. "
        "Entry triggers must pass private portfolio risk before BUY. Existing positions use private thesis/risk gates for HOLD/REDUCE/EXIT. "
        "Shadow validation is ex-post only and cannot rewrite history or tune thresholds."
    )
    packet["auto_order_execution"] = False
    (OUT / "decision_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    edge_backed = int(board.get("gate_edge_source_backed", pd.Series(dtype=bool)).fillna(False).sum()) if not board.empty else 0
    risk_pass = int(board.get("risk_gate_pass", pd.Series(dtype=bool)).fillna(False).sum()) if not board.empty else 0
    print(f"Decision bridge run_id: {run_id}")
    print(f"Activation source: {activation_source}")
    print(f"Research activations accepted: {accepted}")
    print(f"Active driver ids: {activated_driver_ids}")
    print(f"Source-backed live structural rows: {edge_backed}")
    print(f"Decision board rows: {len(board)}")
    print(f"Risk-gate PASS rows: {risk_pass}")
    print(f"Action counts: {packet.get('action_counts', {})}")
    print(f"Portfolio action counts: {packet.get('portfolio_action_counts', {})}")
    print(f"Existing-position engine status: {'PASS' if position_meta.get('position_inputs_valid') else 'BLOCKED'}")
    print(f"Shadow audit rows retained: {len(audit)}")
    print(f"Shadow validation matured outcomes: {len(validation)}")
    print("No brokerage/order execution exists. Historical decisions are immutable; shadow validation never tunes thresholds or rewrites past states.")


if __name__ == "__main__":
    main()
