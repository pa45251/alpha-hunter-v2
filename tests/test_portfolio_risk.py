import json
from pathlib import Path

import pandas as pd

from portfolio_risk import apply_portfolio_risk_gate
from shadow_audit import append_shadow_audit


def triggered_board(driver_id="AI_SERVER_SHIPMENTS"):
    return pd.DataFrame([{
        "run_id": "r1",
        "decision_contract_version": "2.7.1",
        "ticker": "2317.TW",
        "taiwan_code": "2317",
        "name": "Foxconn",
        "global_theme": "AI_Server",
        "driver_id": driver_id,
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


def base_policy(**overrides):
    p = {
        "policy_version": "test",
        "max_single_position_pct": 10,
        "max_theme_exposure_pct": 30,
        "max_gross_exposure_pct": 100,
        "max_new_position_pct": 5,
        "min_avg_turnover_twd": 100000000,
        "max_position_loss_pct": 10,
    }
    p.update(overrides)
    return p


def test_missing_private_inputs_block_buy(monkeypatch):
    monkeypatch.delenv("ALPHA_HUNTER_RISK_POLICY_JSON", raising=False)
    monkeypatch.delenv("ALPHA_HUNTER_PORTFOLIO_JSON", raising=False)
    board, meta = apply_portfolio_risk_gate(triggered_board())
    assert meta["risk_inputs_valid"] is False
    assert board.iloc[0]["portfolio_action"] == "WATCH_ENTRY"
    assert board.iloc[0]["risk_gate_pass"] == False


def test_complete_legacy_private_inputs_can_pass_candidate_risk(monkeypatch):
    portfolio = {"gross_exposure_pct": 50, "positions": []}
    monkeypatch.setenv("ALPHA_HUNTER_RISK_POLICY_JSON", json.dumps(base_policy()))
    monkeypatch.setenv("ALPHA_HUNTER_PORTFOLIO_JSON", json.dumps(portfolio))
    board, meta = apply_portfolio_risk_gate(triggered_board())
    assert meta["risk_inputs_valid"] is True
    assert board.iloc[0]["risk_gate_pass"] == True
    assert board.iloc[0]["portfolio_action"] == "BUY_STOCK"


def test_market_value_schema_derives_leverage_and_blocks_when_already_over_limit(monkeypatch):
    policy = base_policy(max_gross_exposure_pct=160, max_single_position_pct=70, max_theme_exposure_pct=90)
    portfolio = {
        "cash_twd": 0,
        "market_value_twd": 27231807,
        "financing_debt_twd": 14565000,
        "gross_exposure_pct": 214.99,
        "positions": [
            {"ticker": "00757", "market_value_twd": 9342300, "risk_groups": ["AI_CAPEX"]},
            {"ticker": "00898", "market_value_twd": 10711440, "risk_groups": ["BIOTECH_RISK"]},
            {"ticker": "009821", "market_value_twd": 3045150, "risk_groups": ["CRITICAL_MATERIALS"]},
            {"ticker": "3029", "market_value_twd": 4125500, "risk_groups": ["CYBERSECURITY"]},
            {"ticker": "006208", "market_value_twd": 7417, "risk_groups": ["TAIWAN_BROAD"]},
        ],
    }
    monkeypatch.setenv("ALPHA_HUNTER_RISK_POLICY_JSON", json.dumps(policy))
    monkeypatch.setenv("ALPHA_HUNTER_PORTFOLIO_JSON", json.dumps(portfolio))
    board, meta = apply_portfolio_risk_gate(triggered_board())
    assert meta["risk_inputs_valid"] is True
    assert board.iloc[0]["portfolio_action"] == "WATCH_ENTRY"
    assert "PORTFOLIO_ALREADY_OVER_MAX_GROSS" in board.iloc[0]["risk_blockers"]
    # Exact balances/weights must not be copied into public metadata.
    assert "market_value_twd" not in meta
    assert "gross_exposure_pct" not in meta


def test_multi_group_overlap_blocks_correlated_new_buy(monkeypatch):
    policy = base_policy(max_gross_exposure_pct=200, max_single_position_pct=100, max_theme_exposure_pct=30)
    portfolio = {
        "gross_exposure_pct": 50,
        "positions": [
            {"ticker": "ETF1", "weight_pct": 28, "risk_groups": ["AI_CAPEX", "GROWTH_DURATION"]}
        ],
    }
    monkeypatch.setenv("ALPHA_HUNTER_RISK_POLICY_JSON", json.dumps(policy))
    monkeypatch.setenv("ALPHA_HUNTER_PORTFOLIO_JSON", json.dumps(portfolio))
    board, _ = apply_portfolio_risk_gate(triggered_board("AI_SERVER_SHIPMENTS"))
    assert board.iloc[0]["portfolio_action"] == "WATCH_ENTRY"
    assert "MAX_THEME_EXPOSURE" in board.iloc[0]["risk_blockers"]


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
