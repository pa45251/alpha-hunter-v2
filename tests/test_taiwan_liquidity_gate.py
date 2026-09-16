import pandas as pd

from taiwan_sensor import TaiwanScanConfig, select_taiwan_candidates


def test_default_taiwan_liquidity_gate_is_100m_twd():
    assert TaiwanScanConfig().min_turnover20 == 100_000_000.0


def test_candidate_selection_excludes_names_below_100m_turnover():
    stocks = pd.DataFrame(
        [
            {
                "ticker": "HIGH.TW",
                "price": 50.0,
                "avg_turnover20_twd": 100_000_000.0,
                "acceleration": 0.1,
                "rs_20d_vs_bench": 0.1,
                "keynes_v2": 0.1,
                "reaction_state": "PERSISTENT",
                "taiwan_candidate_score_v1": 0.9,
                "taiwan_early_score_v2": 0.9,
            },
            {
                "ticker": "LOW.TW",
                "price": 50.0,
                "avg_turnover20_twd": 99_999_999.0,
                "acceleration": 0.1,
                "rs_20d_vs_bench": 0.1,
                "keynes_v2": 0.1,
                "reaction_state": "PERSISTENT",
                "taiwan_candidate_score_v1": 1.0,
                "taiwan_early_score_v2": 1.0,
            },
        ]
    )

    out = select_taiwan_candidates(stocks, TaiwanScanConfig(top_candidates=2))

    assert out["ticker"].tolist() == ["HIGH.TW"]
