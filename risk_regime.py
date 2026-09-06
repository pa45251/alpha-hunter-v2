from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

OUT = Path("output")
POLICY_PATH = Path("config/portfolio_allocation_policy.json")
OUTPUT_PATH = OUT / "risk_regime.json"

RISK_TICKERS = [
    "^VIX", "^VXN", "SPY", "QQQ", "RSP", "IWM", "MTUM",
    "HYG", "LQD", "ACWI", "VGK", "EWJ", "EWY", "EWT", "FXI",
]
CORE_TICKERS = ["^VIX", "^VXN", "SPY", "QQQ"]
GLOBAL_TICKERS = ["ACWI", "VGK", "EWJ", "EWY", "EWT", "FXI"]


def _close(hist: pd.DataFrame) -> pd.Series:
    if hist is None or hist.empty:
        return pd.Series(dtype=float)
    if "Adj Close" in hist.columns and hist["Adj Close"].notna().any():
        return hist["Adj Close"].astype(float).dropna()
    if "Close" in hist.columns:
        return hist["Close"].astype(float).dropna()
    return pd.Series(dtype=float)


def _download(period: str = "1y") -> dict[str, pd.DataFrame]:
    raw = yf.download(RISK_TICKERS, period=period, auto_adjust=False, group_by="ticker", progress=False, threads=True)
    out: dict[str, pd.DataFrame] = {}
    for ticker in RISK_TICKERS:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                frame = raw[ticker].copy()
            else:
                frame = raw.copy() if len(RISK_TICKERS) == 1 else pd.DataFrame()
            if not frame.empty:
                out[ticker] = frame.dropna(how="all")
        except Exception:
            continue
    return out


def _features(hist: pd.DataFrame) -> dict[str, Any]:
    s = _close(hist)
    if len(s) < 65:
        return {}
    price = float(s.iloc[-1])
    ma20 = float(s.rolling(20).mean().iloc[-1])
    ma60 = float(s.rolling(60).mean().iloc[-1])
    ret5 = float(s.iloc[-1] / s.iloc[-6] - 1.0) if len(s) > 5 else 0.0
    ret20 = float(s.iloc[-1] / s.iloc[-21] - 1.0) if len(s) > 20 else 0.0
    idx = pd.Timestamp(s.index[-1])
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return {
        "price": price,
        "ma20": ma20,
        "ma60": ma60,
        "ret5": ret5,
        "ret20": ret20,
        "above_ma20": bool(price > ma20),
        "above_ma60": bool(price > ma60),
        "ma20_above_ma60": bool(ma20 > ma60),
        "last_date": idx.date().isoformat(),
    }


def _ratio_features(a: pd.DataFrame, b: pd.DataFrame) -> dict[str, Any]:
    sa, sb = _close(a), _close(b)
    if sa.empty or sb.empty:
        return {}
    ia = pd.DatetimeIndex(pd.to_datetime(sa.index))
    ib = pd.DatetimeIndex(pd.to_datetime(sb.index))
    if ia.tz is not None:
        ia = ia.tz_localize(None)
    if ib.tz is not None:
        ib = ib.tz_localize(None)
    sa = sa.copy(); sb = sb.copy()
    sa.index = ia.normalize(); sb.index = ib.normalize()
    x = pd.concat([sa.rename("a"), sb.rename("b")], axis=1).dropna()
    if len(x) < 65:
        return {}
    r = x["a"] / x["b"]
    price = float(r.iloc[-1])
    ma20 = float(r.rolling(20).mean().iloc[-1])
    ma60 = float(r.rolling(60).mean().iloc[-1])
    ret20 = float(r.iloc[-1] / r.iloc[-21] - 1.0)
    return {"price": price, "ma20": ma20, "ma60": ma60, "ret20": ret20, "above_ma20": price > ma20, "above_ma60": price > ma60}


def _vol_points(price: float, ma20: float, ret5: float, bands: tuple[float, float, float]) -> int:
    a, b, c = bands
    if price >= c:
        pts = 20
    elif price >= b:
        pts = 15
    elif price >= a:
        pts = 8
    else:
        pts = 0
    if price > ma20:
        pts += 5
    if ret5 > 0.10:
        pts += 3
    return pts


def _band_for(score: int, policy: dict[str, Any]) -> dict[str, Any]:
    for band in policy["cash_regime"]["bands"]:
        if score <= int(band["max_score"]):
            return band
    return policy["cash_regime"]["bands"][-1]


