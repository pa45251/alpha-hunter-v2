from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from causal_engine import CausalConfig, validate_driver_activation_file
from decision_engine import apply_edge_provenance, apply_exposure_map
from decision_run import _activation_source_for_run, _apply_current_activation
from decision_state_v2 import write_decision_outputs_v2
from launch_gate import apply_launch_gate
from shadow_audit import seal_public_snapshot
from shadow_audit_v2 import append_shadow_audit_v2
from snapshot_lineage_v2 import assert_decision_snapshot_current, build_public_lineage_id

OUT = Path("output")
CONTRACT = "ALPHA_HUNTER_DECISION_BRIDGE_V2"


def main() -> None:
    gate_path = OUT / "gate_report.json"
    manifest_path = OUT / "manifest.json"
    queue_path = OUT / "causal_research_queue.csv"
    structural_path = OUT / "structural_matches.csv"

    required = [gate_path, manifest_path, queue_path, structural_path]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"Decision V2 missing canonical inputs: {missing}")

    # P0 lineage guard: a previously persisted PASS is never treated as a durable permission.
    # Recompute hashes/freshness immediately before decisioning and require exact manifest lineage.
    lineage_meta = assert_decision_snapshot_current(OUT)

    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", ""))
    if not run_id or str(gate.get("run_id", "")) != run_id:
        raise RuntimeError("Decision V2 MIXED_SNAPSHOT_DATA: manifest/gate run_id mismatch")

    queue = pd.read_csv(queue_path)
    structural = pd.read_csv(structural_path, dtype={"taiwan_code": str})
    for name, df in [("causal_research_queue", queue), ("structural_matches", structural)]:
        if "run_id" not in df.columns or df.empty or not df["run_id"].astype(str).eq(run_id).all():
            raise RuntimeError(f"Decision V2 MIXED_SNAPSHOT_DATA: {name} run_id mismatch")

    activation_path, activation_source = _activation_source_for_run(run_id)
    activations = validate_driver_activation_file(activation_path, queue, CausalConfig())
    structural = _apply_current_activation(structural, activations)
    structural = apply_edge_provenance(structural, Path("input/edge_provenance.csv"))
    structural = apply_exposure_map(structural, Path("config/decision_exposure_map.csv"))

    board, packet = write_decision_outputs_v2(structural, run_id, "output")
    board, launch_meta = apply_launch_gate(board)


    evidence_paths = [
        manifest_path,
        gate_path,
        activation_path,
        Path("input/edge_provenance.csv"),
        Path("config/decision_exposure_map.csv"),
        Path("config/launch_policy.json"),
        Path("config/frozen_strategy_v1.json"),
    ]
    public_lineage_id, public_hashes = build_public_lineage_id(run_id, evidence_paths)
    board["public_lineage_id"] = public_lineage_id
    board.to_csv(OUT / "decision_board.csv", index=False)

    sealed = seal_public_snapshot(board, run_id, launch_meta, evidence_paths)
    launch_meta["sealed_snapshot_id"] = sealed

    # Historical outcome evaluation is offline; it must not download prices in Daily Core.
    audit = pd.DataFrame()
    validation = pd.DataFrame()
    validation_report = {"status": "UNAVAILABLE", "future_data_cutoff_enforced": False}
    try:
        audit = append_shadow_audit_v2(board, "output/shadow_audit.csv")
    except Exception as exc:
        # Research outcome scoring must never suppress today's guarded decisions.
        for name in ["shadow_validation.csv", "shadow_validation_report.json"]:
            (OUT / name).unlink(missing_ok=True)
        print(f"WARNING: optional shadow validation failed: {type(exc).__name__}")

    accepted = int(activations.get("activation_valid", pd.Series(dtype=bool)).fillna(False).sum()) if not activations.empty else 0
    activated_driver_ids = sorted(
        activations.loc[
            activations.get("activation_valid", pd.Series(False, index=activations.index)).fillna(False)
            & activations.get("activation_state", pd.Series("UNKNOWN", index=activations.index)).astype(str).eq("ACTIVE"),
            "driver_id",
        ].astype(str).unique().tolist()
    ) if not activations.empty else []

    same_snapshot_v3 = activation_source in {"V3_AUTONOMOUS_RESEARCH", "CHATGPT_CHALLENGER_ADJUDICATION"}
    packet["decision_bridge"] = {
        "contract": CONTRACT,
        "public_lineage_id": public_lineage_id,
        "canonical_snapshot_revalidated_immediately_before_decision": True,
        "persisted_gate_reused_without_revalidation": False,
        "mixed_snapshot_allowed": False,
        "public_evidence_hash_count": len(public_hashes),
    }
    packet["snapshot_lineage_layer"] = lineage_meta
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
    packet["shadow_validation_layer"] = {
        "validation_version": validation_report.get("validation_version"),
        "matured_outcomes": validation_report.get("matured_outcomes", 0),
        "directional_scored_outcomes": validation_report.get("directional_scored_outcomes", 0),
        "directional_hit_rate": validation_report.get("directional_hit_rate"),
        "execution_assumption": validation_report.get("execution_assumption"),
        "future_data_cutoff_enforced": validation_report.get("future_data_cutoff_enforced", False),
        "threshold_tuning_allowed": False,
    }
    packet["current_capability"] = "MARKET_OPPORTUNITY_ONLY"
    packet["missing_downstream_modules"] = [
        "COST_ADJUSTED_OUT_OF_SAMPLE_VALIDATION",
        "FORWARD_ACCEPTANCE_REVIEW",
    ]
    packet["rule"] = (
        "No score can override causal/provenance/reaction gates. Canonical hashes/freshness are revalidated immediately before decisioning. "
        "Previous state must come from a strictly earlier Taiwan market session, so same-session reruns cannot consume triggers. "
        "Identical same-session shadow decisions are one prospective observation. Personal holdings never affect market decisions. "
        "Shadow outcomes can mature only from fully closed market sessions available by the evaluation cutoff. "
        "No brokerage/order execution exists and threshold tuning from prospective outcomes is forbidden."
    )
    packet["auto_order_execution"] = False
    (OUT / "decision_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    edge_backed = int(board.get("gate_edge_source_backed", pd.Series(dtype=bool)).fillna(False).sum()) if not board.empty else 0
    print(f"Decision V2 run_id: {run_id}")
    print(f"Public lineage id: {public_lineage_id}")
    print(f"Activation source: {activation_source}")
    print(f"Research activations accepted: {accepted}")
    print(f"Active driver ids: {activated_driver_ids}")
    print(f"Source-backed live structural rows: {edge_backed}")
    print(f"Decision board rows: {len(board)}")
    print(f"Shadow audit rows retained: {len(audit)}")
    print(f"Shadow validation matured outcomes: {len(validation)}")
    print("Prospective V2 guard active: no mixed snapshot, no same-session trigger consumption, no future daily-bar maturation.")


if __name__ == "__main__":
    main()
