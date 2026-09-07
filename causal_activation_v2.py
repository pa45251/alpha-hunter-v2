from __future__ import annotations

from typing import Any

import pandas as pd

CONTRACT = "ALPHA_HUNTER_CAUSAL_ACTIVATION_V2"

STATE_MAP = {
    "ACTIVE": ("ACTIVE_RESEARCH_VALIDATED", "ACTIVATED_HYPOTHESIS_REQUIRES_FINAL_AUDIT"),
    "INACTIVE": ("INACTIVE_RESEARCH_VALIDATED", "DRIVER_RESEARCH_VALIDATED_INACTIVE"),
    "UNKNOWN": ("UNKNOWN_RESEARCH_VALIDATED", "DRIVER_RESEARCH_VALIDATED_UNKNOWN"),
}


def apply_driver_activation_v2(structural_matches: pd.DataFrame, activations: pd.DataFrame) -> pd.DataFrame:
    """Apply valid ACTIVE/INACTIVE/UNKNOWN states without changing frozen causal_engine.py.

    V1 only wrote ACTIVE back to structural rows. V2 makes INACTIVE and UNKNOWN explicit so
    downstream exit/avoid logic cannot confuse 'not written' with 'not researched'.
    """
    if structural_matches is None or structural_matches.empty:
        return structural_matches
    x = structural_matches.copy()
    if activations is None or activations.empty:
        return x

    cols = [
        "driver_id", "activation_state", "activation_confidence", "activation_valid",
        "as_of_utc", "source_count", "primary_cause", "counter_evidence", "source_summary"
    ]
    cols = [c for c in cols if c in activations.columns]
    a = activations[cols].copy()
    if "driver_id" not in a.columns:
        return x

    # Duplicate driver activations are a contract error; silently multiplying rows is unsafe.
    if a["driver_id"].astype(str).duplicated().any():
        raise ValueError("DUPLICATE_DRIVER_ACTIVATION_V2")

    x = x.merge(a, on="driver_id", how="left", validate="many_to_one")
    valid = x.get("activation_valid", False)
    if not isinstance(valid, pd.Series):
        valid = pd.Series(False, index=x.index)
    valid = valid.fillna(False).astype(bool)
    states = x.get("activation_state", pd.Series("", index=x.index)).fillna("").astype(str).str.upper()

    for source_state, (dynamic_state, causal_status) in STATE_MAP.items():
        mask = valid & states.eq(source_state)
        x.loc[mask, "dynamic_driver_state"] = dynamic_state
        x.loc[mask, "causal_status"] = causal_status
        if source_state == "ACTIVE":
            x.loc[mask, "why_not_decision_eligible"] = "Requires downstream final audit; activation is research evidence, not a trade signal."
        elif source_state == "INACTIVE":
            x.loc[mask, "why_not_decision_eligible"] = "Validated driver is inactive; long entry is blocked and existing-position thesis should be reviewed."
        else:
            x.loc[mask, "why_not_decision_eligible"] = "Validated research remains unknown; no causal trade permission."
    return x


def normalized_driver_state(value: Any) -> str:
    v = str(value or "").upper()
    if v == "ACTIVE_RESEARCH_VALIDATED":
        return "ACTIVE"
    if v == "INACTIVE_RESEARCH_VALIDATED":
        return "INACTIVE"
    if v in {"UNKNOWN_RESEARCH_VALIDATED", "UNRESOLVED", ""}:
        return "UNKNOWN"
    return "STALE_OR_INVALID"
