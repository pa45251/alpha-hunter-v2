import json
import pandas as pd

from existing_position import apply_private_thesis_overlay, evaluate_existing_positions, load_private_thesis_overlay


def policy(**overrides):
    p = {"max_position_loss_pct": 10, "max_gross_exposure_pct": 100}
    p.update(overrides)
    return p


def board(state="CONFIRMING", driver="AI_SERVER_SHIPMENTS", ticker="SYN1.TW"):
    return pd.DataFrame([{
        "ticker": ticker,
        "driver_id": driver,
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED",
        "polarity": "POSITIVE",
        "reaction_state": state,
    }])


def test_exact_ticker_system_thesis_holds_without_user_thesis():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20}]}
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["action"] == "HOLD"
    assert out.iloc[0]["thesis_mapping"] == "SYSTEM_TICKER_EXPOSURE"


def test_risk_group_system_fallback_holds():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "OTHER", "weight_pct": 20, "risk_groups": ["AI_CAPEX"]}]}
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["action"] == "HOLD"
    assert out.iloc[0]["thesis_mapping"] == "SYSTEM_RISK_GROUP"


def test_broken_system_transmission_exits_thesis():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20}]}
    out = evaluate_existing_positions(board("BROKEN"), policy(), portfolio)
    assert out.iloc[0]["action"] == "EXIT_THESIS"


def test_loss_limit_can_force_exit_without_thesis_failure():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20, "unrealized_pnl_pct": -12}]}
    out = evaluate_existing_positions(board(), policy(max_position_loss_pct=10), portfolio)
    assert out.iloc[0]["action"] == "EXIT_RISK"


def test_missing_system_mapping_never_invents_hold_or_exit():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "UNKNOWN", "weight_pct": 20}]}
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["action"] == "REVIEW_RESEARCH"
    assert out.iloc[0]["reason"] == "SYSTEM_EXPOSURE_MAPPING_MISSING"


def test_over_gross_nominates_weakest_non_exit_for_reduction():
    portfolio = {"gross_exposure_pct": 120, "positions": [
        {"ticker": "UNKNOWN", "weight_pct": 25},
        {"ticker": "SYN1", "weight_pct": 30},
    ]}
    out = evaluate_existing_positions(board(), policy(max_gross_exposure_pct=100), portfolio)
    assert out.iloc[0]["action"] == "REDUCE_RISK"
    assert out.iloc[1]["action"] == "HOLD"


def test_user_invalidation_is_challenger_not_authority(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_THESIS_JSON", json.dumps({"positions": [
        {"ticker": "SYN1.TW", "thesis_driver_ids": ["AI_SERVER_SHIPMENTS"], "thesis_status": "INVALIDATED"}
    ]}))
    overlay, status = load_private_thesis_overlay()
    assert status == "VALID"
    portfolio, applied = apply_private_thesis_overlay({"positions": [{"ticker": "SYN1", "weight_pct": 20}]}, overlay)
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert applied == 1
    assert out.iloc[0]["action"] == "HOLD"
    assert bool(out.iloc[0]["user_thesis_disagrees"])


def test_user_driver_disagreement_does_not_replace_system_mapping(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_THESIS_JSON", json.dumps({"positions": [
        {"ticker": "SYN1.TW", "thesis_driver_ids": ["CONTAINER_FREIGHT"], "thesis_status": "ACTIVE"}
    ]}))
    overlay, _ = load_private_thesis_overlay()
    portfolio, _ = apply_private_thesis_overlay({"positions": [{"ticker": "SYN1", "weight_pct": 20}]}, overlay)
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["thesis_mapping"] == "SYSTEM_TICKER_EXPOSURE"
    assert out.iloc[0]["action"] == "HOLD"
    assert bool(out.iloc[0]["user_thesis_disagrees"])


def test_malformed_private_thesis_overlay_is_detected(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_THESIS_JSON", "{not-json")
    overlay, status = load_private_thesis_overlay()
    assert overlay == {}
    assert status == "INVALID_JSON"