def build_risk_regime(histories: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    live_download = histories is None
    histories = histories or _download()
    f = {t: _features(histories.get(t, pd.DataFrame())) for t in RISK_TICKERS}
    missing_core = [t for t in CORE_TICKERS if not f.get(t)]
    if missing_core:
        return {
            "contract": "ALPHA_HUNTER_RISK_REGIME",
            "schema_version": "1.0",
            "generated_at": datetime.now().astimezone().isoformat(),
            "status": "DATA_UNAVAILABLE",
            "missing_core_signals": missing_core,
            "regime": "UNKNOWN",
            "risk_score": None,
            "target_cash_pct": None,
            "gross_multiplier": None,
            "auto_trade_allowed": False,
        }

    # Synthetic histories used in tests can have arbitrary dates. For live downloads,
    # fail closed if any core signal is older than the policy freshness limit.
    max_age = int(policy["cash_regime"].get("max_data_age_days", 5))
    stale_core: list[str] = []
    if live_download:
        today = datetime.now().astimezone().date()
        for ticker in CORE_TICKERS:
            d = pd.Timestamp(f[ticker]["last_date"]).date()
            if (today - d).days > max_age:
                stale_core.append(ticker)
    if stale_core:
        return {
            "contract": "ALPHA_HUNTER_RISK_REGIME",
            "schema_version": "1.0",
            "generated_at": datetime.now().astimezone().isoformat(),
            "status": "STALE_CORE_DATA",
            "stale_core_signals": stale_core,
            "regime": "UNKNOWN",
            "risk_score": None,
            "target_cash_pct": None,
            "gross_multiplier": None,
            "auto_trade_allowed": False,
        }

    components: dict[str, int] = {}
    components["VIX_VXN"] = min(
        48,
        _vol_points(f["^VIX"]["price"], f["^VIX"]["ma20"], f["^VIX"]["ret5"], (20.0, 25.0, 30.0))
        + _vol_points(f["^VXN"]["price"], f["^VXN"]["ma20"], f["^VXN"]["ret5"], (25.0, 30.0, 35.0)),
    )

    trend_pts = 0
    for t in ["SPY", "QQQ"]:
        z = f[t]
        if not z["above_ma20"]:
            trend_pts += 4
        if not z["above_ma60"]:
            trend_pts += 7
        if not z["ma20_above_ma60"]:
            trend_pts += 3
    components["US_TREND"] = min(28, trend_pts)

    breadth_pts = 0
    for t, pts in [("RSP", 4), ("IWM", 4), ("MTUM", 3)]:
        if f.get(t) and f[t].get("ret20", 0.0) < f["SPY"].get("ret20", 0.0):
            breadth_pts += pts
    components["US_BREADTH"] = breadth_pts

    credit = _ratio_features(histories.get("HYG", pd.DataFrame()), histories.get("LQD", pd.DataFrame()))
    credit_pts = 0
    if credit:
        if credit["ret20"] < 0:
            credit_pts += 5
        if not credit["above_ma60"]:
            credit_pts += 5
    components["CREDIT"] = credit_pts

    global_rows = [f[t] for t in GLOBAL_TICKERS if f.get(t)]
    global_pts = 0
    global_above_ma60 = None
    if global_rows:
        global_above_ma60 = sum(1 for z in global_rows if z["above_ma60"]) / len(global_rows)
        if global_above_ma60 < 0.33:
            global_pts = 10
        elif global_above_ma60 < 0.50:
            global_pts = 7
        elif global_above_ma60 < 0.67:
            global_pts = 4
    components["GLOBAL_BREADTH"] = global_pts

    score = min(100, int(sum(components.values())))
    band = _band_for(score, policy)
    dates = [z.get("last_date") for z in f.values() if z.get("last_date")]
    latest_date = max(dates) if dates else None

    return {
        "contract": "ALPHA_HUNTER_RISK_REGIME",
        "schema_version": "1.0",
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "READY",
        "risk_snapshot_date": latest_date,
        "regime": band["label"],
        "risk_score": score,
        "target_cash_pct": float(band["target_cash_pct"]),
        "gross_multiplier": float(band["gross_multiplier"]),
        "components": components,
        "signals": {
            "vix": {k: f["^VIX"][k] for k in ["price", "ma20", "ret5", "last_date"]},
            "vxn": {k: f["^VXN"][k] for k in ["price", "ma20", "ret5", "last_date"]},
            "spy": {k: f["SPY"][k] for k in ["price", "ma20", "ma60", "ret20", "last_date"]},
            "qqq": {k: f["QQQ"][k] for k in ["price", "ma20", "ma60", "ret20", "last_date"]},
            "credit_hyg_lqd": credit,
            "global_above_ma60_pct": global_above_ma60,
        },
        "method": "Unfitted heuristic combining volatility, US trend, breadth, credit and global breadth. It is an advisory risk budget, not an order trigger.",
        "auto_trade_allowed": False,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = build_risk_regime()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Risk regime: status={payload.get('status')} regime={payload.get('regime')} score={payload.get('risk_score')} target_cash={payload.get('target_cash_pct')}")


if __name__ == "__main__":
    main()
