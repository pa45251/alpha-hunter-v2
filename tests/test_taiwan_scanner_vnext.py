import numpy as np
import pandas as pd

from taiwan_sensor import (
    TaiwanScanConfig,
    _add_turnover_feature,
    add_taiwan_candidate_score,
    select_taiwan_candidates,
)


def _feature_row(ticker="A.TW", **overrides):
    row = dict(
        ticker=ticker,
        price=100.0,
        avg_turnover20_twd=200_000_000.0,
        median_turnover20_twd=150_000_000.0,
        ret_5d=0.05,
        ret_20d=0.10,
        ret_60d=0.10,
        ma20_slope=0.01,
        volume_ratio20=1.2,
        dist_52w_high=-0.05,
        keynes_v2=0.5,
        rs_5d_vs_bench=0.03,
        rs_20d_vs_bench=0.08,
        rs_60d_vs_bench=0.04,
        acceleration=0.04,
        trend="REBOUND",
        bias20=0.05,
    )
    row.update(overrides)
    return row


def _selection_row(ticker, stage, score=0.5, early=0.5, turnover=400_000_000.0, median=None, **overrides):
    reaction = {
        "EARLY": "PRE_CONFIRMATION",
        "CONFIRMED": "CONFIRMING",
        "PERSISTENT": "PERSISTENT",
        "PULLBACK": "PULLBACK",
        "WATCH": "UNKNOWN",
        "BROKEN": "BROKEN",
    }[stage]
    row = dict(
        ticker=ticker,
        price=50.0,
        avg_turnover20_twd=turnover,
        median_turnover20_twd=turnover if median is None else median,
        acceleration=0.1,
        rs_5d_vs_bench=0.1,
        rs_20d_vs_bench=0.1,
        rs_acceleration=0.075,
        keynes_v2=0.5,
        trend_stage=stage,
        reaction_state=reaction,
        extension_risk="NORMAL",
        taiwan_candidate_score_v1=score,
        taiwan_early_score_v2=early,
        taiwan_early_score_v3=early,
    )
    row.update(overrides)
    return row


def test_primary_research_cap_clamps_legacy_150_request_to_100():
    assert TaiwanScanConfig().top_candidates == 100
    assert TaiwanScanConfig(top_candidates=150).top_candidates == 100


def test_rebound_needs_strict_early_confirmation():
    out = add_taiwan_candidate_score(pd.DataFrame([_feature_row()]))
    row = out.iloc[0]
    assert row["trend_stage"] == "EARLY"
    assert row["reaction_state"] == "PRE_CONFIRMATION"


def test_bear_cannot_become_early_from_short_term_improvement_alone():
    out = add_taiwan_candidate_score(pd.DataFrame([
        _feature_row(
            trend="BEAR",
            ma20_slope=0.02,
            rs_5d_vs_bench=0.04,
            rs_20d_vs_bench=-0.02,
            acceleration=0.08,
            keynes_v2=0.8,
        )
    ]))
    assert out.iloc[0]["trend_stage"] == "WATCH"


def test_rebound_fails_early_if_relative_strength_is_not_accelerating():
    out = add_taiwan_candidate_score(pd.DataFrame([
        _feature_row(rs_5d_vs_bench=0.01, rs_20d_vs_bench=0.08)
    ]))
    assert out.iloc[0]["rs_acceleration"] < 0
    assert out.iloc[0]["trend_stage"] == "WATCH"


def test_rebound_requires_two_of_three_supporting_votes():
    out = add_taiwan_candidate_score(pd.DataFrame([
        _feature_row(
            ret_5d=-0.05,
            ret_20d=0.10,
            rs_20d_vs_bench=-0.01,
            rs_5d_vs_bench=0.02,
            keynes_v2=0.5,
        )
    ]))
    assert out.iloc[0]["acceleration"] < 0
    assert out.iloc[0]["rs_acceleration"] > 0
    assert out.iloc[0]["trend_stage"] == "WATCH"


def test_strong_up_structure_can_be_persistent_and_extension_is_separate():
    out = add_taiwan_candidate_score(pd.DataFrame([
        _feature_row(trend="STRONG_UP", bias20=0.25, ret_5d=0.10, rs_60d_vs_bench=0.05)
    ]))
    row = out.iloc[0]
    assert row["trend_stage"] == "PERSISTENT"
    assert row["extension_risk"] == "EXTENDED"
    assert row["reaction_state"] == "EXTENDED"


