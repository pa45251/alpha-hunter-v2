from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from portfolio_risk_v2 import apply_entry_risk_gate_v2

OUT = Path("output")
BOARD_PATH = OUT / "decision_board.csv"
ALIGN_PATH = OUT / "global_alignment_v2.json"
MANIFEST_PATH = OUT / "manifest.json"
CSV_OUT = OUT / "entry_plans_v2.csv"
JSON_OUT = OUT / "entry_plans_v2.json"

CONTRACT = "ALPHA_HUNTER_ENTRY_STRUCTURE_V2"
STRATEGY_VERSION = "ALPHA_HUNTER_ADVISORY_V2"


@dataclass(frozen=True)
class EntryPolicyV2:
    atr_lookback: int = 14
    fresh_window: int = 20
    pullback_window: int = 12
    continuation_window: int = 20
    continuation_prior_window: int = 20
    breakout_buffer_atr: float = 0.25
    stop_noise_atr: float = 0.25
    chase_allowance_atr: float = 0.75
    min_volume_ratio: float = 1.0
    min_history: int = 80


ENTRY_STYLE_FRESH = "FRESH_BREAKOUT"
ENTRY_STYLE_PULLBACK = "PULLBACK_RECOVERY"
ENTRY_STYLE_CONTINUATION = "CONTINUATION_BASE"


def _finite(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


def _f(v: Any, default: float = np.nan) -> float:
    return float(v) if _finite(v) else default


def tw_stock_tick(price: float) -> float:
    """TWSE/TPEX common-share price increment schedule used by the V2 stock lane."""
    p = float(price)
    if p < 10:
        return 0.01
    if p < 50:
        return 0.05
    if p < 100:
        return 0.10
    if p < 500:
        return 0.50
    if p < 1000:
        return 1.00
    return 5.00


def _round_up_tick(price: float, tick: float) -> float:
    return round(math.ceil((price - 1e-12) / tick) * tick, 6)


def _round_down_tick(price: float, tick: float) -> float:
    return round(math.floor((price + 1e-12) / tick) * tick, 6)


def _normalize_history(hist: pd.DataFrame) -> pd.DataFrame:
    if hist is None or hist.empty:
        return pd.DataFrame()
    h = hist.copy()
    if isinstance(h.columns, pd.MultiIndex):
        return pd.DataFrame()
    req = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in h.columns for c in req):
        return pd.DataFrame()
    h = h[req].copy()
    for c in req:
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h = h.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()
    return h


def simple_atr(hist: pd.DataFrame, n: int = 14) -> float:
    h = _normalize_history(hist)
    if len(h) < n + 1:
        return np.nan
    prev = h["Close"].shift(1)
    tr = pd.concat([
        (h["High"] - h["Low"]).abs(),
        (h["High"] - prev).abs(),
        (h["Low"] - prev).abs(),
    ], axis=1).max(axis=1)
    return float(tr.tail(n).mean())


def _median_true_range(hist: pd.DataFrame) -> float:
    h = _normalize_history(hist)
    if len(h) < 2:
        return np.nan
    prev = h["Close"].shift(1)
    tr = pd.concat([
        (h["High"] - h["Low"]).abs(),
        (h["High"] - prev).abs(),
        (h["Low"] - prev).abs(),
    ], axis=1).max(axis=1)
    return float(tr.dropna().median()) if tr.notna().any() else np.nan


def _avg_turnover20(hist: pd.DataFrame) -> float:
    h = _normalize_history(hist)
    if h.empty:
        return np.nan
    x = (h["Close"] * h["Volume"]).dropna().tail(20)
    return float(x.mean()) if len(x) >= 5 else np.nan


def _volume_ratio_prior20(hist: pd.DataFrame) -> float:
    h = _normalize_history(hist)
    if len(h) < 21:
        return np.nan
    prior = h["Volume"].iloc[-21:-1].replace(0, np.nan).dropna()
    if prior.empty:
        return np.nan
    baseline = float(prior.median())
    return float(h["Volume"].iloc[-1] / baseline) if baseline > 0 else np.nan


def _ma(hist: pd.DataFrame, n: int) -> float:
    h = _normalize_history(hist)
    if len(h) < n:
        return np.nan
    return float(h["Close"].rolling(n).mean().iloc[-1])


