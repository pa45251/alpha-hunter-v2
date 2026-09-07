from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
from typing import Callable, Iterable
import json

import pandas as pd

from shadow_validation import (
    BENCHMARK_TICKER,
    DEFAULT_HORIZONS,
    DIRECTIONAL_AVOID_ACTIONS,
    DIRECTIONAL_LONG_ACTIONS,
    _benchmark_return,
    _clean_prices,
    _default_price_loader,
    _entry_and_exit,
)

CONTRACT = "ALPHA_HUNTER_SHADOW_VALIDATION_V2"


def _as_utc_timestamp(now_utc: datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(now_utc)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _closed_session_cutoff(ticker: str, now_utc: datetime | pd.Timestamp) -> pd.Timestamp:
    """Latest calendar date whose daily bar can safely be treated as closed.

    Taiwan instruments use 13:35 Asia/Taipei (five-minute safety margin after cash close).
    Other tickers use 16:10 America/New_York as a conservative US/default daily-bar cutoff.
    Holidays/weekends need no special calendar here: nonexistent sessions have no price rows.
    """
    now = _as_utc_timestamp(now_utc)
    t = str(ticker or "").upper()
    if t.endswith(".TW") or t.endswith(".TWO") or t == "^TWII":
        local = now.tz_convert("Asia/Taipei")
        d = local.normalize()
        if local.time() < time(13, 35):
            d = d - pd.Timedelta(days=1)
        return d.tz_localize(None)

    local = now.tz_convert("America/New_York")
    d = local.normalize()
    if local.time() < time(16, 10):
        d = d - pd.Timedelta(days=1)
    return d.tz_localize(None)


def _clip_to_closed_sessions(prices: pd.DataFrame, ticker: str, now_utc: datetime | pd.Timestamp) -> pd.DataFrame:
    p = _clean_prices(prices)
    if p.empty:
        return p
    cutoff = _closed_session_cutoff(ticker, now_utc)
    return p[p.index <= cutoff].copy()


def evaluate_shadow_audit_v2(
    audit: pd.DataFrame,
    price_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    benchmark_ticker: str = BENCHMARK_TICKER,
    now_utc: datetime | None = None,
) -> pd.DataFrame:
    """Point-in-time shadow evaluation using only fully closed sessions available by cutoff."""
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
    # Loader shape may include a partial/future-labelled daily row. The explicit closed-session
    # clip below is the authority, not the provider's returned endpoint.
    end = (_as_utc_timestamp(now).tz_localize(None) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    cache: dict[str, pd.DataFrame] = {}

    def prices(t: str) -> pd.DataFrame:
        if t not in cache:
            raw = loader(t, start, end)
            cache[t] = _clip_to_closed_sessions(raw, t, now)
        return cache[t]

    bench = prices(benchmark_ticker)
    rows: list[dict] = []
    for r in x.itertuples(index=False):
        ticker = str(getattr(r, "ticker", "")).strip()
        if not ticker:
            continue
        p = prices(ticker)
        cutoff = _closed_session_cutoff(ticker, now)
        for h in hlist:
            outcome = _entry_and_exit(p, getattr(r, "audit_at_utc", ""), h)
            if outcome is None:
                continue
            entry_date, entry_open, exit_date, exit_close = outcome
            # Future-data sentinel: this should be impossible after clipping; keep an explicit
            # guard so a later refactor cannot silently mature an unavailable observation.
            if exit_date > cutoff:
                continue
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
                "validated_at_utc": _as_utc_timestamp(now).isoformat(),
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
                "evaluation_cutoff_date": cutoff.date().isoformat(),
                "future_data_cutoff_enforced": True,
                "forward_return": raw_ret,
                "benchmark_ticker": benchmark_ticker,
                "benchmark_return": bench_ret,
                "excess_return": excess,
                "directional_scored": scored,
                "directional_correct": correct,
            })
    return pd.DataFrame(rows)


def build_validation_report_v2(results: pd.DataFrame) -> dict:
    report = {
        "contract": CONTRACT,
        "validation_version": "2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_assumption": "NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_DATE",
        "benchmark": BENCHMARK_TICKER,
        "threshold_tuning_allowed": False,
        "metric_scope": "PROSPECTIVE_GROSS_SIGNAL_OUTCOMES_ONLY_NOT_PORTFOLIO_STRATEGY_ACCEPTANCE",
        "cost_adjusted": False,
        "live_promotion_allowed": False,
        "future_data_cutoff_enforced": True,
        "partial_or_future_daily_bars_allowed": False,
        "hindsight_rule": "Historical decisions are immutable. Outcomes are appended only after fully closed market sessions mature; validation never rewrites past states or tunes gates.",
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


def write_shadow_validation_v2(
    audit_path: str = "output/shadow_audit.csv",
    output_csv: str = "output/shadow_validation.csv",
    report_json: str = "output/shadow_validation_report.json",
) -> tuple[pd.DataFrame, dict]:
    p = Path(audit_path)
    audit = pd.read_csv(p, dtype={"taiwan_code": str}) if p.exists() else pd.DataFrame()
    results = evaluate_shadow_audit_v2(audit)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_csv, index=False)
    report = build_validation_report_v2(results)
    Path(report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, report
