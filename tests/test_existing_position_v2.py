import pandas as pd

from existing_position_v2 import evaluate_existing_positions


def policy(**overrides):
    p = {"max_position_loss_pct": 10, "max_gross_exposure_pct": 100}
    p.update(overrides)
    return p


def board(state="CONFIRMING", ticker="SYN1.TW"):
    return pd.DataFrame([{
        "ticker": ticker,
        "driver_id": "AI_SERVER_SHIPMENTS",
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED",
        "polarity": "POSITIVE",
        "reaction_state": state,
    }])


def test_broken_active_driver_requires_review_not_exit():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20}]}
    out = evaluate_existing_positions(board("BROKEN"), policy(), portfolio)
    assert out.iloc[0]["action"] == "REVIEW_RESEARCH"
    assert out.iloc[0]["reason"] == "SYSTEM_THESIS_TRANSMISSION_BROKEN_REQUIRES_PERSISTENCE_CONFIRMATION"


def test_causal_inactive_still_exits():
    b = board("CONFIRMING")
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20}]}
    out = evaluate_existing_positions(b, policy(), portfolio, {"AI_SERVER_SHIPMENTS": "INACTIVE"})
    assert out.iloc[0]["action"] == "EXIT_THESIS"


def test_loss_limit_still_exits():
    portfolio = {"gross_exposure_pct": 80, "positions": [{"ticker": "SYN1", "weight_pct": 20, "unrealized_pnl_pct": -12}]}
    out = evaluate_existing_positions(board(), policy(), portfolio)
    assert out.iloc[0]["action"] == "EXIT_RISK"


def test_broken_review_can_still_be_selected_for_portfolio_risk_reduction():
    portfolio = {"gross_exposure_pct": 120, "positions": [
        {"ticker": "SYN1", "weight_pct": 25},
        {"ticker": "SYN2", "weight_pct": 30},
    ]}
    b = pd.concat([board("BROKEN", "SYN1.TW"), board("CONFIRMING", "SYN2.TW")], ignore_index=True)
    out = evaluate_existing_positions(b, policy(max_gross_exposure_pct=100), portfolio)
    assert out.iloc[0]["action"] == "REDUCE_RISK"
    assert out.iloc[0]["reason"] == "PORTFOLIO_GROSS_EXPOSURE_ABOVE_POLICY"
    assert out.iloc[1]["action"] == "HOLD"