def _ma_slope(hist: pd.DataFrame, n: int = 20, slope_window: int = 10) -> float:
    h = _normalize_history(hist)
    s = h["Close"].rolling(n).mean().dropna().tail(slope_window)
    if len(s) < max(5, slope_window // 2):
        return np.nan
    return float(np.polyfit(np.arange(len(s), dtype=float), s.to_numpy(dtype=float), 1)[0])


def _base_range_slope(base: pd.DataFrame, atr: float) -> float:
    if base is None or base.empty or not _finite(atr) or atr <= 0:
        return np.nan
    y = base["Close"].to_numpy(dtype=float)
    slope = np.polyfit(np.arange(len(y), dtype=float), y, 1)[0]
    return float(slope * max(1, len(y) - 1) / atr)


def _price_structure(pivot: float, support: float, atr: float, policy: EntryPolicyV2) -> dict[str, float] | None:
    if not all(_finite(v) for v in [pivot, support, atr]) or atr <= 0 or pivot <= 0 or support <= 0:
        return None
    tick = tw_stock_tick(pivot)
    buffer = max(tick, policy.breakout_buffer_atr * atr)
    trigger = _round_up_tick(pivot + buffer, tick)
    invalidation = _round_down_tick(support - policy.stop_noise_atr * atr, tick)
    zone_high = _round_down_tick(pivot + policy.chase_allowance_atr * atr, tick)
    if invalidation <= 0 or invalidation >= trigger or zone_high < trigger:
        return None
    return {
        "tick_size": tick,
        "trigger_price": trigger,
        "buy_zone_low": trigger,
        "buy_zone_high": zone_high,
        "invalidation_price": invalidation,
    }


def _global_confirmation(alignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "PASS" if bool(alignment.get("alignment_eligible")) else "FAIL",
        "driver_id": alignment.get("driver_id"),
        "basket": alignment.get("international_theme"),
        "breadth_n": alignment.get("breadth_n"),
        "breadth_eligible": alignment.get("breadth_eligible"),
        "global_trend_score": alignment.get("global_trend_score"),
        "international_breadth_score": alignment.get("international_breadth_score"),
        "score_is_probability": False,
    }


def _common_gate_blockers(row: dict[str, Any], alignment: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(row.get("dynamic_driver_state", "")).upper() != "ACTIVE_RESEARCH_VALIDATED":
        blockers.append("CAUSAL_DRIVER_NOT_ACTIVE")
    if str(row.get("provenance_status", "")).upper() != "SOURCE_BACKED":
        blockers.append("COMPANY_EDGE_NOT_SOURCE_BACKED")
    if str(row.get("polarity", "")).upper() != "POSITIVE":
        blockers.append("NON_POSITIVE_TRANSMISSION")
    if not bool(alignment.get("alignment_eligible")):
        blockers.append("GLOBAL_ALIGNMENT_NOT_ELIGIBLE")
    reaction = str(row.get("reaction_state", "UNKNOWN")).upper()
    if reaction == "BROKEN":
        blockers.append("PRICE_STRUCTURE_BROKEN")
    if reaction == "EXTENDED":
        blockers.append("PRICE_EXTENDED")
    return blockers


def _plan_base(row: dict[str, Any], alignment: dict[str, Any], hist: pd.DataFrame, style: str, policy: EntryPolicyV2) -> dict[str, Any]:
    h = _normalize_history(hist)
    last = h.iloc[-1] if not h.empty else pd.Series(dtype=float)
    last_idx = h.index[-1] if not h.empty else None
    current_price = _f(last.get("Close")) if not h.empty else np.nan
    ma20 = _ma(h, 20)
    ma60 = _ma(h, 60)
    atr_now = simple_atr(h.iloc[:-1], policy.atr_lookback) if len(h) > policy.atr_lookback + 1 else np.nan
    return {
        "contract": CONTRACT,
        "strategy_version": STRATEGY_VERSION,
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "global_theme": row.get("global_theme"),
        "driver_id": row.get("driver_id"),
        "global_alignment_score": alignment.get("alignment_score"),
        "score_is_probability": False,
        "reaction_state": str(row.get("reaction_state", "UNKNOWN")).upper(),
        "entry_style": style,
        "current_action": "PREPARE",
        "current_price": current_price,
        "price_as_of_utc": pd.Timestamp(last_idx).isoformat() if last_idx is not None else None,
        "signal_as_of_utc": datetime.now(timezone.utc).isoformat(),
        "price_basis": "RAW_TRADEABLE_OHLC",
        "currency": "TWD",
        "instrument_type": "TAIWAN_COMMON_STOCK",
        "is_closed_bar": True,
        "atr14": atr_now,
        "atr_pct": (atr_now / current_price) if _finite(atr_now) and _finite(current_price) and current_price > 0 else np.nan,
        "ma20": ma20,
        "ma60": ma60,
        "rs20": _f(row.get("rs_20d_vs_bench")),
        "rs60": _f(row.get("rs_60d_vs_bench")),
        "keynes_v2": _f(row.get("keynes_v2")),
        "avg_turnover20_twd": _avg_turnover20(h),
        "volume_ratio20_prior_median": _volume_ratio_prior20(h),
        "global_confirmation": _global_confirmation(alignment),
        "entry_structure_valid": False,
        "entry_executable": False,
        "entry_status": "WATCHLIST",
        "trigger_price": np.nan,
        "buy_zone_low": np.nan,
        "buy_zone_high": np.nan,
        "invalidation_price": np.nan,
        "reference_pivot": np.nan,
        "base_start": None,
        "base_end": None,
        "base_high": np.nan,
        "base_low": np.nan,
        "support_zone": None,
        "recovery_trigger": np.nan,
        "close_confirmation_required": True,
        "blockers": "",
        "why_now": "",
        "why_not_now": "",
        "deployment_mode": "SHADOW_ADVISORY_ONLY",
        "auto_trade_allowed": False,
    }


def _apply_structure(plan: dict[str, Any], pivot: float, support: float, atr: float, policy: EntryPolicyV2) -> bool:
    levels = _price_structure(pivot, support, atr, policy)
    if levels is None:
        return False
    plan.update(levels)
    plan["reference_pivot"] = pivot
    plan["entry_structure_valid"] = True
    return True


def build_fresh_plan(row: dict[str, Any], alignment: dict[str, Any], hist: pd.DataFrame, policy: EntryPolicyV2) -> dict[str, Any]:
    plan = _plan_base(row, alignment, hist, ENTRY_STYLE_FRESH, policy)
    h = _normalize_history(hist)
    blockers = _common_gate_blockers(row, alignment)
    reaction = str(row.get("reaction_state", "UNKNOWN")).upper()
    if reaction not in {"PRE_CONFIRMATION", "EARLY_CONFIRMATION", "CONFIRMING"}:
        blockers.append("REACTION_NOT_FRESH_ENTRY_FAMILY")
    if len(h) < max(policy.min_history, policy.fresh_window + policy.atr_lookback + 2):
        blockers.append("INSUFFICIENT_OHLCV_HISTORY")
    if blockers:
        plan["current_action"] = "AVOID" if any(x in blockers for x in ["CAUSAL_DRIVER_NOT_ACTIVE", "PRICE_STRUCTURE_BROKEN"]) else "PREPARE"
        plan["blockers"] = ";".join(dict.fromkeys(blockers))
        plan["why_not_now"] = plan["blockers"]
        return plan

    pre = h.iloc[:-1]
    base = pre.tail(policy.fresh_window)
    atr = simple_atr(pre, policy.atr_lookback)
    pivot = float(base["High"].max())
    support = float(base["Low"].min())
    plan["base_start"] = pd.Timestamp(base.index[0]).isoformat()
    plan["base_end"] = pd.Timestamp(base.index[-1]).isoformat()
    plan["base_high"] = pivot
    plan["base_low"] = support
    if not _apply_structure(plan, pivot, support, atr, policy):
        plan["blockers"] = "INVALID_FRESH_PRICE_STRUCTURE"
        plan["why_not_now"] = plan["blockers"]
        return plan

    close = float(h["Close"].iloc[-1])
    vol_ratio = _volume_ratio_prior20(h)
    if close > float(plan["buy_zone_high"]):
        plan["current_action"] = "DONT_CHASE"
        plan["entry_status"] = "CONFIRMED_BUT_OVER_ZONE" if close >= float(plan["trigger_price"]) else "WATCHLIST"
        plan["why_not_now"] = "CURRENT_CLOSE_ABOVE_DYNAMIC_CHASE_ZONE"
    elif close >= float(plan["trigger_price"]):
        if not _finite(vol_ratio) or vol_ratio < policy.min_volume_ratio:
            plan["current_action"] = "PREPARE"
            plan["entry_status"] = "PRICE_CONFIRMED_PARTICIPATION_UNCONFIRMED"
            plan["why_not_now"] = "VOLUME_CONFIRMATION_NOT_MET"
        else:
            plan["current_action"] = "PREPARE"
            plan["entry_status"] = "CONFIRMED_NEXT_SESSION_CONDITIONAL"
            plan["why_now"] = "PRIOR_KNOWN_PIVOT_BROKEN_ON_CLOSED_BAR_WITH_GLOBAL_CAUSAL_ALIGNMENT"
            plan["why_not_now"] = "LIVE_EXECUTABLE_QUOTE_REQUIRED_FOR_BUY_NOW"
    else:
        plan["current_action"] = "WAIT_BREAKOUT"
        plan["entry_status"] = "WAITING_FOR_TRIGGER"
        plan["why_not_now"] = "CLOSE_BELOW_FROZEN_BREAKOUT_TRIGGER"
    return plan


def build_pullback_plan(row: dict[str, Any], alignment: dict[str, Any], hist: pd.DataFrame, policy: EntryPolicyV2) -> dict[str, Any]:
    plan = _plan_base(row, alignment, hist, ENTRY_STYLE_PULLBACK, policy)
    h = _normalize_history(hist)
    blockers = _common_gate_blockers(row, alignment)
    reaction = str(row.get("reaction_state", "UNKNOWN")).upper()
    if reaction not in {"PULLBACK", "PERSISTENT"}:
        blockers.append("REACTION_NOT_PULLBACK_FAMILY")
    if len(h) < max(policy.min_history, 60):
        blockers.append("INSUFFICIENT_OHLCV_HISTORY")
    if not (_finite(row.get("rs_60d_vs_bench")) and float(row.get("rs_60d_vs_bench")) > 0):
        blockers.append("ESTABLISHED_RS60_NOT_PRESENT")
    if blockers:
        plan["current_action"] = "AVOID" if "PRICE_STRUCTURE_BROKEN" in blockers else "PREPARE"
        plan["blockers"] = ";".join(dict.fromkeys(blockers))
        plan["why_not_now"] = plan["blockers"]
        return plan

    pre = h.iloc[:-1]
    pb = pre.tail(policy.pullback_window)
    low_pos = int(np.argmin(pb["Low"].to_numpy(dtype=float)))
    if low_pos >= len(pb) - 2:
        plan["current_action"] = "WAIT_PULLBACK"
        plan["why_not_now"] = "PULLBACK_LOW_NOT_YET_FOLLOWED_BY_RECOVERY_RESISTANCE"
        return plan
    support = float(pb["Low"].iloc[low_pos])
    after_low = pb.iloc[low_pos + 1:]
    pivot = float(after_low["High"].max())
    atr = simple_atr(pre, policy.atr_lookback)
    plan["support_zone"] = {
        "low": support,
        "ma20": _ma(pre, 20),
        "ma60": _ma(pre, 60),
    }
    plan["base_start"] = pd.Timestamp(pb.index[low_pos]).isoformat()
    plan["base_end"] = pd.Timestamp(pb.index[-1]).isoformat()
    plan["base_low"] = support
    plan["base_high"] = pivot
    if not _apply_structure(plan, pivot, support, atr, policy):
        plan["blockers"] = "INVALID_PULLBACK_RECOVERY_STRUCTURE"
        plan["why_not_now"] = plan["blockers"]
        return plan
    plan["recovery_trigger"] = plan["trigger_price"]

    close = float(h["Close"].iloc[-1])
    if close < support:
        plan["current_action"] = "AVOID"
        plan["entry_status"] = "PULLBACK_SUPPORT_FAILED"
        plan["why_not_now"] = "CURRENT_CLOSE_BELOW_IDENTIFIED_PULLBACK_SUPPORT"
    elif close > float(plan["buy_zone_high"]):
        plan["current_action"] = "DONT_CHASE"
        plan["entry_status"] = "RECOVERY_CONFIRMED_BUT_OVER_ZONE"
        plan["why_not_now"] = "CURRENT_CLOSE_ABOVE_DYNAMIC_CHASE_ZONE"
    elif close >= float(plan["trigger_price"]):
        plan["current_action"] = "PREPARE"
        plan["entry_status"] = "CONFIRMED_NEXT_SESSION_CONDITIONAL"
        plan["why_now"] = "PULLBACK_RESISTANCE_RECOVERED_WHILE_ESTABLISHED_TREND_AND_GLOBAL_DRIVER_REMAIN_VALID"
        plan["why_not_now"] = "LIVE_EXECUTABLE_QUOTE_REQUIRED_FOR_BUY_NOW"
    else:
        plan["current_action"] = "WAIT_PULLBACK"
        plan["entry_status"] = "WAITING_FOR_RECOVERY_TRIGGER"
        plan["why_not_now"] = "SUPPORT_ZONE_IS_NOT_AN_ENTRY;_RECOVERY_TRIGGER_NOT_RECLAIMED"
    return plan


def build_continuation_plan(row: dict[str, Any], alignment: dict[str, Any], hist: pd.DataFrame, policy: EntryPolicyV2) -> dict[str, Any]:
    plan = _plan_base(row, alignment, hist, ENTRY_STYLE_CONTINUATION, policy)
    h = _normalize_history(hist)
    blockers = _common_gate_blockers(row, alignment)
    reaction = str(row.get("reaction_state", "UNKNOWN")).upper()
    if reaction != "PERSISTENT":
        blockers.append("REACTION_NOT_PERSISTENT")
    if len(h) < max(policy.min_history, policy.continuation_window + policy.continuation_prior_window + 25):
        blockers.append("INSUFFICIENT_OHLCV_HISTORY")
    if not (_finite(row.get("rs_60d_vs_bench")) and float(row.get("rs_60d_vs_bench")) > 0):
        blockers.append("ESTABLISHED_RS60_NOT_PRESENT")
    if blockers:
        plan["current_action"] = "AVOID" if "PRICE_STRUCTURE_BROKEN" in blockers else "PREPARE"
        plan["blockers"] = ";".join(dict.fromkeys(blockers))
        plan["why_not_now"] = plan["blockers"]
        return plan

    pre = h.iloc[:-1]
    base = pre.tail(policy.continuation_window)
    prior = pre.iloc[-(policy.continuation_window + policy.continuation_prior_window):-policy.continuation_window]
    atr = simple_atr(pre, policy.atr_lookback)
    recent_tr = _median_true_range(base.tail(max(5, policy.continuation_window // 2)))
    prior_tr = _median_true_range(prior)
    ma20_pre = _ma(pre, 20)
    ma60_pre = _ma(pre, 60)
    ma20_slope = _ma_slope(pre, 20, 10)
    base_width = float(base["High"].max() - base["Low"].min())
    slope_atr = _base_range_slope(base, atr)

    contraction = _finite(recent_tr) and _finite(prior_tr) and recent_tr <= prior_tr
    width_ok = _finite(atr) and atr > 0 and base_width <= 8.0 * atr
    slope_ok = _finite(slope_atr) and abs(slope_atr) <= 1.5
    trend_ok = all(_finite(v) for v in [ma20_pre, ma60_pre, ma20_slope]) and ma20_pre > ma60_pre and ma20_slope >= 0

    ma20_series = pre["Close"].rolling(20).mean()
    start_i = pre.index.get_loc(base.index[0])
    ma20_start = _f(ma20_series.iloc[start_i]) if start_i < len(ma20_series) else np.nan
    dist_start = abs(float(base["Close"].iloc[0]) - ma20_start) / atr if _finite(ma20_start) and _finite(atr) and atr > 0 else np.nan
    dist_end = abs(float(base["Close"].iloc[-1]) - ma20_pre) / atr if _finite(ma20_pre) and _finite(atr) and atr > 0 else np.nan
    catchup_ok = _finite(dist_end) and (_finite(dist_start) and dist_end <= dist_start or dist_end <= 1.5)

    quality_flags = {
        "volatility_contracted": bool(contraction),
        "base_width_stable": bool(width_ok),
        "range_not_directional": bool(slope_ok),
        "ma20_ma60_structure_intact": bool(trend_ok),
        "ma20_catchup": bool(catchup_ok),
        "rs_persistent": bool(_finite(row.get("rs_60d_vs_bench")) and float(row.get("rs_60d_vs_bench")) > 0),
    }
    plan["continuation_quality"] = quality_flags
    if not all(quality_flags.values()):
        plan["current_action"] = "WAIT_BREAKOUT"
        plan["entry_status"] = "NO_VALID_CONTINUATION_BASE"
        plan["why_not_now"] = "CONTINUATION_BASE_QUALITY_NOT_COMPLETE"
        plan["blockers"] = ";".join([k.upper() for k, v in quality_flags.items() if not v])
        return plan

    pivot = float(base["High"].max())
    support = float(base["Low"].min())
    plan["base_start"] = pd.Timestamp(base.index[0]).isoformat()
    plan["base_end"] = pd.Timestamp(base.index[-1]).isoformat()
    plan["base_high"] = pivot
    plan["base_low"] = support
    if not _apply_structure(plan, pivot, support, atr, policy):
        plan["blockers"] = "INVALID_CONTINUATION_STRUCTURE"
        plan["why_not_now"] = plan["blockers"]
        return plan

    close = float(h["Close"].iloc[-1])
    vol_ratio = _volume_ratio_prior20(h)
    if close > float(plan["buy_zone_high"]):
        plan["current_action"] = "DONT_CHASE"
        plan["entry_status"] = "CONTINUATION_CONFIRMED_BUT_OVER_ZONE"
        plan["why_not_now"] = "CURRENT_CLOSE_ABOVE_DYNAMIC_CHASE_ZONE"
    elif close >= float(plan["trigger_price"]):
        if not _finite(vol_ratio) or vol_ratio < policy.min_volume_ratio:
            plan["current_action"] = "PREPARE"
            plan["entry_status"] = "CONTINUATION_PRICE_CONFIRMED_PARTICIPATION_UNCONFIRMED"
            plan["why_not_now"] = "VOLUME_CONFIRMATION_NOT_MET"
        else:
            plan["current_action"] = "PREPARE"
            plan["entry_status"] = "CONFIRMED_NEXT_SESSION_CONDITIONAL"
            plan["why_now"] = "PERSISTENT_TREND_FORMED_A_VALID_CONTRACTING_BASE_AND_CLOSED_ABOVE_FROZEN_TRIGGER"
            plan["why_not_now"] = "LIVE_EXECUTABLE_QUOTE_REQUIRED_FOR_BUY_NOW"
    else:
        plan["current_action"] = "WAIT_BREAKOUT"
        plan["entry_status"] = "CONTINUATION_BASE_WAITING_FOR_TRIGGER"
        plan["why_not_now"] = "VALID_CONTINUATION_BASE_EXISTS_BUT_BREAKOUT_NOT_CONFIRMED"
    return plan


def choose_plan(row: dict[str, Any], alignment: dict[str, Any], hist: pd.DataFrame, policy: EntryPolicyV2 = EntryPolicyV2()) -> dict[str, Any]:
    reaction = str(row.get("reaction_state", "UNKNOWN")).upper()
    if reaction in {"PRE_CONFIRMATION", "EARLY_CONFIRMATION", "CONFIRMING"}:
        return build_fresh_plan(row, alignment, hist, policy)
    if reaction == "PULLBACK":
        return build_pullback_plan(row, alignment, hist, policy)
    if reaction == "PERSISTENT":
        cont = build_continuation_plan(row, alignment, hist, policy)
        if bool(cont.get("entry_structure_valid")) or cont.get("entry_status") == "NO_VALID_CONTINUATION_BASE":
            return cont
        return build_pullback_plan(row, alignment, hist, policy)
    plan = _plan_base(row, alignment, hist, "NONE", policy)
    blockers = _common_gate_blockers(row, alignment)
    if reaction == "BROKEN":
        plan["current_action"] = "AVOID"
    elif reaction == "EXTENDED":
        plan["current_action"] = "DONT_CHASE"
    else:
        plan["current_action"] = "PREPARE"
    plan["blockers"] = ";".join(dict.fromkeys(blockers + ["NO_ENTRY_STYLE_FOR_CURRENT_REACTION"]))
    plan["why_not_now"] = plan["blockers"]
    return plan


def _download_histories(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    tickers = list(dict.fromkeys([str(t) for t in tickers if str(t).strip()]))
    if not tickers:
        return {}
    raw = yf.download(tickers, period=period, auto_adjust=False, group_by="ticker", progress=False, threads=True)
    result: dict[str, pd.DataFrame] = {}
    if len(tickers) == 1:
        if raw is not None and not raw.empty:
            result[tickers[0]] = raw.copy()
        return result
    for t in tickers:
        try:
            d = raw[t].copy()
            if not d.empty:
                result[t] = d
        except Exception:
            continue
    return result


def _load_alignment_map() -> dict[str, dict[str, Any]]:
    if not ALIGN_PATH.exists():
        return {}
    try:
        payload = json.loads(ALIGN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(r.get("ticker")): r for r in (payload.get("top_aligned") or []) if r.get("ticker")}


def _load_all_alignment_rows() -> dict[str, dict[str, Any]]:
    csv_path = OUT / "global_alignment_v2.csv"
    if not csv_path.exists():
        return _load_alignment_map()
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return _load_alignment_map()
    return {str(r.get("ticker")): r for r in df.to_dict(orient="records") if r.get("ticker")}


def build_entry_plans_from_inputs(board: pd.DataFrame, alignment_rows: dict[str, dict[str, Any]], histories: dict[str, pd.DataFrame], policy: EntryPolicyV2 = EntryPolicyV2()) -> pd.DataFrame:
    if board is None or board.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    # One price episode per ticker. Pick the highest research-priority driver row after alignment gating.
    x = board.copy()
    if "research_priority_score" in x.columns:
        x = x.sort_values("research_priority_score", ascending=False)
    x = x.drop_duplicates("ticker", keep="first")
    for r in x.to_dict(orient="records"):
        ticker = str(r.get("ticker", ""))
        align = alignment_rows.get(ticker, {})
        hist = histories.get(ticker, pd.DataFrame())
        plan = choose_plan(r, align, hist, policy)
        rows.append(plan)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    risked, meta = apply_entry_risk_gate_v2(out)
    risked["risk_v2_contract"] = meta.get("contract")
    # End-of-day plans can be confirmed, but without a live executable quote BUY_NOW remains false.
    risked["entry_executable"] = False
    risked["buy_now_blocker"] = "LIVE_EXECUTABLE_QUOTE_REQUIRED"
    return risked


def write_outputs() -> tuple[pd.DataFrame, dict[str, Any]]:
    if not BOARD_PATH.exists() or not ALIGN_PATH.exists():
        raise RuntimeError("ENTRY_STRUCTURE_V2_INPUT_MISSING")
    board = pd.read_csv(BOARD_PATH, dtype={"taiwan_code": str})
    alignment_rows = _load_all_alignment_rows()
    tickers = [str(t) for t in board.get("ticker", pd.Series(dtype=str)).dropna().unique().tolist()]
    histories = _download_histories(tickers)
    plans = build_entry_plans_from_inputs(board, alignment_rows, histories)
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    plans.to_csv(CSV_OUT, index=False)

    run_id = None
    if MANIFEST_PATH.exists():
        try:
            run_id = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("run_id")
        except Exception:
            run_id = None

    def records_for(style: str) -> list[dict[str, Any]]:
        if plans.empty:
            return []
        p = plans[plans["entry_style"].eq(style)].copy()
        order = {"CONFIRMED_NEXT_SESSION_CONDITIONAL": 0, "WAITING_FOR_TRIGGER": 1, "CONTINUATION_BASE_WAITING_FOR_TRIGGER": 1, "WAITING_FOR_RECOVERY_TRIGGER": 1}
        p["_order"] = p["entry_status"].map(order).fillna(9)
        score = pd.to_numeric(p.get("global_alignment_score"), errors="coerce").fillna(-1)
        p["_score"] = score
        p = p.sort_values(["_order", "_score"], ascending=[True, False]).drop(columns=["_order", "_score"])
        return p.head(10).replace({np.nan: None}).to_dict(orient="records")

    payload = {
        "contract": CONTRACT,
        "schema_version": "2.0",
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": run_id,
        "status": "READY" if not plans.empty else "DATA_UNAVAILABLE",
        "score_is_probability": False,
        "buy_now_requires_live_executable_quote": True,
        "fresh": records_for(ENTRY_STYLE_FRESH),
        "pullback": records_for(ENTRY_STYLE_PULLBACK),
        "continuation": records_for(ENTRY_STYLE_CONTINUATION),
        "all_plans": plans.head(100).replace({np.nan: None}).to_dict(orient="records") if not plans.empty else [],
        "auto_trade_allowed": False,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return plans, payload


def main() -> None:
    try:
        plans, payload = write_outputs()
        print(f"Entry Structure V2 status={payload.get('status')} plans={len(plans)}")
    except Exception as exc:
        # Market-data outages must fail closed and leave a machine-readable artifact.
        payload = {
            "contract": CONTRACT,
            "schema_version": "2.0",
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
        print(f"Entry Structure V2 status=DATA_UNAVAILABLE failure={type(exc).__name__}")


if __name__ == "__main__":
    main()
