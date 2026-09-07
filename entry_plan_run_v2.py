from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from entry_structure_v2 import (
    CONTRACT,
    STRATEGY_VERSION,
    EntryPolicyV2,
    _download_histories,
    choose_plan,
)
from portfolio_risk_v2 import apply_entry_risk_gate_v2

OUT = Path("output")
BOARD_PATH = OUT / "decision_board.csv"
ALIGN_CSV_PATH = OUT / "global_alignment_v2.csv"
MANIFEST_PATH = OUT / "manifest.json"
CSV_OUT = OUT / "entry_plans_v2.csv"
JSON_OUT = OUT / "entry_plans_v2.json"


def build_canonical_plans(
    board: pd.DataFrame,
    alignment: pd.DataFrame,
    histories: dict[str, pd.DataFrame],
    policy: EntryPolicyV2 = EntryPolicyV2(),
) -> pd.DataFrame:
    if board is None or board.empty or alignment is None or alignment.empty:
        return pd.DataFrame()

    # One canonical alignment row per ticker. Entry structure MUST use that exact driver.
    a = alignment.sort_values(["alignment_eligible", "alignment_score"], ascending=[False, False]).drop_duplicates("ticker", keep="first")
    rows = []
    for ar in a.to_dict(orient="records"):
        ticker = str(ar.get("ticker", ""))
        driver = str(ar.get("driver_id", ""))
        hits = board[(board["ticker"].astype(str) == ticker) & (board["driver_id"].astype(str) == driver)].copy()
        if hits.empty:
            # Fail closed rather than silently borrowing another driver row.
            rows.append({
                "contract": CONTRACT,
                "strategy_version": STRATEGY_VERSION,
                "ticker": ticker,
                "name": ar.get("name"),
                "driver_id": driver,
                "global_alignment_score": ar.get("alignment_score"),
                "score_is_probability": False,
                "entry_style": "NONE",
                "current_action": "AVOID",
                "entry_status": "DRIVER_LINEAGE_MISMATCH",
                "entry_structure_valid": False,
                "entry_executable": False,
                "blockers": "ENTRY_DRIVER_NOT_FOUND_IN_DECISION_BOARD",
                "why_now": "",
                "why_not_now": "ENTRY_DRIVER_NOT_FOUND_IN_DECISION_BOARD",
                "avg_turnover20_twd": np.nan,
                "auto_trade_allowed": False,
            })
            continue
        if "research_priority_score" in hits.columns:
            hits = hits.sort_values("research_priority_score", ascending=False)
        row = hits.iloc[0].to_dict()
        hist = histories.get(ticker, pd.DataFrame())
        plan = choose_plan(row, ar, hist, policy)
        plan["entry_driver_matches_alignment_driver"] = str(plan.get("driver_id")) == driver
        if not plan["entry_driver_matches_alignment_driver"]:
            plan["entry_structure_valid"] = False
            plan["current_action"] = "AVOID"
            plan["entry_status"] = "DRIVER_LINEAGE_MISMATCH"
            plan["blockers"] = ";".join(filter(None, [str(plan.get("blockers", "")), "ENTRY_DRIVER_ALIGNMENT_MISMATCH"]))
        rows.append(plan)

    plans = pd.DataFrame(rows)
    if plans.empty:
        return plans
    risked, meta = apply_entry_risk_gate_v2(plans)
    risked["risk_v2_contract"] = meta.get("contract")
    # EOD pipeline has no live executable quote; never emit BUY_NOW from yesterday's close.
    risked["entry_executable"] = False
    risked["buy_now_blocker"] = "LIVE_EXECUTABLE_QUOTE_REQUIRED"
    return risked


def _style_records(plans: pd.DataFrame, style: str) -> list[dict]:
    if plans.empty:
        return []
    p = plans[plans["entry_style"].eq(style)].copy()
    p["_score"] = pd.to_numeric(p.get("global_alignment_score"), errors="coerce").fillna(-1)
    status_rank = {
        "CONFIRMED_NEXT_SESSION_CONDITIONAL": 0,
        "PRICE_CONFIRMED_PARTICIPATION_UNCONFIRMED": 1,
        "CONTINUATION_PRICE_CONFIRMED_PARTICIPATION_UNCONFIRMED": 1,
        "WAITING_FOR_TRIGGER": 2,
        "WAITING_FOR_RECOVERY_TRIGGER": 2,
        "CONTINUATION_BASE_WAITING_FOR_TRIGGER": 2,
    }
    p["_status"] = p["entry_status"].map(status_rank).fillna(9)
    p = p.sort_values(["_status", "_score"], ascending=[True, False]).drop(columns=["_score", "_status"])
    return p.head(10).replace({np.nan: None}).to_dict(orient="records")


def write_outputs() -> tuple[pd.DataFrame, dict]:
    if not BOARD_PATH.exists() or not ALIGN_CSV_PATH.exists():
        raise RuntimeError("ENTRY_PLAN_V2_INPUT_MISSING")
    board = pd.read_csv(BOARD_PATH, dtype={"taiwan_code": str})
    alignment = pd.read_csv(ALIGN_CSV_PATH)
    tickers = alignment["ticker"].dropna().astype(str).drop_duplicates().tolist()
    histories = _download_histories(tickers)
    plans = build_canonical_plans(board, alignment, histories)
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    plans.to_csv(CSV_OUT, index=False)

    run_id = None
    if MANIFEST_PATH.exists():
        try:
            run_id = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("run_id")
        except Exception:
            pass
    payload = {
        "contract": CONTRACT,
        "schema_version": "2.1",
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": run_id,
        "status": "READY" if not plans.empty else "DATA_UNAVAILABLE",
        "canonical_driver_source": "GLOBAL_ALIGNMENT_V2",
        "score_is_probability": False,
        "buy_now_requires_live_executable_quote": True,
        "fresh": _style_records(plans, "FRESH_BREAKOUT"),
        "pullback": _style_records(plans, "PULLBACK_RECOVERY"),
        "continuation": _style_records(plans, "CONTINUATION_BASE"),
        "all_plans": plans.head(100).replace({np.nan: None}).to_dict(orient="records") if not plans.empty else [],
        "auto_trade_allowed": False,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return plans, payload


def main() -> None:
    try:
        plans, payload = write_outputs()
        print(f"Canonical Entry Plan V2 status={payload.get('status')} plans={len(plans)}")
    except Exception as exc:
        payload = {
            "contract": CONTRACT,
            "schema_version": "2.1",
            "strategy_version": STRATEGY_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "DATA_UNAVAILABLE",
            "failure": type(exc).__name__,
            "entry_executable": False,
            "auto_trade_allowed": False,
        }
        JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
        JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if CSV_OUT.exists():
            CSV_OUT.unlink()
        print(f"Canonical Entry Plan V2 status=DATA_UNAVAILABLE failure={type(exc).__name__}")


if __name__ == "__main__":
    main()
