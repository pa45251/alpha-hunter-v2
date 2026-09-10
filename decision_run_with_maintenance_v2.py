"""Guarded V2 decision entrypoint with ephemeral portfolio-maintenance research."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path

import decision_run_v2
import risk_regime
from existing_position_v2 import apply_existing_position_engine as _base_existing_position_engine
from portfolio_maintenance_research import private_board_overlay


def _aggregate_private_states(run_id: str) -> dict[str, int]:
    path = Path(os.getenv("ALPHA_HUNTER_MAINTENANCE_RESEARCH_PATH", "/tmp/portfolio_maintenance_result.json"))
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if str(payload.get("research_run_id", "")) != str(run_id):
        return {}
    counts = Counter(
        str(r.get("state", "UNKNOWN")).upper()
        for r in (payload.get("results") or [])
        if isinstance(r, dict)
    )
    return {k: int(v) for k, v in counts.items() if k in {"ACTIVE", "INACTIVE", "UNKNOWN"}}


def _maintenance_existing_position_engine(board):
    manifest = json.loads(Path("output/manifest.json").read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", ""))
    private_board, maintenance_meta = private_board_overlay(board, run_id)
    maintenance_meta = dict(maintenance_meta or {})
    maintenance_meta["maintenance_state_counts"] = _aggregate_private_states(run_id)
    actions, position_meta = _base_existing_position_engine(private_board)
    position_meta = dict(position_meta or {})
    position_meta["maintenance_research"] = maintenance_meta
    return actions, position_meta


def _rebuild_same_snapshot_risk_regime() -> None:
    manifest_path = Path("output/manifest.json")
    if not manifest_path.exists():
        raise RuntimeError("RISK_REGIME_CANONICAL_MANIFEST_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise RuntimeError("RISK_REGIME_CANONICAL_MANIFEST_NOT_PASS")
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise RuntimeError("RISK_REGIME_CANONICAL_RUN_ID_MISSING")

    payload = risk_regime.build_risk_regime()
    if payload.get("status") != "READY":
        raise RuntimeError(f"RISK_REGIME_NOT_READY:{payload.get('status')}")
    if str(payload.get("source_run_id") or "") != run_id:
        raise RuntimeError("RISK_REGIME_LINEAGE_MISMATCH_AFTER_REBUILD")

    out = Path("output")
    out.mkdir(parents=True, exist_ok=True)
    (out / "risk_regime.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "Risk regime rebuilt for canonical snapshot: "
        f"run_id={run_id} regime={payload.get('regime')} score={payload.get('risk_score')}"
    )


def main() -> None:
    decision_run_v2.apply_existing_position_engine = _maintenance_existing_position_engine
    decision_run_v2.main()
    # The autonomous research workflow publishes position CIO immediately after this
    # entrypoint. Always rebuild the risk overlay here so that the CIO cannot consume
    # a previous snapshot's risk_regime.json. Fail closed if same-snapshot rebuild fails.
    _rebuild_same_snapshot_risk_regime()


if __name__ == "__main__":
    main()
