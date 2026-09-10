from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

OUT = Path("output")
CONTRACT = "ALPHA_HUNTER_BUY_NOW_REPORT_V1"
ALLOWED_REGIMES = {"RISK_ON", "NORMAL"}


def _s(v: Any) -> str:
    return str(v or "").strip().upper()


def _plans_by_ticker(entries: dict) -> dict[str, dict]:
    plans = entries.get("all_plans") or []
    if not plans:
        plans = (entries.get("fresh") or []) + (entries.get("pullback") or []) + (entries.get("continuation") or [])
    return {str(p.get("ticker")): p for p in plans if isinstance(p, dict) and p.get("ticker")}


def build_buy_now_report(advisory: pd.DataFrame, regime: dict, entries: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    if advisory is None or advisory.empty or regime.get("status") != "READY" or entries.get("status") != "READY":
        return {
            "contract": CONTRACT,
            "status": "DATA_UNAVAILABLE",
            "generated_at": now,
            "recommendations": [],
            "reason": "Required validated advisory, risk-regime, or exact-entry artifact is unavailable.",
            "auto_trade_allowed": False,
        }

    regime_label = _s(regime.get("regime"))
    run_ids = {str(v) for v in advisory.get("run_id", pd.Series(dtype=str)).dropna().astype(str).unique() if str(v)}
    entry_run = str(entries.get("source_run_id", ""))
    if len(run_ids) != 1 or not entry_run or entry_run not in run_ids:
        return {
            "contract": CONTRACT,
            "status": "DATA_UNAVAILABLE",
            "generated_at": now,
            "risk_regime": regime_label,
            "recommendations": [],
            "reason": "Advisory and exact-entry artifacts are not from the same canonical run.",
            "auto_trade_allowed": False,
        }

    if regime_label not in ALLOWED_REGIMES:
        return {
            "contract": CONTRACT,
            "status": "NO_BUY_NOW",
            "generated_at": now,
            "source_run_id": next(iter(run_ids)),
            "risk_regime": regime_label,
            "recommendations": [],
            "reason": "Risk regime is not RISK_ON/NORMAL; no new immediate-buy recommendation is surfaced.",
            "auto_trade_allowed": False,
        }

    plans = _plans_by_ticker(entries)
    eligible: list[dict] = []
    for _, r in advisory.iterrows():
        ticker = str(r.get("ticker", "") or "")
        if not ticker:
            continue
        if _s(r.get("preferred_exposure")) != "STOCK":
            continue
        if _s(r.get("advisory_action")) != "BUY_BIAS_STOCK" or _s(r.get("advisory_confidence")) != "HIGH":
            continue
        if _s(r.get("dynamic_driver_state")) != "ACTIVE_RESEARCH_VALIDATED":
            continue
        if _s(r.get("provenance_status")) != "SOURCE_BACKED":
            continue
        if _s(r.get("semantic_breadth_state")) != "HEALTHY":
            continue
        if _s(r.get("reaction_state")) != "CONFIRMING":
            continue

        plan = plans.get(ticker)
        if not plan:
            continue
        if str(plan.get("driver_id", "")) != str(r.get("driver_id", "")):
            continue
        if not bool(plan.get("entry_structure_valid", False)):
            continue
        if _s((plan.get("global_confirmation") or {}).get("status")) != "PASS":
            continue
        if _s(plan.get("entry_status")) != "CONFIRMED_NEXT_SESSION_CONDITIONAL":
            continue
        if not bool(plan.get("risk_v2_pass", False)):
            continue
        lo, hi, invalid = plan.get("buy_zone_low"), plan.get("buy_zone_high"), plan.get("invalidation_price")
        if lo is None or hi is None or invalid is None:
            continue
        try:
            rank_score = float(r.get("research_priority_score", 0) or 0)
        except Exception:
            rank_score = 0.0
        eligible.append({
            "ticker": ticker,
            "name": r.get("name"),
            "driver_id": r.get("driver_id"),
            "semantic_theme": r.get("global_theme"),
            "semantic_breadth_state": r.get("semantic_breadth_state"),
            "entry_style": plan.get("entry_style"),
            "trigger_price": plan.get("trigger_price"),
            "buy_zone_low": lo,
            "buy_zone_high": hi,
            "invalidation_price": invalid,
            "execution_condition": "BUY ONLY IF LIVE EXECUTABLE QUOTE IS WITHIN THE CANONICAL BUY ZONE; OTHERWISE NO TRADE.",
            "research_priority_score": rank_score,
        })

    eligible.sort(key=lambda x: x["research_priority_score"], reverse=True)
    if eligible:
        # User-facing contract is intentionally low-noise: surface only the single best immediate opportunity.
        best = eligible[0]
        best.pop("research_priority_score", None)
        return {
            "contract": CONTRACT,
            "status": "BUY_NOW",
            "generated_at": now,
            "source_run_id": next(iter(run_ids)),
            "risk_regime": regime_label,
            "recommendations": [best],
            "reason": "One stock clears causal, company-edge, semantic-breadth, price-confirmation, exact-entry and portfolio-risk gates.",
            "auto_trade_allowed": False,
        }

    return {
        "contract": CONTRACT,
        "status": "NO_BUY_NOW",
        "generated_at": now,
        "source_run_id": next(iter(run_ids)),
        "risk_regime": regime_label,
        "recommendations": [],
        "reason": "No stock clears every immediate-buy gate. Watchlists and near-misses are intentionally suppressed.",
        "auto_trade_allowed": False,
    }


def write_outputs() -> dict:
    advisory_path = OUT / "cio_advisory.csv"
    regime_path = OUT / "risk_regime.json"
    entries_path = OUT / "entry_plans_v2.json"
    advisory = pd.read_csv(advisory_path, dtype={"taiwan_code": str}) if advisory_path.exists() else pd.DataFrame()
    regime = json.loads(regime_path.read_text(encoding="utf-8")) if regime_path.exists() else {}
    entries = json.loads(entries_path.read_text(encoding="utf-8")) if entries_path.exists() else {}
    payload = build_buy_now_report(advisory, regime, entries)
    (OUT / "buy_now_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    p = write_outputs()
    print(f"BUY NOW report status={p.get('status')} recommendations={len(p.get('recommendations') or [])}")


if __name__ == "__main__":
    main()
