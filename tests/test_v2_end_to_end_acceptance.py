import json

import numpy as np
import pandas as pd

import global_alignment_v2 as ga
from entry_plan_run_v2 import build_canonical_plans
from portfolio_allocation_v2 import build_portfolio_allocation_v2
from entry_action_board_v2 import build_block


def _history():
    # Deterministic synthetic history: a stable rise followed by a tight 20-session base.
    idx = pd.bdate_range("2026-01-02", periods=100)
    first = np.linspace(80, 100, 79)
    base = np.array([100.0 + 0.15 * np.sin(i) for i in range(20)])
    current = np.array([100.1])
    close = np.concatenate([first, base, current])
    high = close + 0.45
    low = close - 0.45
    volume = np.full(len(close), 2_000_000.0)
    return pd.DataFrame({
        "Open": close - 0.05, "High": high, "Low": low, "Close": close, "Volume": volume,
    }, index=idx)


def _board():
    return pd.DataFrame([{
        "run_id": "R-V2", "ticker": "2317.TW", "name": "SYN-HONHAI",
        "global_theme": "AI_Server", "driver_id": "AI_SERVER_SHIPMENTS",
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED", "polarity": "POSITIVE",
        "reaction_state": "PRE_CONFIRMATION", "linkage_confidence": 0.95,
        "rs_20d_vs_bench": -0.01, "rs_60d_vs_bench": 0.05,
        "acceleration": 0.03, "keynes_v2": 0.20,
        "research_priority_score": 0.80,
    }])


def _breadth():
    return pd.DataFrame([{
        "theme": "AI_Server", "n": 6, "breadth_eligible": True,
        "above_ma20_pct": 0.83, "above_ma60_pct": 0.83,
        "positive_rs5_pct": 0.67, "positive_rs20_pct": 0.83,
        "near_20d_high_pct": 0.67, "near_52w_high_pct": 0.50,
        "breadth_confidence": "HIGH", "median_rs20": 0.08,
    }])


def _policy():
    return {
        "policy_version": "v2-acceptance",
        "max_single_position_pct": 100,
        "max_theme_exposure_pct": 100,
        "max_gross_exposure_pct": 200,
        "max_new_position_pct": 3,
        "min_avg_turnover_twd": 100_000_000,
        "max_position_loss_pct": 10,
    }


def _rotation_policy():
    return {
        "rotation": {
            "min_edge_spread": 0.18, "strong_edge_spread": 0.35,
            "max_source_trim_pct": {"RISK_ON": 50, "UNKNOWN": 0},
            "redeploy_pct_of_trim": {"RISK_ON": 100, "UNKNOWN": 0},
        }
    }


def test_v2_chain_uses_one_driver_one_plan_and_never_auto_executes(monkeypatch):
    board = _board()
    alignment = ga.build_global_alignment_v2(board, _breadth())
    assert len(alignment) == 1
    ar = alignment.iloc[0]
    assert bool(ar["alignment_eligible"])
    assert ar["driver_id"] == "AI_SERVER_SHIPMENTS"
    assert bool(ar["score_is_probability"]) is False

    monkeypatch.setenv("ALPHA_HUNTER_RISK_POLICY_JSON", json.dumps(_policy()))
    monkeypatch.setenv("ALPHA_HUNTER_PORTFOLIO_JSON", json.dumps({"gross_exposure_pct": 50, "positions": []}))
    plans = build_canonical_plans(board, alignment, {"2317.TW": _history()})
    assert len(plans) == 1
    plan = plans.iloc[0].to_dict()
    assert plan["driver_id"] == ar["driver_id"]
    assert bool(plan["entry_driver_matches_alignment_driver"])
    assert bool(plan["entry_structure_valid"])
    assert plan["trigger_price"] > plan["reference_pivot"]
    assert plan["buy_zone_high"] >= plan["buy_zone_low"]
    assert plan["invalidation_price"] < plan["trigger_price"]
    assert plan["current_action"] != "BUY_NOW"
    assert not bool(plan["entry_executable"])

    entry_packet = {"status": "READY", "all_plans": [plan]}
    positions = {"positions": [{
        "alias": "標的D", "advisory_action": "REVIEW_HOLD", "signal_score": 0.40,
        "confidence": "MEDIUM", "signal_state": "MIXED",
    }]}
    candidates = {"top_advisories": [{
        "ticker": "2317.TW", "name": "SYN-HONHAI", "driver_id": "AI_SERVER_SHIPMENTS",
        "preferred_exposure": "STOCK", "advisory_action": "BUY_BIAS_STOCK",
        "advisory_confidence": "HIGH", "reaction_state": "PRE_CONFIRMATION",
        "provenance_status": "SOURCE_BACKED", "research_priority_score": 0.8,
        "advisory_missing_evidence": "",
    }]}
    regime = {"status": "READY", "regime": "RISK_ON", "risk_score": 10, "target_cash_pct": 0}
    rotation = build_portfolio_allocation_v2(_rotation_policy(), positions, candidates, regime, entry_packet)
    assert rotation["best_entry_plan_destination"]["ticker"] == "2317.TW"
    assert rotation["rotations"][0]["source_alias"] == "標的D"
    assert rotation["rotations"][0]["suggested_source_trim_pct_now"] == 0
    assert rotation["rotations"][0]["trigger_price"] == plan["trigger_price"]

    alignment_packet = {"top_aligned": alignment.to_dict(orient="records")}
    entry_full = {"fresh": [plan], "pullback": [], "continuation": []}
    block = build_block(alignment_packet, entry_full, rotation)
    assert "A. Strongest Global-Aligned Trend" in block
    assert "B. Best Fresh Entry" in block
    assert str(plan["trigger_price"]) in block
    assert "標的D" in block
