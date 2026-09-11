from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

OUT = Path("output")
BOARD_PATH = OUT / "decision_board.csv"
BREADTH_PATH = OUT / "theme_breadth.csv"
CSV_OUT = OUT / "global_alignment_v2.csv"
JSON_OUT = OUT / "global_alignment_v2.json"

DRIVER_THEME_MAP = {
    "AI_SERVER_SHIPMENTS": "AI_Server",
    "AI_SERVER_RACK_BUILD": "AI_Server",
    "AI_SERVER_THERMAL_DENSITY": "AI_Server",
    "DATACENTER_POWER_INFRA": "AI_Infrastructure",
    "DATACENTER_COOLING_INFRA": "AI_Infrastructure",
    "AI_NETWORKING_UPGRADE": "AI_Networking",
    "DRAM_PRICING": "Memory",
    "SPECIALTY_MEMORY_PRICING": "Memory",
    "MEMORY_IC_CYCLE": "Memory",
    "NAND_STORAGE_CYCLE": "Memory",
    "LEADING_EDGE_FOUNDRY_AI_DEMAND": "AI_Semiconductor",
    "MATURE_NODE_FOUNDRY_UTILIZATION": "Semiconductor",
    "WAFER_FAB_EQUIPMENT_CAPEX": "Semiconductor_Equipment",
    "ADVANCED_PACKAGING_TEST_CAPEX": "AI_Semiconductor",
    "GRID_CAPEX": "Power_Grid",
    "POWER_ELECTRONICS_CAPEX": "Power",
    "NUCLEAR_GRID_SECOND_ORDER": "Nuclear_Power",
    "CONTAINER_FREIGHT": "Shipping",
    "DRY_BULK_FREIGHT": "Shipping",
    "COPPER_COMMODITY_TRADE_INVENTORY": "Copper",
    "ENTERPRISE_CYBER_SPEND": "Cybersecurity",
    "BIOPHARMA_RISK_APPETITE": "Biotech",
    "GENOMICS_RISK_APPETITE": "Genomics",
    "FINANCIALS_RATE_CREDIT_CYCLE": "Financials",
    "CONSUMER_ELECTRONICS_CYCLE": "Consumer_Tech",
}

