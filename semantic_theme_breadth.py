from __future__ import annotations

import pandas as pd

BREADTH_CONTRACT = "ALPHA_HUNTER_TAIWAN_SEMANTIC_BREADTH_V1"


def _code(v) -> str:
    return str(v or "").strip().split(".")[0].zfill(4)


def classify_semantic_breadth(row: pd.Series) -> str:
    """Classify breadth with transparent, deliberately unfitted thresholds.

    Price breadth can validate participation or block a stock-alpha entry, but it can
    never activate a causal driver. Themes with fewer than three mapped live stocks
    are explicitly low-confidence rather than treated as healthy.
    """
    n = int(row.get("n", 0) or 0)
    if n < 3:
        return "LOW_CONFIDENCE"
    above20 = float(row.get("above_ma20_pct", 0) or 0)
    above60 = float(row.get("above_ma60_pct", 0) or 0)
    rs20 = float(row.get("positive_rs20_pct", 0) or 0)
    median_rs20 = float(row.get("median_rs20", 0) or 0)
    if above20 >= 0.50 and above60 >= 0.50 and rs20 >= 0.50 and median_rs20 >= 0:
        return "HEALTHY"
    if above20 <= 0.35 and rs20 <= 0.35 and median_rs20 < 0:
        return "BROKEN"
    return "MIXED"


def build_taiwan_semantic_breadth(stocks: pd.DataFrame, exposures: pd.DataFrame) -> pd.DataFrame:
    if stocks is None or stocks.empty or exposures is None or exposures.empty:
        return pd.DataFrame()
    required_stock = {"code", "price", "ma20", "ma60", "rs_20d_vs_bench", "dist_20d_high", "dist_52w_high", "keynes_v2"}
    required_edge = {"global_theme", "taiwan_code"}
    if not required_stock.issubset(stocks.columns) or not required_edge.issubset(exposures.columns):
        return pd.DataFrame()

    s = stocks.copy()
    s["taiwan_code"] = s["code"].map(_code)
    e = exposures.copy()
    e["taiwan_code"] = e["taiwan_code"].map(_code)
    if "enabled" in e.columns:
        e = e[pd.to_numeric(e["enabled"], errors="coerce").fillna(0).astype(int).eq(1)]
    if "polarity" in e.columns:
        e = e[e["polarity"].fillna("").astype(str).str.upper().eq("POSITIVE")]
    e = e[["global_theme", "taiwan_code"]].dropna().drop_duplicates()
    x = e.merge(s, on="taiwan_code", how="inner")
    if x.empty:
        return pd.DataFrame()

    rows = []
    for theme, g in x.groupby("global_theme", dropna=False):
        n = len(g)
        row = {
            "semantic_theme": str(theme),
            "n": int(n),
            "above_ma20_pct": float((g["price"] > g["ma20"]).mean()),
            "above_ma60_pct": float((g["price"] > g["ma60"]).mean()),
            "positive_rs20_pct": float((g["rs_20d_vs_bench"] > 0).mean()),
            "near_20d_high_pct": float((g["dist_20d_high"] > -0.05).mean()),
            "near_52w_high_pct": float((g["dist_52w_high"] > -0.05).mean()),
            "median_rs20": float(g["rs_20d_vs_bench"].median()),
            "median_keynes_v2": float(g["keynes_v2"].median()),
        }
        row["semantic_breadth_state"] = classify_semantic_breadth(pd.Series(row))
        row["breadth_contract"] = BREADTH_CONTRACT
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["semantic_breadth_state", "positive_rs20_pct", "median_rs20"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def attach_semantic_breadth(structural: pd.DataFrame, breadth: pd.DataFrame) -> pd.DataFrame:
    x = structural.copy()
    if x.empty:
        return x
    if breadth is None or breadth.empty:
        x["semantic_breadth_state"] = "UNKNOWN"
        return x
    keep = [
        "semantic_theme", "n", "above_ma20_pct", "above_ma60_pct", "positive_rs20_pct",
        "near_20d_high_pct", "near_52w_high_pct", "median_rs20", "median_keynes_v2",
        "semantic_breadth_state", "breadth_contract",
    ]
    b = breadth[[c for c in keep if c in breadth.columns]].copy()
    b = b.rename(columns={
        "semantic_theme": "global_theme",
        "n": "semantic_breadth_n",
        "above_ma20_pct": "semantic_above_ma20_pct",
        "above_ma60_pct": "semantic_above_ma60_pct",
        "positive_rs20_pct": "semantic_positive_rs20_pct",
        "near_20d_high_pct": "semantic_near_20d_high_pct",
        "near_52w_high_pct": "semantic_near_52w_high_pct",
        "median_rs20": "semantic_median_rs20",
        "median_keynes_v2": "semantic_median_keynes_v2",
    })
    x = x.merge(b, on="global_theme", how="left", validate="many_to_one")
    x["semantic_breadth_state"] = x["semantic_breadth_state"].fillna("UNKNOWN")
    return x
