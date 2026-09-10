import pandas as pd

from semantic_theme_breadth import build_taiwan_semantic_breadth, attach_semantic_breadth


def _stocks():
    return pd.DataFrame([
        {"code": "1001", "price": 110, "ma20": 100, "ma60": 90, "rs_20d_vs_bench": 0.10, "dist_20d_high": -0.01, "dist_52w_high": -0.02, "keynes_v2": 0.5},
        {"code": "1002", "price": 108, "ma20": 100, "ma60": 95, "rs_20d_vs_bench": 0.05, "dist_20d_high": -0.02, "dist_52w_high": -0.03, "keynes_v2": 0.4},
        {"code": "1003", "price": 105, "ma20": 100, "ma60": 98, "rs_20d_vs_bench": 0.02, "dist_20d_high": -0.03, "dist_52w_high": -0.04, "keynes_v2": 0.3},
        {"code": "2001", "price": 80, "ma20": 90, "ma60": 100, "rs_20d_vs_bench": -0.10, "dist_20d_high": -0.10, "dist_52w_high": -0.20, "keynes_v2": -0.5},
        {"code": "2002", "price": 82, "ma20": 90, "ma60": 100, "rs_20d_vs_bench": -0.08, "dist_20d_high": -0.12, "dist_52w_high": -0.18, "keynes_v2": -0.4},
        {"code": "2003", "price": 85, "ma20": 90, "ma60": 100, "rs_20d_vs_bench": -0.05, "dist_20d_high": -0.08, "dist_52w_high": -0.15, "keynes_v2": -0.3},
    ])


def _edges():
    rows = []
    for code in ["1001", "1002", "1003"]:
        rows.append({"global_theme": "GOOD", "taiwan_code": code, "enabled": 1, "polarity": "POSITIVE"})
    for code in ["2001", "2002", "2003"]:
        rows.append({"global_theme": "BAD", "taiwan_code": code, "enabled": 1, "polarity": "POSITIVE"})
    return pd.DataFrame(rows)


def test_semantic_breadth_separates_healthy_and_broken_groups():
    b = build_taiwan_semantic_breadth(_stocks(), _edges()).set_index("semantic_theme")
    assert b.loc["GOOD", "semantic_breadth_state"] == "HEALTHY"
    assert b.loc["BAD", "semantic_breadth_state"] == "BROKEN"


def test_duplicate_driver_edges_do_not_double_count_theme_members():
    edges = pd.concat([_edges(), pd.DataFrame([{"global_theme": "GOOD", "taiwan_code": "1001", "enabled": 1, "polarity": "POSITIVE"}])])
    b = build_taiwan_semantic_breadth(_stocks(), edges).set_index("semantic_theme")
    assert int(b.loc["GOOD", "n"]) == 3


def test_attach_semantic_breadth_to_structural_rows():
    b = build_taiwan_semantic_breadth(_stocks(), _edges())
    structural = pd.DataFrame([{"global_theme": "GOOD", "ticker": "1001.TW"}, {"global_theme": "UNKNOWN_THEME", "ticker": "9999.TW"}])
    out = attach_semantic_breadth(structural, b)
    assert out.iloc[0]["semantic_breadth_state"] == "HEALTHY"
    assert out.iloc[1]["semantic_breadth_state"] == "UNKNOWN"
