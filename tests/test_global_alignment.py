import pandas as pd

import global_alignment as ga


def _breadth():
    return pd.DataFrame([
        {
            "theme": "AI_Server", "above_ma20_pct": 0.8, "above_ma60_pct": 1.0,
            "positive_rs5_pct": 0.8, "positive_rs20_pct": 0.8,
            "near_20d_high_pct": 0.6, "near_52w_high_pct": 0.5,
            "breadth_confidence": "MEDIUM", "median_rs20": 0.12,
        },
        {
            "theme": "Cybersecurity", "above_ma20_pct": 0.2, "above_ma60_pct": 0.5,
            "positive_rs5_pct": 0.1, "positive_rs20_pct": 0.2,
            "near_20d_high_pct": 0.1, "near_52w_high_pct": 0.1,
            "breadth_confidence": "HIGH", "median_rs20": -0.03,
        },
    ])


def _row(ticker, name, driver, reaction, rs20, rs60, accel, keynes, provenance="SOURCE_BACKED"):
    return {
        "run_id": "R1", "ticker": ticker, "name": name, "driver_id": driver,
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": provenance, "polarity": "POSITIVE",
        "reaction_state": reaction, "linkage_confidence": 0.95,
        "rs_20d_vs_bench": rs20, "rs_60d_vs_bench": rs60,
        "acceleration": accel, "keynes_v2": keynes,
    }


def test_aligned_confirming_stock_ranks_above_weak_international_theme():
    board = pd.DataFrame([
        _row("2317.TW", "鴻海", "AI_SERVER_SHIPMENTS", "CONFIRMING", 0.08, 0.12, 0.04, 0.5),
        _row("9999.TW", "弱資安", "ENTERPRISE_CYBER_SPEND", "CONFIRMING", 0.10, 0.11, 0.05, 0.6),
    ])
    out = ga.build_global_alignment(board, _breadth())
    honhai = out[out["ticker"] == "2317.TW"].iloc[0]
    cyber = out[out["ticker"] == "9999.TW"].iloc[0]
    assert bool(honhai["alignment_eligible"])
    assert not bool(cyber["alignment_eligible"])
    assert honhai["alignment_score"] > cyber["alignment_score"]


def test_preconfirmation_preserves_early_discovery_when_accel_and_keynes_positive():
    board = pd.DataFrame([
        _row("2317.TW", "鴻海", "AI_SERVER_SHIPMENTS", "PRE_CONFIRMATION", -0.01, 0.02, 0.04, 0.4),
        _row("2222.TW", "早期雜訊", "AI_SERVER_SHIPMENTS", "PRE_CONFIRMATION", -0.01, 0.02, -0.01, -0.1),
    ])
    out = ga.build_global_alignment(board, _breadth())
    good = out[out["ticker"] == "2317.TW"].iloc[0]
    bad = out[out["ticker"] == "2222.TW"].iloc[0]
    assert bool(good["alignment_eligible"])
    assert good["alignment_action"] == "PREPARE"
    assert not bool(bad["alignment_eligible"])
    assert "EARLY_TAIWAN_TREND_NOT_CLEAN" in bad["blockers"]


def test_extended_and_broken_are_never_fresh_entry_eligible():
    board = pd.DataFrame([
        _row("A.TW", "A", "AI_SERVER_SHIPMENTS", "EXTENDED", 0.2, 0.2, 0.1, 0.8),
        _row("B.TW", "B", "AI_SERVER_SHIPMENTS", "BROKEN", 0.2, 0.2, 0.1, 0.8),
    ])
    out = ga.build_global_alignment(board, _breadth())
    assert not out["alignment_eligible"].any()


def test_score_is_relative_not_probability_flag():
    board = pd.DataFrame([
        _row("2317.TW", "鴻海", "AI_SERVER_SHIPMENTS", "CONFIRMING", 0.08, 0.12, 0.04, 0.5),
    ])
    out = ga.build_global_alignment(board, _breadth())
    assert bool(out.iloc[0]["score_is_probability"]) is False
