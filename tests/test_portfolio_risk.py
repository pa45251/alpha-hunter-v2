import json
from pathlib import Path

import pandas as pd

from portfolio_risk import apply_portfolio_risk_gate
from shadow_audit import append_shadow_audit


def triggered_board():
    return pd.DataFrame([{
        "run_id": "r1",
        "decision_contract_version": "2.7.1",
        "ticker": "2317.TW",
        "taiwan_code": "2317",
        "name": "Foxconn",
        "global_theme": "AI_Server",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED",
        "reaction_state": "CONFIRMING",
        "previous_reaction_state": "PRE_CONFIRMATION",
        "entry_trigger_state": "BREAKOUT_CONFIRMATION_TRIGGER",
        "stock_vs_etf_state": "STOCK_ALPHA_RESEARCH",
        "candidate_action": "ENTRY_TRIGGERED_STOCK_RISK_PENDING",
        "decision_blockers": "PORTFOLIO_RISK_NOT_YET_VALIDATED",
        "avg_turnover20_twd": 1_000_000_000,
    }])


def test_missing_private_inputs_block_buy(monkeypatch):
    monkeypatch.delenv("ALPHA_HUNTER_RISK_POLICY_JSON", raising=False)
    monkeypatch.delenv("ALPHA_HUNTER_PORTFOLIO_JSON", raising=False)
    board, meta = apply_portfolio_risk_gate(triggered_board())
    assert meta["risk_inputs_valid"] is False
    assert board.iloc[0]["portfolio_action"] == "WATCH_ENTRY"
    assert board.iloc[0]["risk_gate_pass"] == False


def test_complete_private_inputs_can_pass_candidate_risk(monkeypatch):
    policy = {
        "policy_version": "test",
        "max_single_position_pct": 10,
        "max_theme_exposure_pct": 30,
        "max_gross_exposure_pct": 100,
        "max_new_position_pct": 5,
        "min_avg_turnover_twd": 100000000,
        "max_position_loss_pct": 10
    }
    portfolio = {"gross_exposure_pct": 50, "positions": []}
    monkeypatch.setenv("ALPHA_HUNTER_RISK_POLICY_JSON", json.dumps(policy))
    monkeypatch.setenv("ALPHA_HUNTER_PORTFOLIO_JSON", json.dumps(portfolio))
    board, meta = apply_portfolio_risk_gate(triggered_board())
    assert meta["risk_inputs_valid"] is True
    assert board.iloc[0]["risk_gate_pass"] == True
    assert board.iloc[0]["portfolio_action"] == "BUY_STOCK"


def test_shadow_audit_does_not_require_private_portfolio_fields(tmp_path: Path):
    p = tmp_path / "audit.csv"
    board = triggered_board()
    board["portfolio_action"] = "WATCH_ENTRY"
    board["risk_gate_pass"] = False
    board["risk_blockers"] = "RISK_POLICY_MISSING"
    audit = append_shadow_audit(board, str(p))
    assert len(audit) == 1
    assert "weight_pct" not in audit.columns
    assert "capital" not in audit.columns
