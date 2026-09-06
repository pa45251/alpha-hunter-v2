from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd


AUDIT_COLUMNS = [
    "audit_at_utc", "run_id", "decision_contract_version", "ticker", "taiwan_code", "name",
    "global_theme", "driver_id", "dynamic_driver_state", "provenance_status", "reaction_state",
    "previous_reaction_state", "entry_trigger_state", "stock_vs_etf_state", "candidate_action",
    "portfolio_action", "risk_gate_pass", "decision_blockers", "risk_blockers",
    "strategy_version", "deployment_mode", "live_execution_authorized", "execution_action"
]


def append_shadow_audit(board: pd.DataFrame, path: str = "output/shadow_audit.csv") -> pd.DataFrame:
    """Append public, non-sensitive point-in-time decision states.

    No portfolio weights, capital amounts, or personal holdings are written here.
    """
    if board is None or board.empty:
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    x = board.copy()
    x["audit_at_utc"] = datetime.now(timezone.utc).isoformat()
    for c in AUDIT_COLUMNS:
        if c not in x.columns:
            x[c] = ""
    x = x[AUDIT_COLUMNS]

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        try:
            old = pd.read_csv(p, dtype={"taiwan_code": str})
            x = pd.concat([old, x], ignore_index=True)
        except Exception as exc:
            raise RuntimeError("Existing shadow audit unreadable; refusing to overwrite") from exc
    for c in ["run_id", "ticker", "driver_id", "candidate_action", "portfolio_action", "strategy_version"]:
        x[c] = x[c].fillna("")
    x = x.drop_duplicates(subset=["run_id", "ticker", "driver_id", "candidate_action", "portfolio_action", "strategy_version"], keep="first")
    x.to_csv(p, index=False)
    return x


def seal_public_snapshot(board, run_id, launch_meta, evidence_paths, path="output/shadow_journal.jsonl"):
    """Append-only public evidence; private position actions are never accepted here."""
    payload = {
        "run_id": run_id, "strategy_version": launch_meta["strategy_version"],
        "deployment_mode": "SHADOW", "live_execution_authorized": False,
        "freeze_integrity_pass": launch_meta.get("freeze_integrity_pass", False),
        "signals": json.loads(board[[c for c in AUDIT_COLUMNS if c in board]].to_json(orient="records")),
        "public_evidence": {str(p): p.read_text(encoding="utf-8") for p in evidence_paths if p.exists()},
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    snapshot_id = hashlib.sha256(encoded.encode()).hexdigest()
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with p.open(encoding="utf-8") as handle:
            for line in handle:
                if json.loads(line).get("snapshot_id") == snapshot_id:
                    return snapshot_id
    row = {"snapshot_id": snapshot_id, "sealed_at_utc": datetime.now(timezone.utc).isoformat(), **payload}
    with p.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return snapshot_id
