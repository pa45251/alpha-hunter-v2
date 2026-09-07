import pandas as pd
import pytest

from causal_activation_v2 import apply_driver_activation_v2, normalized_driver_state


def _structural():
    return pd.DataFrame([
        {"driver_id": "D1", "ticker": "A.TW", "dynamic_driver_state": "UNRESOLVED", "causal_status": "STRUCTURAL_MATCH_RESEARCH_REQUIRED"},
        {"driver_id": "D2", "ticker": "B.TW", "dynamic_driver_state": "UNRESOLVED", "causal_status": "STRUCTURAL_MATCH_RESEARCH_REQUIRED"},
        {"driver_id": "D3", "ticker": "C.TW", "dynamic_driver_state": "UNRESOLVED", "causal_status": "STRUCTURAL_MATCH_RESEARCH_REQUIRED"},
    ])


def test_active_inactive_unknown_are_explicitly_propagated():
    activations = pd.DataFrame([
        {"driver_id": "D1", "activation_state": "ACTIVE", "activation_valid": True},
        {"driver_id": "D2", "activation_state": "INACTIVE", "activation_valid": True},
        {"driver_id": "D3", "activation_state": "UNKNOWN", "activation_valid": True},
    ])
    out = apply_driver_activation_v2(_structural(), activations).set_index("driver_id")
    assert normalized_driver_state(out.loc["D1", "dynamic_driver_state"]) == "ACTIVE"
    assert normalized_driver_state(out.loc["D2", "dynamic_driver_state"]) == "INACTIVE"
    assert normalized_driver_state(out.loc["D3", "dynamic_driver_state"]) == "UNKNOWN"
    assert "inactive" in out.loc["D2", "why_not_decision_eligible"].lower()


def test_invalid_activation_does_not_override_unresolved_state():
    activations = pd.DataFrame([
        {"driver_id": "D1", "activation_state": "ACTIVE", "activation_valid": False},
    ])
    out = apply_driver_activation_v2(_structural(), activations).set_index("driver_id")
    assert out.loc["D1", "dynamic_driver_state"] == "UNRESOLVED"


def test_duplicate_driver_activation_is_rejected():
    activations = pd.DataFrame([
        {"driver_id": "D1", "activation_state": "ACTIVE", "activation_valid": True},
        {"driver_id": "D1", "activation_state": "INACTIVE", "activation_valid": True},
    ])
    with pytest.raises(ValueError, match="DUPLICATE_DRIVER_ACTIVATION_V2"):
        apply_driver_activation_v2(_structural(), activations)
