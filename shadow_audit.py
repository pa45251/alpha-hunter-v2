from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import pandas as pd


AUDIT_COLUMNS = [
    "audit_at_utc", "run_id", "decision_contract_version", "ticker", "taiwan_code", "name",
    "global_theme", "driver_id", "dynamic_driver_state", "provenance_status", "reaction_state",
    "previous_reaction_state", "entry_trigger_state", "stock_vs_etf_state", "candidate_action",
    "portfolio_action", "risk_gate_pass", "decision_blockers", "risk_blockers"
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
        except Exception:
            pass
    x = x.drop_duplicates(subset=["run_id", "ticker", "driver_id", "candidate_action", "portfolio_action"], keep="last")
    x.to_csv(p, index=False)
    return x