def test_relative_strength_acceleration_is_5d_equivalent_change():
    out = add_taiwan_candidate_score(pd.DataFrame([
        _feature_row(rs_5d_vs_bench=0.03, rs_20d_vs_bench=0.08)
    ]))
    assert np.isclose(out.iloc[0]["rs_acceleration"], 0.01)


def test_median_turnover_and_capacity_are_diagnostics():
    idx = pd.bdate_range("2026-08-20", periods=20)
    hist = pd.DataFrame({
        "Close": np.repeat(10.0, 20),
        "Volume": np.r_[np.repeat(1_000_000.0, 19), 100_000_000.0],
    }, index=idx)
    features = {}
    _add_turnover_feature(hist, features)
    assert features["avg_turnover20_twd"] > features["median_turnover20_twd"]
    assert features["median_turnover20_twd"] == 10_000_000.0
    assert features["liquidity_capacity_2pct_2d_twd"] == 400_000.0


def test_median_turnover_is_now_a_hard_liquidity_gate():
    stocks = pd.DataFrame([
        _selection_row("GOOD.TW", "CONFIRMED", score=0.9, turnover=400_000_000.0, median=200_000_000.0),
        _selection_row("SPIKE.TW", "CONFIRMED", score=1.0, turnover=500_000_000.0, median=100_000_000.0),
    ])
    out = select_taiwan_candidates(stocks, TaiwanScanConfig(top_candidates=10))
    assert out["ticker"].tolist() == ["GOOD.TW"]


def test_mature_stage_does_not_need_positive_acceleration_to_remain_qualified():
    stocks = pd.DataFrame([
        _selection_row("PULLBACK.TW", "PULLBACK", score=0.8, acceleration=-0.2, rs_acceleration=-0.1),
    ])
    out = select_taiwan_candidates(stocks, TaiwanScanConfig(top_candidates=10))
    assert out["ticker"].tolist() == ["PULLBACK.TW"]


def test_primary_does_not_fill_with_watch_stage_just_to_hit_quota():
    stocks = pd.DataFrame([
        _selection_row("C.TW", "CONFIRMED", score=0.9),
        _selection_row("E.TW", "EARLY", early=0.8),
        _selection_row("W.TW", "WATCH", score=1.0, early=1.0),
    ])
    out = select_taiwan_candidates(stocks, TaiwanScanConfig(top_candidates=10))
    assert set(out["ticker"]) == {"C.TW", "E.TW"}
    assert len(out) == 2


def test_early_has_ceiling_but_no_reserved_quota_when_over_capacity():
    rows = [_selection_row(f"C{i}.TW", "CONFIRMED", score=1.0 - i * 0.01) for i in range(12)]
    rows += [_selection_row(f"E{i}.TW", "EARLY", score=0.99 - i * 0.01, early=0.99 - i * 0.01) for i in range(4)]
    out = select_taiwan_candidates(pd.DataFrame(rows), TaiwanScanConfig(top_candidates=10))
    assert (out["candidate_bucket"] == "EARLY").sum() <= 3
    assert len(out) == 10


def test_low_priority_early_is_not_reserved_a_seat():
    rows = [_selection_row(f"C{i}.TW", "CONFIRMED", score=1.0 - i * 0.01) for i in range(10)]
    rows += [_selection_row("E.TW", "EARLY", early=0.10)]
    out = select_taiwan_candidates(pd.DataFrame(rows), TaiwanScanConfig(top_candidates=10))
    assert "E.TW" not in set(out["ticker"])
    assert len(out) == 10


def test_under_capacity_keeps_all_qualified_names_without_manufacturing_quota():
    rows = [_selection_row(f"C{i}.TW", "CONFIRMED", score=0.8 - i * 0.01) for i in range(2)]
    rows += [_selection_row(f"E{i}.TW", "EARLY", early=0.7 - i * 0.01) for i in range(4)]
    out = select_taiwan_candidates(pd.DataFrame(rows), TaiwanScanConfig(top_candidates=10))
    assert len(out) == 6
    assert (out["candidate_bucket"] == "EARLY").sum() == 4


def test_rejected_names_are_not_returned_by_candidate_selection():
    stocks = pd.DataFrame([
        _selection_row("PRIMARY.TW", "CONFIRMED", score=0.9),
        _selection_row("WATCH.TW", "WATCH", score=1.0, early=1.0),
        _selection_row("ILLIQ.TW", "EARLY", early=1.0, turnover=50_000_000.0),
    ])
    out = select_taiwan_candidates(stocks, TaiwanScanConfig(top_candidates=10))
    assert out["ticker"].tolist() == ["PRIMARY.TW"]
