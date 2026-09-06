from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
import json

import pandas as pd


DEFAULT_HORIZONS = (5, 20, 60)
BENCHMARK_TICKER = "^TWII"
DIRECTIONAL_LONG_ACTIONS = {"BUY_STOCK", "BUY_ETF"}
DIRECTIONAL_AVOID_ACTIONS = {"AVOID_BROKEN"}


def _default_price_loader(ticker: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    try:
        x = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False, threads=False)
    except Exception:
        return pd.DataFrame()
    if x is None or x.empty:
        return pd.DataFrame()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = [str(c[0]) for c in x.columns]
    return x


def _clean_prices(x: pd.DataFrame) -> pd.DataFrame:
    if x is None or x.empty:
        return pd.DataFrame(columns=["Open", "Close"])
    y = x.copy()
    y.index = pd.to_datetime(y.index, errors="coerce").tz_localize(None).normalize()
    y = y[~y.index.isna()].sort_index()
    for c in ["Open", "Close"]:
        if c not in y.columns:
            y[c] = pd.NA
        y[c] = pd.to_numeric(y[c], errors="coerce")
    return y[["Open", "Close"]].dropna(how="all")


def _entry_and_exit(prices: pd.DataFrame, audit_at_utc: str, horizon: int) -> tuple[pd.Timestamp, float, pd.Timestamp, float] | None:
    """Conservative shadow execution: next trading session open strictly after the decision's Taipei calendar date."""
    p = _clean_prices(prices)
    if p.empty:
        return None
    audit = pd.to_datetime(audit_at_utc, utc=True, errors="coerce")
    if pd.isna(audit):
        return None
    decision_date = audit.tz_convert("Asia/Taipei").tz_localize(None).normalize()
    eligible = p[p.index > decision_date]
    if eligible.empty:
        return None
    entry_date = eligible.index[0]
    entry_pos = p.index.get_loc(entry_date)
    exit_pos = entry_pos + int(horizon) - 1
    if exit_pos >= len(p):
        return None
    entry_open = p.iloc[entry_pos]["Open"]
    exit_close = p.iloc[exit_pos]["Close"]
    if pd.isna(entry_open) or pd.isna(exit_close) or float(entry_open) <= 0:
        return None
    return entry_date, float(entry_open), p.index[exit_pos], float(exit_close)


def _benchmark_return(bench: pd.DataFrame, entry_date: pd.Timestamp, exit_date: pd.Timestamp) -> float | None:
    b = _clean_prices(bench)
    if entry_date not in b.index or exit_date not in b.index:
        return None
    o, c = b.loc[entry_date, "Open"], b.loc[exit_date, "Close"]
    if pd.isna(o) or pd.isna(c) or float(o) <= 0:
        return None
    return float(c) / float(o) - 1.0


