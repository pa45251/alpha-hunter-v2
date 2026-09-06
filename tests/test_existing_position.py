import json
import pandas as pd

from existing_position import apply_private_thesis_overlay, evaluate_existing_positions, load_private_thesis_overlay


def policy(**overrides):
    p = {"max_position_loss_pct": 10, "max_gross_exposure_pct": 100}
    p.update(overrides)
    return p


def board(state="CONFIRMING", driver="AI_SERVER_SHIPMENTS"):
    return pd.DataFrame([{
        "driver_id": driver,
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED",
        "polarity": "POSITIVE",
        "reaction_state": state,
    }])


def test_active_source_backed_thesis_holds():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20, "risk_groups": ["AI_CAPEX"]}]}
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["action"] == "HOLD"
    assert out.iloc[0]["thesis_mapping"] == "RISK_GROUP_INFERRED"


def test_broken_transmission_exits_thesis():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20, "thesis_driver_ids": ["AI_SERVER_SHIPMENTS"]}]}
    out = evaluate_existing_positions(board("BROKEN"), policy(), portfolio)
    assert out.iloc[0]["action"] == "EXIT_THESIS"


def test_loss_limit_can_force_exit_without_price_signal():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20, "risk_groups": ["AI_CAPEX"], "unrealized_pnl_pct": -12}]}
    out = evaluate_existing_positions(board(), policy(max_position_loss_pct=10), portfolio)
    assert out.iloc[0]["action"] == "EXIT_RISK"


def test_missing_thesis_mapping_never_invents_exit():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20}]}
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["action"] == "REVIEW_THESIS"


def test_over_gross_nominates_weakest_non_exit_for_reduction():
    portfolio = {"gross_exposure_pct": 120, "positions": [
        {"ticker": "SYN1", "weight_pct": 25},
        {"ticker": "SYN2", "weight_pct": 30, "risk_groups": ["AI_CAPEX"]},
    ]}
    out = evaluate_existing_positions(board(), policy(max_gross_exposure_pct=100), portfolio)
    assert out.iloc[0]["action"] == "REDUCE_RISK"
    assert out.iloc[1]["action"] == "HOLD"


def test_explicit_private_invalidation_has_priority():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20, "risk_groups": ["AI_CAPEX"], "thesis_status": "INVALIDATED"}]}
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["action"] == "EXIT_THESIS"


def test_private_thesis_overlay_upgrades_inferred_mapping_to_explicit(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_THESIS_JSON", json.dumps({"positions": [
        {"ticker": "SYN1.TW", "thesis_driver_ids": ["AI_SERVER_SHIPMENTS"], "thesis_status": "ACTIVE"}
    ]}))
    overlay, status = load_private_thesis_overlay()
    assert status == "VALID"
    portfolio, applied = apply_private_thesis_overlay(
        {"positions": [{"ticker": "SYN1", "weight_pct": 20, "risk_groups": ["AI_CAPEX"]}]}, overlay
    )
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert applied == 1
    assert out.iloc[0]["thesis_mapping"] == "EXPLICIT"
    assert out.iloc[0]["action"] == "HOLD"


def test_malformed_private_thesis_overlay_is_detected(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_THESIS_JSON", "{not-json")
    overlay, status = load_private_thesis_overlay()
    assert overlay == {}
    assert status == "INVALID_JSON"
