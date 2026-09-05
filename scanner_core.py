from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd
import yfinance as yf

TRADING_DAYS = 252

@dataclass
class ScanConfig:
    lookback: str = "2y"
    min_obs: int = 140
    benchmark: str = "SPY"
    output_dir: str = "output"


def _safe_ret(series: pd.Series, n: int) -> float:
    s = series.dropna()
    if len(s) <= n:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1.0)


def _slope(series: pd.Series, n: int) -> float:
    s = series.dropna().tail(n)
    if len(s) < max(5, n // 2):
        return np.nan
    y = s.values.astype(float)
    x = np.arange(len(y), dtype=float)
    # normalized linear slope per day
    denom = np.nanmean(y)
    if not np.isfinite(denom) or denom == 0:
        return np.nan
    return float(np.polyfit(x, y, 1)[0] / denom)


def efficiency_ratio(close: pd.Series, n: int = 20) -> float:
    s = close.dropna().tail(n + 1)
    if len(s) < n + 1:
        return np.nan
    net = abs(float(s.iloc[-1] - s.iloc[0]))
    path = float(s.diff().abs().sum())
    return net / path if path > 0 else np.nan


def max_drawdown(close: pd.Series, n: int = 20) -> float:
    s = close.dropna().tail(n + 1)
    if s.empty:
        return np.nan
    dd = s / s.cummax() - 1.0
    return float(dd.min())


def keynes_legacy(close: pd.Series) -> float:
    """Exact spirit of the user's original Keynes indicator.

    K = 8 * 20D momentum - 1.5 * (90D std(price) / 90D EMA(price))
    """
    s = close.dropna()
    if len(s) < 100:
        return np.nan
    momentum = _safe_ret(s, 20)
    stdev = float(s.rolling(90).std().iloc[-1])
    ema = float(s.ewm(span=90, adjust=False).mean().iloc[-1])
    cov = stdev / ema if ema else np.nan
    if not np.isfinite(momentum) or not np.isfinite(cov):
        return np.nan
    return float(momentum * 8.0 - cov * 1.5)


def keynes_v2(close: pd.Series, n: int = 20) -> float:
    """Trend-quality version.

    Risk-adjusted n-day return multiplied by Efficiency Ratio.
    It penalizes noisy/choppy paths rather than penalizing price dispersion caused by a clean trend.
    This is an experimental feature, not a calibrated trading rule.
    """
    s = close.dropna()
    if len(s) < n + 5:
        return np.nan
    ret_n = _safe_ret(s, n)
    daily = s.pct_change().dropna().tail(n)
    vol_n = float(daily.std(ddof=1) * math.sqrt(n)) if len(daily) > 2 else np.nan
    er = efficiency_ratio(s, n)
    if not np.isfinite(ret_n) or not np.isfinite(vol_n) or not np.isfinite(er) or vol_n <= 0:
        return np.nan
    return float((ret_n / vol_n) * er)


def atr_pct(hist: pd.DataFrame, n: int = 14) -> float:
    h = hist["High"].astype(float)
    l = hist["Low"].astype(float)
    c = hist["Close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().iloc[-1]
    return float(atr / c.iloc[-1]) if c.iloc[-1] else np.nan


def trend_state(close: pd.Series) -> str:
    s = close.dropna()
    if len(s) < 65:
        return "UNKNOWN"
    curr = s.iloc[-1]
    ma20 = s.rolling(20).mean().iloc[-1]
    ma60 = s.rolling(60).mean().iloc[-1]
    if curr > ma20 > ma60:
        return "STRONG_UP"
    if curr < ma20 and curr > ma60:
        return "PULLBACK"
    if curr < ma60:
        return "BEAR"
    if curr > ma20 and ma20 < ma60:
        return "REBOUND"
    return "RANGE"


def extract_features(hist: pd.DataFrame, benchmark_close: Optional[pd.Series] = None) -> Dict[str, float | str]:
    h = hist.dropna(subset=["Close"]).copy()
    c = h["Close"].astype(float)
    if len(c) < 65:
        return {}
    curr = float(c.iloc[-1])
    ma5 = float(c.rolling(5).mean().iloc[-1])
    ma20 = float(c.rolling(20).mean().iloc[-1])
    ma60 = float(c.rolling(60).mean().iloc[-1])
    high52 = float(h["High"].tail(TRADING_DAYS).max()) if "High" in h else float(c.tail(TRADING_DAYS).max())
    vol_ratio = np.nan
    if "Volume" in h:
        v = h["Volume"].astype(float)
        base = float(v.rolling(20).mean().iloc[-1])
        vol_ratio = float(v.iloc[-1] / base) if base > 0 else np.nan

    out: Dict[str, float | str] = {
        "price": curr,
        "ret_1d": _safe_ret(c, 1),
        "ret_5d": _safe_ret(c, 5),
        "ret_20d": _safe_ret(c, 20),
        "ret_60d": _safe_ret(c, 60),
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "ma20_slope": _slope(c.rolling(20).mean(), 10),
        "ma60_slope": _slope(c.rolling(60).mean(), 20),
        "bias20": curr / ma20 - 1.0 if ma20 else np.nan,
        "dist_52w_high": curr / high52 - 1.0 if high52 else np.nan,
        "volume_ratio20": vol_ratio,
        "atr_pct14": atr_pct(h),
        "er20": efficiency_ratio(c, 20),
        "vol20": float(c.pct_change().dropna().tail(20).std(ddof=1) * math.sqrt(20)),
        "maxdd20": max_drawdown(c, 20),
        "keynes_legacy": keynes_legacy(c),
        "keynes_v2": keynes_v2(c, 20),
        "trend": trend_state(c),
    }
    if benchmark_close is not None:
        b = benchmark_close.dropna()
        aligned = pd.concat([c.rename("asset"), b.rename("bench")], axis=1).dropna()
        for n in (5, 20, 60):
            if len(aligned) > n:
                ar = aligned["asset"].iloc[-1] / aligned["asset"].iloc[-1-n] - 1
                br = aligned["bench"].iloc[-1] / aligned["bench"].iloc[-1-n] - 1
                out[f"rs_{n}d_vs_bench"] = float(ar - br)
            else:
                out[f"rs_{n}d_vs_bench"] = np.nan
    return out


def _download(tickers: Iterable[str], period: str = "2y") -> Dict[str, pd.DataFrame]:
    tickers = list(dict.fromkeys([t for t in tickers if t]))
    if not tickers:
        return {}
    raw = yf.download(tickers, period=period, auto_adjust=False, group_by="ticker", progress=False, threads=True)
    result: Dict[str, pd.DataFrame] = {}
    if len(tickers) == 1:
        result[tickers[0]] = raw.copy()
        return result
    for t in tickers:
        try:
            df = raw[t].copy()
            if not df.empty:
                result[t] = df
        except Exception:
            continue
    return result


def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average")


def add_cross_section_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Adds transparent provisional scores while preserving all raw features.

    We deliberately avoid optimization. Score weights are simple priors and are intended for audit.
    """
    x = df.copy()
    for col in ["rs_20d_vs_bench", "rs_60d_vs_bench", "ret_5d", "ma20_slope", "volume_ratio20", "dist_52w_high", "keynes_v2"]:
        if col not in x:
            x[col] = np.nan

    x["acceleration"] = x["ret_5d"] - x["ret_20d"] / 4.0
    # High is good. For distance to high, closer to zero is better.
    ranks = {
        "r_rs20": _pct_rank(x["rs_20d_vs_bench"]),
        "r_rs60": _pct_rank(x["rs_60d_vs_bench"]),
        "r_accel": _pct_rank(x["acceleration"]),
        "r_slope": _pct_rank(x["ma20_slope"]),
        "r_volume": _pct_rank(x["volume_ratio20"]),
        "r_high": _pct_rank(x["dist_52w_high"]),
        "r_quality": _pct_rank(x["keynes_v2"]),
    }
    for k, v in ranks.items():
        x[k] = v

    # Provisional heuristic, intentionally not fitted.
    x["leader_score_v1"] = (
        0.25*x["r_rs20"] + 0.20*x["r_rs60"] + 0.15*x["r_accel"] +
        0.10*x["r_slope"] + 0.10*x["r_volume"] + 0.10*x["r_high"] + 0.10*x["r_quality"]
    )
    return x


def classify_leader(row: pd.Series) -> str:
    rs20 = row.get("rs_20d_vs_bench", np.nan)
    rs60 = row.get("rs_60d_vs_bench", np.nan)
    accel = row.get("acceleration", np.nan)
    score = row.get("leader_score_v1", np.nan)
    kv2 = row.get("keynes_v2", np.nan)
    trend = row.get("trend", "")

    if trend == "BEAR" and (not np.isfinite(rs20) or rs20 < 0):
        return "WEAKENING"
    if np.isfinite(rs20) and np.isfinite(rs60) and rs20 > 0 and rs60 > 0 and score >= 0.70:
        if np.isfinite(accel) and accel > 0:
            return "PERSISTENT"
        return "PULLBACK_LEADER"
    if np.isfinite(rs20) and rs20 > 0 and np.isfinite(accel) and accel > 0 and score >= 0.55:
        return "EMERGING"
    if np.isfinite(accel) and accel > 0 and np.isfinite(kv2) and kv2 > 0 and score >= 0.45:
        return "EARLY_EMERGING"
    if np.isfinite(rs20) and rs20 < 0 and np.isfinite(accel) and accel < 0:
        return "WEAKENING"
    return "NEUTRAL"


def compute_theme_breadth(stock_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if stock_df.empty:
        return pd.DataFrame()
    for theme, g in stock_df.groupby("theme", dropna=False):
        n = len(g)
        if n == 0:
            continue
        rows.append({
            "theme": theme,
            "n": n,
            "above_ma20_pct": float((g["price"] > g["ma20"]).mean()),
            "above_ma60_pct": float((g["price"] > g["ma60"]).mean()),
            "positive_rs5_pct": float((g["rs_5d_vs_bench"] > 0).mean()),
            "positive_rs20_pct": float((g["rs_20d_vs_bench"] > 0).mean()),
            "near_20d_high_pct": float((g["dist_52w_high"] > -0.05).mean()),
            "median_rs20": float(g["rs_20d_vs_bench"].median()),
            "median_keynes_v2": float(g["keynes_v2"].median()),
            "median_keynes_legacy": float(g["keynes_legacy"].median()),
        })
    return pd.DataFrame(rows).sort_values(["positive_rs20_pct", "median_rs20"], ascending=False)


def update_registry(current: pd.DataFrame, previous_path: Path) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    prev = pd.DataFrame()
    if previous_path.exists():
        try:
            prev = pd.read_csv(previous_path)
        except Exception:
            prev = pd.DataFrame()
    prev_map = prev.set_index("ticker").to_dict("index") if not prev.empty and "ticker" in prev else {}

    out = []
    for _, r in current.iterrows():
        p = prev_map.get(r["ticker"], {})
        prev_state = p.get("state", "")
        raw = classify_leader(r)
        streak = int(p.get("confirmation_streak", 0) or 0)

        confirm_family = {"EMERGING", "PERSISTENT", "PULLBACK_LEADER", "EARLY_EMERGING"}
        if raw in confirm_family:
            streak = streak + 1 if prev_state in confirm_family else 1
        else:
            streak = 0

        # Hysteresis: one-day spikes stay candidate; persistent requires repeated confirmation.
        weak_streak = 0
        if raw == "PERSISTENT" and streak < 3:
            state = "EMERGING"
        elif raw == "EARLY_EMERGING" and streak < 2:
            state = "CANDIDATE"
        elif raw == "WEAKENING" and prev_state in {"PERSISTENT", "PULLBACK_LEADER"}:
            weak_streak = int(p.get("weakening_streak", 0) or 0) + 1
            state = "WEAKENING" if weak_streak >= 2 else prev_state
        else:
            state = raw

        out.append({
            "ticker": r["ticker"],
            "theme": r.get("theme", "Unclassified"),
            "name": r.get("name", ""),
            "state": state,
            "raw_state": raw,
            "confirmation_streak": streak,
            "weakening_streak": weak_streak,
            "leader_score_v1": r.get("leader_score_v1", np.nan),
            "rs20": r.get("rs_20d_vs_bench", np.nan),
            "rs60": r.get("rs_60d_vs_bench", np.nan),
            "keynes_legacy": r.get("keynes_legacy", np.nan),
            "keynes_v2": r.get("keynes_v2", np.nan),
            "updated_at_utc": now,
        })
    return pd.DataFrame(out).sort_values(["theme", "leader_score_v1"], ascending=[True, False])


def run_scan(universe_csv: str = "config/universe.csv", config: ScanConfig = ScanConfig()) -> Dict[str, pd.DataFrame]:
    uni = pd.read_csv(universe_csv)
    required = {"ticker", "theme"}
    if not required.issubset(uni.columns):
        raise ValueError(f"universe.csv must contain {required}")

    tickers = uni["ticker"].dropna().astype(str).unique().tolist()
    if config.benchmark not in tickers:
        tickers = [config.benchmark] + tickers

    data = _download(tickers, config.lookback)
    bench_hist = data.get(config.benchmark)
    if bench_hist is None or bench_hist.empty:
        raise RuntimeError(f"Benchmark {config.benchmark} unavailable")
    bench_close = bench_hist["Close"]

    rows = []
    for _, meta in uni.iterrows():
        t = str(meta["ticker"])
        hist = data.get(t)
        if hist is None or hist.empty or len(hist.dropna(subset=["Close"])) < config.min_obs:
            continue
        f = extract_features(hist, bench_close)
        if not f:
            continue
        row = meta.to_dict()
        row.update(f)
        rows.append(row)

    stocks = pd.DataFrame(rows)
    if stocks.empty:
        raise RuntimeError("No stock features produced")
    stocks = add_cross_section_scores(stocks)
    stocks["raw_leader_state"] = stocks.apply(classify_leader, axis=1)
    stocks = stocks.sort_values("leader_score_v1", ascending=False)

    breadth = compute_theme_breadth(stocks)
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    registry_path = out_dir / "leader_registry.csv"
    registry = update_registry(stocks, registry_path)

    return {"stocks": stocks, "breadth": breadth, "registry": registry}


def write_outputs(results: Dict[str, pd.DataFrame], output_dir: str = "output") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    results["stocks"].to_csv(out / "market_snapshot.csv", index=False)
    results["breadth"].to_csv(out / "theme_breadth.csv", index=False)
    results["registry"].to_csv(out / "leader_registry.csv", index=False)

    payload = {
        "generated_at_utc": ts,
        "schema_version": "2.0",
        "notes": {
            "keynes_legacy": "Original user heuristic retained unchanged in spirit.",
            "keynes_v2": "Experimental risk-adjusted trend-quality feature using return volatility and efficiency ratio.",
            "leader_score_v1": "Provisional, non-optimized ranking score. Raw features should drive audit.",
        },
        "top_leaders": results["registry"].query("state in ['PERSISTENT','EMERGING','PULLBACK_LEADER']").head(50).replace({np.nan: None}).to_dict("records"),
        "theme_breadth": results["breadth"].replace({np.nan: None}).to_dict("records"),
    }
    (out / "market_snapshot.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_audit_log(results: Dict[str, pd.DataFrame], path: str = "output/feature_history.csv") -> None:
    stocks = results["stocks"].copy()
    stocks["snapshot_date_utc"] = datetime.now(timezone.utc).date().isoformat()
    keep = [
        "snapshot_date_utc","ticker","theme","price","ret_1d","ret_5d","ret_20d","ret_60d",
        "rs_5d_vs_bench","rs_20d_vs_bench","rs_60d_vs_bench","acceleration","er20","vol20","maxdd20",
        "keynes_legacy","keynes_v2","leader_score_v1","raw_leader_state"
    ]
    stocks = stocks[[c for c in keep if c in stocks.columns]]
    p = Path(path)
    if p.exists():
        old = pd.read_csv(p)
        stocks = pd.concat([old, stocks], ignore_index=True)
        stocks = stocks.drop_duplicates(["snapshot_date_utc","ticker"], keep="last")
    stocks.to_csv(p, index=False)
