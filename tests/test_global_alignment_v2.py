import pandas as pd

import global_alignment_v2 as ga


def _breadth():
    return pd.DataFrame([
        {
            "theme": "AI_Server", "n": 5, "breadth_eligible": True,
            "above_ma20_pct": 0.8, "above_ma60_pct": 0.8,
            "positive_rs5_pct": 0.8, "positive_rs20_pct": 0.8,
            "near_20d_high_pct": 0.6, "near_52w_high_pct": 0.5,
            "breadth_confidence": "MEDIUM", "median_rs20": 0.10,
        },
        {
            "theme": "Power_Grid", "n": 4, "breadth_eligible": True,
            "above_ma20_pct": 0.75, "above_ma60_pct": 0.75,
            "positive_rs5_pct": 0.75, "positive_rs20_pct": 0.75,
            "near_20d_high_pct": 0.5, "near_52w_high_pct": 0.5,
            "breadth_confidence": "MEDIUM", "median_rs20": 0.08,
        },
        {
            "theme": "Shipping", "n": 1, "breadth_eligible": False,
            "above_ma20_pct": 1.0, "above_ma60_pct": 1.0,
            "positive_rs5_pct": 1.0, "positive_rs20_pct": 1.0,
            "near_20d_high_pct": 1.0, "near_52w_high_pct": 1.0,
            "breadth_confidence": "LOW", "median_rs20": 0.20,
        },
    ])


def _row(ticker, driver="AI_SERVER_SHIPMENTS", rs20=0.08, rs60=0.12, accel=0.04, keynes=0.5):
    return {
        "run_id": "R1", "ticker": ticker, "name": ticker, "driver_id": driver,
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED", "polarity": "POSITIVE",
        "reaction_state": "CONFIRMING", "linkage_confidence": 0.95,
        "rs_20d_vs_bench": rs20, "rs_60d_vs_bench": rs60,
        "acceleration": accel, "keynes_v2": keynes,
    }


def test_duplicate_driver_row_cannot_change_other_ticker_price_rank():
    base = pd.DataFrame([
        _row("A.TW", rs20=0.10, rs60=0.10, accel=0.03, keynes=0.4),
        _row("B.TW", rs20=0.05, rs60=0.06, accel=0.02, keynes=0.2),
        _row("C.TW", rs20=0.02, rs60=0.03, accel=0.01, keynes=0.1),
    ])
    first = ga.build_global_alignment_v2(base, _breadth()).set_index("ticker")
    duplicated = pd.concat([base, pd.DataFrame([_row("A.TW", rs20=0.10, rs60=0.10, accel=0.03, keynes=0.4)])], ignore_index=True)
    second = ga.build_global_alignment_v2(duplicated, _breadth()).set_index("ticker")
    assert first.loc["B.TW", "taiwan_trend_score"] == second.loc["B.TW", "taiwan_trend_score"]
    assert first.loc["C.TW", "keynes_quality_rank"] == second.loc["C.TW", "keynes_quality_rank"]


def test_breadth_ineligible_theme_cannot_pass_even_if_percentages_are_perfect():
    board = pd.DataFrame([_row("2606.TW", driver="DRY_BULK_FREIGHT")])
    out = ga.build_global_alignment_v2(board, _breadth())
    r = out.iloc[0]
    assert not bool(r["alignment_eligible"])
    assert "INTERNATIONAL_BREADTH_COVERAGE_INSUFFICIENT" in r["blockers"]


def test_grid_capex_uses_power_grid_basket():
    board = pd.DataFrame([_row("1519.TW", driver="GRID_CAPEX")])
    out = ga.build_global_alignment_v2(board, _breadth())
    r = out.iloc[0]
    assert r["international_theme"] == "Power_Grid"
    assert bool(r["breadth_eligible"])


def test_v2_score_is_never_probability():
    board = pd.DataFrame([_row("2317.TW")])
    out = ga.build_global_alignment_v2(board, _breadth())
    assert bool(out.iloc[0]["score_is_probability"]) is False