REACTION_ACTION = {
    "PRE_CONFIRMATION": "PREPARE",
    "EARLY_CONFIRMATION": "ENTRY_READY",
    "CONFIRMING": "ENTRY_READY",
    "PULLBACK": "ENTRY_READY_PULLBACK",
    "PERSISTENT": "HOLD_DONT_CHASE",
    "EXTENDED": "DO_NOT_CHASE",
    "BROKEN": "BLOCKED",
    "UNKNOWN": "WAIT",
}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _rank01(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    if x.notna().sum() <= 1:
        return pd.Series(0.5, index=s.index, dtype=float)
    return x.rank(pct=True, method="average").fillna(0.0)


def _breadth_score(row: pd.Series) -> tuple[float, float]:
    trend = (
        0.35 * _f(row.get("above_ma20_pct"))
        + 0.35 * _f(row.get("above_ma60_pct"))
        + 0.30 * max(0.0, min(1.0, 0.5 + 3.0 * _f(row.get("median_rs20"))))
    )
    breadth = (
        0.40 * _f(row.get("positive_rs20_pct"))
        + 0.25 * _f(row.get("positive_rs5_pct"))
        + 0.20 * _f(row.get("near_20d_high_pct"))
        + 0.15 * _f(row.get("near_52w_high_pct"))
    )
    return float(np.clip(trend, 0, 1)), float(np.clip(breadth, 0, 1))


def _ticker_price_ranks(board: pd.DataFrame) -> pd.DataFrame:
    """Compute price-quality ranks once per ticker, independent of driver-row count."""
    cols = ["ticker", "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration", "keynes_v2"]
    x = board[[c for c in cols if c in board.columns]].copy()
    if "ticker" not in x.columns:
        return pd.DataFrame()
    # Keep ticker as a normal column. Pandas 3 rejects a merge key that is both index and column.
    x = x.drop_duplicates("ticker", keep="first").reset_index(drop=True)
    x["r_rs20_v2"] = _rank01(x.get("rs_20d_vs_bench", pd.Series(index=x.index, dtype=float)))
    x["r_rs60_v2"] = _rank01(x.get("rs_60d_vs_bench", pd.Series(index=x.index, dtype=float)))
    x["r_accel_v2"] = _rank01(x.get("acceleration", pd.Series(index=x.index, dtype=float)))
    x["r_keynes_v2"] = _rank01(x.get("keynes_v2", pd.Series(index=x.index, dtype=float)))
    x["taiwan_trend_score_v2"] = 0.40 * x["r_rs20_v2"] + 0.30 * x["r_rs60_v2"] + 0.30 * x["r_accel_v2"]
    return x[["ticker", "r_rs20_v2", "r_rs60_v2", "r_accel_v2", "r_keynes_v2", "taiwan_trend_score_v2"]]


def build_global_alignment_v2(board: pd.DataFrame, breadth: pd.DataFrame) -> pd.DataFrame:
    if board is None or board.empty or breadth is None or breadth.empty:
        return pd.DataFrame()

    x = board.copy()
    for c in ["dynamic_driver_state", "provenance_status", "polarity", "reaction_state", "driver_id", "ticker", "name"]:
        if c not in x:
            x[c] = ""
        x[c] = x[c].fillna("").astype(str)

    ranks = _ticker_price_ranks(x)
    x = x.merge(ranks, on="ticker", how="left", validate="many_to_one")

    b = breadth.copy()
    if "theme" not in b.columns:
        return pd.DataFrame()
    b["theme"] = b["theme"].astype(str)
    bidx = b.set_index("theme", drop=False)
    rows: list[dict[str, Any]] = []

    for _, r in x.iterrows():
        driver = str(r.get("driver_id", "")).upper()
        theme = DRIVER_THEME_MAP.get(driver, "")
        reaction = str(r.get("reaction_state", "UNKNOWN")).upper()
        blockers: list[str] = []

        active = str(r.get("dynamic_driver_state", "")).upper() == "ACTIVE_RESEARCH_VALIDATED"
        source_backed = str(r.get("provenance_status", "")).upper() == "SOURCE_BACKED"
        positive = str(r.get("polarity", "")).upper() == "POSITIVE"
        if not active:
            blockers.append("GLOBAL_DRIVER_NOT_ACTIVE")
        if not source_backed:
            blockers.append("COMPANY_EDGE_NOT_SOURCE_BACKED")
        if not positive:
            blockers.append("NON_POSITIVE_LONG_EDGE")
        if reaction == "BROKEN":
            blockers.append("TAIWAN_TRANSMISSION_BROKEN")
        if reaction == "EXTENDED":
            blockers.append("TAIWAN_PRICE_EXTENDED")

        global_trend = 0.0
        international_breadth = 0.0
        breadth_conf = "MISSING"
        breadth_n = 0
        breadth_eligible = False
        if theme and theme in bidx.index:
            br = bidx.loc[theme]
            if isinstance(br, pd.DataFrame):
                br = br.iloc[0]
            global_trend, international_breadth = _breadth_score(br)
            breadth_conf = str(br.get("breadth_confidence", "LOW")).upper()
            breadth_n = int(_f(br.get("n"), 0))
            raw_eligible = br.get("breadth_eligible", breadth_n >= 3)
            breadth_eligible = bool(raw_eligible) and breadth_n >= 3
            if not breadth_eligible:
                blockers.append("INTERNATIONAL_BREADTH_COVERAGE_INSUFFICIENT")
        else:
            blockers.append("INTERNATIONAL_THEME_MAPPING_MISSING")

        if theme and theme in bidx.index and global_trend < 0.45:
            blockers.append("GLOBAL_THEME_TREND_NOT_SUPPORTIVE")
        if theme and theme in bidx.index and international_breadth < 0.40:
            blockers.append("INTERNATIONAL_BREADTH_NOT_SUPPORTIVE")

        rs20 = _f(r.get("rs_20d_vs_bench"), np.nan)
        accel = _f(r.get("acceleration"), np.nan)
        keynes = _f(r.get("keynes_v2"), np.nan)
        if reaction == "PRE_CONFIRMATION":
            if not (np.isfinite(accel) and np.isfinite(keynes) and accel > 0 and keynes > 0):
                blockers.append("EARLY_TAIWAN_TREND_NOT_CLEAN")
        elif reaction in {"CONFIRMING", "EARLY_CONFIRMATION", "PULLBACK", "PERSISTENT"}:
            if not (np.isfinite(rs20) and np.isfinite(keynes) and rs20 > 0 and keynes > 0):
                blockers.append("TAIWAN_TREND_NOT_SUPPORTIVE")
        elif reaction not in {"BROKEN", "EXTENDED"}:
            blockers.append("TAIWAN_ENTRY_STATE_NOT_READY")

        causal = (
            0.45 * (1.0 if active else 0.0)
            + 0.30 * (1.0 if source_backed else 0.0)
            + 0.25 * max(0.0, min(1.0, _f(r.get("linkage_confidence"))))
        )
        score = (
            0.30 * global_trend
            + 0.25 * _f(r.get("taiwan_trend_score_v2"))
            + 0.20 * international_breadth
            + 0.15 * _f(r.get("r_keynes_v2"))
            + 0.10 * causal
        )
        eligible = len(blockers) == 0
        confidence = "HIGH"
        if breadth_conf == "LOW" or breadth_n < 6:
            confidence = "MEDIUM"
        if breadth_conf == "MISSING" or not source_backed or not breadth_eligible:
            confidence = "LOW"

        rows.append({
            "run_id": r.get("run_id"),
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "driver_id": driver,
            "international_theme": theme,
            "reaction_state": reaction,
            "alignment_action": REACTION_ACTION.get(reaction, "WAIT"),
            "alignment_eligible": eligible,
            "alignment_score": round(float(np.clip(score, 0, 1)), 4),
            "alignment_confidence": confidence,
            "global_trend_score": round(global_trend, 4),
            "taiwan_trend_score": round(_f(r.get("taiwan_trend_score_v2")), 4),
            "international_breadth_score": round(international_breadth, 4),
            "keynes_quality_rank": round(_f(r.get("r_keynes_v2")), 4),
            "causal_confidence_score": round(causal, 4),
            "breadth_n": breadth_n,
            "breadth_eligible": breadth_eligible,
            "rs20_vs_tw": _f(r.get("rs_20d_vs_bench"), np.nan),
            "rs60_vs_tw": _f(r.get("rs_60d_vs_bench"), np.nan),
            "acceleration": _f(r.get("acceleration"), np.nan),
            "keynes_v2": _f(r.get("keynes_v2"), np.nan),
            "blockers": ";".join(dict.fromkeys(blockers)),
            "score_is_probability": False,
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["alignment_eligible", "alignment_score"], ascending=[False, False])
    out = out.drop_duplicates("ticker", keep="first").reset_index(drop=True)
    out["alignment_rank"] = np.arange(1, len(out) + 1)
    return out[["alignment_rank"] + [c for c in out.columns if c != "alignment_rank"]]


def write_outputs() -> tuple[pd.DataFrame, dict[str, Any]]:
    from canonical_evidence import assert_output_lineage
    run_id = assert_output_lineage(["decision_packet.json"])
    if not BOARD_PATH.exists() or not BREADTH_PATH.exists():
        raise RuntimeError("GLOBAL_ALIGNMENT_V2_INPUT_MISSING")
    board = pd.read_csv(BOARD_PATH, dtype={"taiwan_code": str})
    breadth = pd.read_csv(BREADTH_PATH)
    leaderboard = build_global_alignment_v2(board, breadth)
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(CSV_OUT, index=False)
    top = leaderboard[leaderboard["alignment_eligible"]].head(20) if not leaderboard.empty else leaderboard
    payload = {
        "source_run_id": run_id,
        "public_lineage_id": json.loads((OUT / "decision_packet.json").read_text())["decision_bridge"]["public_lineage_id"],
        "contract": "ALPHA_HUNTER_GLOBAL_ALIGNMENT_V2",
        "schema_version": "2.0",
        "generated_at": datetime.now().astimezone().isoformat(),
        "score_is_probability": False,
        "score_interpretation": "Relative alignment/evidence strength only; not a calibrated win probability.",
        "hard_rules": [
            "PRICE_CANNOT_CREATE_CAUSALITY",
            "ACTIVE_DRIVER_REQUIRED",
            "SOURCE_BACKED_COMPANY_EDGE_REQUIRED",
            "VALID_INTERNATIONAL_BREADTH_COVERAGE_REQUIRED",
            "DUPLICATE_DRIVER_ROWS_CANNOT_CHANGE_PRICE_RANKS",
            "BROKEN_AND_EXTENDED_BLOCK_FRESH_ENTRY",
        ],
        "top_aligned": top.to_dict(orient="records") if not top.empty else [],
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return leaderboard, payload


def main() -> None:
    board, packet = write_outputs()
    top = packet.get("top_aligned") or []
    best = top[0] if top else {}
    print(f"Global alignment V2 rows={len(board)} eligible={int(board['alignment_eligible'].sum()) if not board.empty else 0} best={best.get('ticker')} {best.get('name')}")


if __name__ == "__main__":
    main()
