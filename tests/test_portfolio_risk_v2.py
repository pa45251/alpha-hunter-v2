import json
import math

import pandas as pd

from portfolio_risk_v2 import apply_entry_risk_gate_v2, validate_risk_inputs_v2


def _policy(**overrides):
    p = {
        "policy_version": "v2-test",
        "max_single_position_pct": 100,
        "max_theme_exposure_pct": 100,
        "max_gross_exposure_pct": 200,
        "max_new_position_pct": 3,
        "min_avg_turnover_twd": 100_000_000,
        "max_position_loss_pct": 10,
    }
    p.update(overrides)
    return p


def _portfolio(**overrides):
    p = {"gross_exposure_pct": 50, "positions": []}
    p.update(overrides)
    return p


def _plan(turnover=1_000_000_000):
    return pd.DataFrame([{
        "ticker": "2317.TW",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "entry_structure_valid": True,
        "avg_turnover20_twd": turnover,
    }])


def test_nan_gross_exposure_is_invalid_input():
    valid, blockers, _ = validate_risk_inputs_v2(_policy(), _portfolio(gross_exposure_pct=float("nan")))
    assert valid is False
    assert "PORTFOLIO_FIELD_NONFINITE:gross_exposure_pct" in blockers


def test_nonfinite_policy_value_is_invalid_input():
    valid, blockers, _ = validate_risk_inputs_v2(_policy(max_gross_exposure_pct=float("inf")), _portfolio())
    assert valid is False
    assert "RISK_POLICY_FIELD_NONFINITE:max_gross_exposure_pct" in blockers


def test_missing_zero_nan_and_inf_turnover_all_fail_closed(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RISK_POLICY_JSON", json.dumps(_policy()))
    monkeypatch.setenv("ALPHA_HUNTER_PORTFOLIO_JSON", json.dumps(_portfolio()))
    for turnover in [None, 0, float("nan"), float("inf")]:
        board = _plan(turnover)
        if turnover is None:
            board = board.drop(columns=["avg_turnover20_twd"])
        out, _ = apply_entry_risk_gate_v2(board)
        assert bool(out.iloc[0]["risk_v2_pass"]) is False
        assert "LIQUIDITY_DATA_MISSING_OR_INVALID" in out.iloc[0]["risk_v2_blockers"]


def test_complete_finite_inputs_and_liquidity_can_pass(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RISK_POLICY_JSON", json.dumps(_policy()))
    monkeypatch.setenv("ALPHA_HUNTER_PORTFOLIO_JSON", json.dumps(_portfolio()))
    out, meta = apply_entry_risk_gate_v2(_plan())
    assert meta["risk_inputs_valid"] is True
    assert bool(out.iloc[0]["risk_v2_pass"]) is True
    assert out.iloc[0]["risk_v2_blockers"] == ""
