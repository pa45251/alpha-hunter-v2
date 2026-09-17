import pandas as pd

from taiwan_sensor import TaiwanScanConfig, select_taiwan_candidates


def test_default_taiwan_liquidity_gate_is_300m_twd():
    cfg = TaiwanScanConfig()
    assert cfg.min_turnover20 == 300_000_000.0
    assert cfg.min_median_turnover20 == 150_000_000.0


def test_candidate_selection_requires_turnover_strictly_above_300m():
    stocks = pd.DataFrame(
        [
            {
                "ticker": "HIGH.TW",
                "price": 50.0,
                "avg_turnover20_twd": 300_000_001.0,
                "acceleration": 0.1,
                "rs_20d_vs_bench": 0.1,
                "keynes_v2": 0.1,
                "reaction_state": "PERSISTENT",
                "taiwan_candidate_score_v1": 0.9,
                "taiwan_early_score_v2": 0.9,
            },
            {
                "ticker": "EDGE.TW",
                "price": 50.0,
                "avg_turnover20_twd": 300_000_000.0,
                "acceleration": 0.1,
                "rs_20d_vs_bench": 0.1,
                "keynes_v2": 0.1,
                "reaction_state": "PERSISTENT",
                "taiwan_candidate_score_v1": 1.0,
                "taiwan_early_score_v2": 1.0,
            },
            {
                "ticker": "LOW.TW",
                "price": 50.0,
                "avg_turnover20_twd": 299_999_999.0,
                "acceleration": 0.1,
                "rs_20d_vs_bench": 0.1,
                "keynes_v2": 0.1,
                "reaction_state": "PERSISTENT",
                "taiwan_candidate_score_v1": 1.0,
                "taiwan_early_score_v2": 1.0,
            },
        ]
    )

    out = select_taiwan_candidates(stocks, TaiwanScanConfig(top_candidates=3))

    assert out["ticker"].tolist() == ["HIGH.TW"]
