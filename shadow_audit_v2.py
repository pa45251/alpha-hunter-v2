from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from shadow_audit import AUDIT_COLUMNS as LEGACY_AUDIT_COLUMNS

CONTRACT = "ALPHA_HUNTER_SHADOW_AUDIT_V2"
AUDIT_COLUMNS_V2 = [*LEGACY_AUDIT_COLUMNS, "decision_session", "public_lineage_id"]


def _audit_session(row: pd.Series) -> str:
    raw = str(row.get("decision_session", "") or "").strip()
    if raw and raw.lower() != "nan":
        try:
            return pd.Timestamp(raw).date().isoformat()
        except Exception:
            pass
    try:
        ts = pd.to_datetime(row.get("audit_at_utc"), utc=True, errors="coerce")
        if pd.isna(ts):
            return ""
        return pd.Timestamp(ts).tz_convert("Asia/Taipei").date().isoformat()
    except Exception:
        return ""


def append_shadow_audit_v2(board: pd.DataFrame, path: str = "output/shadow_audit.csv") -> pd.DataFrame:
    """Append public point-in-time decisions with market-session identity.

    Identical decisions produced by repeated runs of the same closed Taiwan session are retained as
    one prospective sample. Materially different same-session decisions are not silently collapsed.
    No private position values, weights, aliases or P/L are written.
    """
    if board is None or board.empty:
        return pd.DataFrame(columns=AUDIT_COLUMNS_V2)

    x = board.copy()
    x["audit_at_utc"] = datetime.now(timezone.utc).isoformat()
    for c in AUDIT_COLUMNS_V2:
        if c not in x.columns:
            x[c] = ""
    x = x[AUDIT_COLUMNS_V2]
    x["decision_session"] = x.apply(_audit_session, axis=1)

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        try:
            old = pd.read_csv(p, dtype={"taiwan_code": str})
        except Exception as exc:
            raise RuntimeError("Existing shadow audit unreadable; refusing to overwrite") from exc
        for c in AUDIT_COLUMNS_V2:
            if c not in old.columns:
                old[c] = ""
        old = old[AUDIT_COLUMNS_V2]
        old["decision_session"] = old.apply(_audit_session, axis=1)
        x = pd.concat([old, x], ignore_index=True)

    for c in [
        "decision_session", "ticker", "driver_id", "candidate_action", "portfolio_action",
        "strategy_version", "public_lineage_id",
    ]:
        x[c] = x[c].fillna("").astype(str)

    # Same-session reruns that reproduce the same public decision are one prospective observation.
    # A changed action/status remains a separate event and keeps its own audit timestamp.
    dedupe = [
        "decision_session", "ticker", "driver_id", "candidate_action", "portfolio_action",
        "strategy_version",
    ]
    x = x.sort_values("audit_at_utc").drop_duplicates(dedupe, keep="first")
    x.to_csv(p, index=False)
    return x