def evaluate_shadow_audit(
    audit: pd.DataFrame,
    price_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    benchmark_ticker: str = BENCHMARK_TICKER,
    now_utc: datetime | None = None,
) -> pd.DataFrame:
    """Evaluate public decision states ex-post without changing historical decisions.

    The validator never tunes thresholds. It records executable next-session-open outcomes and
    benchmark-relative returns only after a horizon has actually matured.
    """
    if audit is None or audit.empty:
        return pd.DataFrame()
    loader = price_loader or _default_price_loader
    hlist = tuple(sorted({int(h) for h in horizons if int(h) > 0}))
    now = now_utc or datetime.now(timezone.utc)

    x = audit.copy()
    for c in ["audit_at_utc", "run_id", "ticker", "driver_id", "candidate_action", "portfolio_action"]:
        if c not in x.columns:
            x[c] = ""
    parsed = pd.to_datetime(x["audit_at_utc"], utc=True, errors="coerce")
    valid_dates = parsed.dropna()
    if valid_dates.empty:
        return pd.DataFrame()

    start = (valid_dates.min().tz_convert("Asia/Taipei").tz_localize(None) - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    # Add calendar slack so 60 trading sessions can mature without a second query shape.
    end = (pd.Timestamp(now).tz_convert("UTC").tz_localize(None) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    cache: dict[str, pd.DataFrame] = {}

    def prices(t: str) -> pd.DataFrame:
        if t not in cache:
            cache[t] = loader(t, start, end)
        return cache[t]

    bench = prices(benchmark_ticker)
    rows: list[dict] = []
    for r in x.itertuples(index=False):
        ticker = str(getattr(r, "ticker", "")).strip()
        if not ticker:
            continue
        p = prices(ticker)
        for h in hlist:
            outcome = _entry_and_exit(p, getattr(r, "audit_at_utc", ""), h)
            if outcome is None:
                continue
            entry_date, entry_open, exit_date, exit_close = outcome
            raw_ret = exit_close / entry_open - 1.0
            bench_ret = _benchmark_return(bench, entry_date, exit_date)
            excess = raw_ret - bench_ret if bench_ret is not None else None
            portfolio_action = str(getattr(r, "portfolio_action", "")).upper()
            candidate_action = str(getattr(r, "candidate_action", "")).upper()
            scored = False
            correct = None
            if portfolio_action in DIRECTIONAL_LONG_ACTIONS and excess is not None:
                scored, correct = True, excess > 0
            elif candidate_action in DIRECTIONAL_AVOID_ACTIONS and excess is not None:
                scored, correct = True, excess <= 0
            rows.append({
                "validated_at_utc": now.isoformat(),
                "run_id": str(getattr(r, "run_id", "")),
                "audit_at_utc": str(getattr(r, "audit_at_utc", "")),
                "ticker": ticker,
                "driver_id": str(getattr(r, "driver_id", "")),
                "candidate_action": candidate_action,
                "portfolio_action": portfolio_action,
                "horizon_sessions": h,
                "entry_date": entry_date.date().isoformat(),
                "entry_basis": "NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_DATE",
                "exit_date": exit_date.date().isoformat(),
                "forward_return": raw_ret,
                "benchmark_ticker": benchmark_ticker,
                "benchmark_return": bench_ret,
                "excess_return": excess,
                "directional_scored": scored,
                "directional_correct": correct,
            })
    return pd.DataFrame(rows)


def build_validation_report(results: pd.DataFrame) -> dict:
    report = {
        "contract": "ALPHA_HUNTER_SHADOW_VALIDATION",
        "validation_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_assumption": "NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_DATE",
        "benchmark": BENCHMARK_TICKER,
        "threshold_tuning_allowed": False,
        "metric_scope": "GROSS_SIGNAL_OUTCOMES_ONLY_NOT_PORTFOLIO_STRATEGY_ACCEPTANCE",
        "cost_adjusted": False,
        "live_promotion_allowed": False,
        "hindsight_rule": "Historical decisions are immutable. Outcomes are appended only after horizons mature; validation never rewrites past states or tunes gates.",
        "matured_outcomes": 0,
        "directional_scored_outcomes": 0,
        "directional_hit_rate": None,
        "by_horizon": {},
    }
    if results is None or results.empty:
        return report
    report["matured_outcomes"] = int(len(results))
    scored = results[results["directional_scored"].fillna(False).astype(bool)]
    report["directional_scored_outcomes"] = int(len(scored))
    if not scored.empty:
        report["directional_hit_rate"] = float(scored["directional_correct"].astype(bool).mean())
    for h, g in results.groupby("horizon_sessions"):
        excess = pd.to_numeric(g["excess_return"], errors="coerce").dropna()
        s = g[g["directional_scored"].fillna(False).astype(bool)]
        report["by_horizon"][str(int(h))] = {
            "matured": int(len(g)),
            "mean_excess_return": float(excess.mean()) if not excess.empty else None,
            "median_excess_return": float(excess.median()) if not excess.empty else None,
            "directional_scored": int(len(s)),
            "directional_hit_rate": float(s["directional_correct"].astype(bool).mean()) if not s.empty else None,
        }
    return report


def write_shadow_validation(
    audit_path: str = "output/shadow_audit.csv",
    output_csv: str = "output/shadow_validation.csv",
    report_json: str = "output/shadow_validation_report.json",
) -> tuple[pd.DataFrame, dict]:
    p = Path(audit_path)
    audit = pd.read_csv(p, dtype={"taiwan_code": str}) if p.exists() else pd.DataFrame()
    results = evaluate_shadow_audit(audit)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_csv, index=False)
    report = build_validation_report(results)
    Path(report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, report
