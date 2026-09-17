from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from scanner_core import (
    TAIPEI_TZ,
    ScanConfig,
    _price_series,
    add_cross_section_scores,
    compute_theme_breadth,
    extract_features,
)

TWSE_ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
TPEX_ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"


@dataclass
class TaiwanScanConfig:
    lookback: str = "1y"
    min_obs: int = 140
    benchmark: str = "^TWII"
    batch_size: int = 80
    # Maximum expensive research load, not a target that must be filled.
    top_candidates: int = 100
    primary_research_cap: int = 100
    min_price: float = 5.0
    # Liquidity must be durable, not created by one or two abnormal volume days.
    min_turnover20: float = 300_000_000.0
    # Defaults to 50% of the configured mean-turnover floor. With the production
    # mean floor of TWD 300m this is TWD 150m; custom configs scale coherently.
    min_median_turnover20: float | None = None
    # When qualified names exceed research capacity, EARLY names may occupy at most
    # this fraction. This is a ceiling, never a reserved quota.
    early_max_fraction: float = 0.30
    output_dir: str = "output"

    def __post_init__(self) -> None:
        self.top_candidates = min(max(0, int(self.top_candidates)), max(0, int(self.primary_research_cap)))
        if self.min_median_turnover20 is None:
            self.min_median_turnover20 = 0.5 * float(self.min_turnover20)
        else:
            self.min_median_turnover20 = max(0.0, float(self.min_median_turnover20))
        self.early_max_fraction = min(1.0, max(0.0, float(self.early_max_fraction)))


def _decode_twse_response(resp: requests.Response) -> str:
    """TWSE ISIN pages are commonly Big5/CP950 encoded.

    Try declared/apparent encoding first, then Big5/CP950 fallbacks.
    """
    candidates = [resp.encoding, resp.apparent_encoding, "big5", "cp950", "utf-8"]
    for enc in [x for x in candidates if x]:
        try:
            text = resp.content.decode(enc, errors="strict")
            if "有價證券" in text or "產業別" in text or "市場別" in text:
                return text
        except Exception:
            pass
    return resp.content.decode("big5", errors="replace")


def _parse_isin_table(html: str, exchange: str, suffix: str) -> pd.DataFrame:
    tables = pd.read_html(io.StringIO(html), header=0)
    if not tables:
        raise RuntimeError(f"No ISIN table parsed for {exchange}")
    df = max(tables, key=len).copy()
    df.columns = [str(c).strip() for c in df.columns]
    first = df.columns[0]
    industry_col = next((c for c in df.columns if "產業別" in c), None)
    market_col = next((c for c in df.columns if "市場別" in c), None)
    listed_col = next((c for c in df.columns if "上市日" in c or "上櫃日" in c), None)
    cfi_col = next((c for c in df.columns if "CFI" in c.upper()), None)

    rows = []
    for _, r in df.iterrows():
        raw = str(r.get(first, "")).strip()
        m = re.match(r"^(\d{4})\s*[\u3000\s]+(.+)$", raw)
        if not m:
            continue
        code, name = m.group(1), m.group(2).strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        industry = str(r.get(industry_col, "未分類")).strip() if industry_col else "未分類"
        cfi = str(r.get(cfi_col, "")).strip().upper() if cfi_col else ""
        if cfi and not cfi.startswith("ES"):
            continue
        if industry in {"", "nan", "NaN"}:
            continue
        market = str(r.get(market_col, exchange)).strip() if market_col else exchange
        listed_date = str(r.get(listed_col, "")).strip() if listed_col else ""
        rows.append({
            "code": code,
            "ticker": f"{code}{suffix}",
            "name": name,
            "industry": industry if industry and industry != "nan" else "未分類",
            "exchange": exchange,
            "market": market,
            "listed_date": listed_date,
            "cfi_code": cfi,
            "benchmark": "^TWII",
        })
    out = pd.DataFrame(rows).drop_duplicates("ticker")
    if out.empty:
        raise RuntimeError(f"Parsed zero common stocks for {exchange}")
    return out


def fetch_taiwan_universe(timeout: int = 30) -> pd.DataFrame:
    headers = {"User-Agent": "Mozilla/5.0 AlphaHunter/2.4"}
    parts = []
    for url, exchange, suffix in [
        (TWSE_ISIN_URL, "TWSE", ".TW"),
        (TPEX_ISIN_URL, "TPEX", ".TWO"),
    ]:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        text = _decode_twse_response(resp)
        parts.append(_parse_isin_table(text, exchange, suffix))
    uni = pd.concat(parts, ignore_index=True).drop_duplicates("ticker")
    uni["theme"] = uni["industry"]
    uni["region"] = "TW"
    uni["source"] = "TWSE_ISIN"
    return uni.sort_values(["exchange", "code"]).reset_index(drop=True)


def _download_chunked(tickers: Iterable[str], period: str, batch_size: int = 80) -> Dict[str, pd.DataFrame]:
    tickers = list(dict.fromkeys([str(t) for t in tickers if t]))
    result: Dict[str, pd.DataFrame] = {}
    for start in range(0, len(tickers), batch_size):
        chunk = tickers[start:start + batch_size]
        last_exc = None
        for attempt in range(2):
            try:
                raw = yf.download(
                    chunk,
                    period=period,
                    auto_adjust=False,
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )
                if len(chunk) == 1:
                    if not raw.empty:
                        result[chunk[0]] = raw.copy()
                else:
                    for t in chunk:
                        try:
                            d = raw[t].copy()
                            if not d.empty:
                                result[t] = d
                        except Exception:
                            continue
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        if last_exc:
            print(f"Warning: batch {start}-{start+len(chunk)-1} failed: {last_exc}")
        time.sleep(0.3)
    return result


def _add_turnover_feature(hist: pd.DataFrame, f: dict) -> None:
    try:
        close = hist["Close"].astype(float)
        vol = hist["Volume"].astype(float)
        turnover = (close * vol).dropna().tail(20)
        f["avg_turnover20_twd"] = float(turnover.mean()) if not turnover.empty else np.nan
        f["median_turnover20_twd"] = float(turnover.median()) if not turnover.empty else np.nan
        # Informational execution-capacity proxy only: 2% participation over two sessions.
        f["liquidity_capacity_2pct_2d_twd"] = (
            float(turnover.median()) * 0.04 if not turnover.empty else np.nan
        )
    except Exception:
        f["avg_turnover20_twd"] = np.nan
        f["median_turnover20_twd"] = np.nan
        f["liquidity_capacity_2pct_2d_twd"] = np.nan


def _col(df: pd.DataFrame, name: str, default=np.nan) -> pd.Series:
    if name in df.columns:
        return df[name]
    return pd.Series(default, index=df.index)


def add_taiwan_candidate_score(df: pd.DataFrame) -> pd.DataFrame:
    """Transparent Taiwan discovery/research-priority features.

    Scanner scores allocate research attention; they are not expected-return rankings
    or trade signals. Lifecycle stage and extension risk are kept separate so an
    otherwise valid trend is not semantically overwritten merely because price is hot.
    """
    x = add_cross_section_scores(df)
    x["r_turnover"] = x["avg_turnover20_twd"].rank(pct=True, method="average")

    rs5 = pd.to_numeric(_col(x, "rs_5d_vs_bench"), errors="coerce")
    rs20 = pd.to_numeric(_col(x, "rs_20d_vs_bench"), errors="coerce")
    x["rs_acceleration"] = rs5 - rs20 / 4.0
    x["r_rs_accel"] = x["rs_acceleration"].rank(pct=True, method="average")

    bias = pd.to_numeric(_col(x, "bias20", 0.0), errors="coerce").fillna(0.0)
    x["extension_quality"] = (1.0 - (bias.abs() / 0.20)).clip(0, 1)
    x["r_extension"] = x["extension_quality"].rank(pct=True, method="average")
    x["taiwan_candidate_score_v1"] = (
        0.20 * x["r_rs20"]
        + 0.25 * x["r_accel"]
        + 0.20 * x["r_quality"]
        + 0.10 * x["r_slope"]
        + 0.10 * x["r_volume"]
        + 0.05 * x["r_turnover"]
        + 0.10 * x["r_extension"]
    )

    # Keep the historical v2 score for downstream compatibility/audit lineage.
    x["taiwan_early_score_v2"] = (
        0.30 * x["r_accel"]
        + 0.25 * x["r_quality"]
        + 0.15 * x["r_slope"]
        + 0.10 * x["r_volume"]
        + 0.10 * x["r_turnover"]
        + 0.10 * x["r_extension"]
    )
    # v3 adds relative-strength acceleration on the same 5D-equivalent scale.
    x["taiwan_early_score_v3"] = (
        0.25 * x["r_accel"]
        + 0.20 * x["r_rs_accel"]
        + 0.20 * x["r_quality"]
        + 0.15 * x["r_slope"]
        + 0.10 * x["r_volume"]
        + 0.05 * x["r_turnover"]
        + 0.05 * x["r_extension"]
    )

    rs60 = pd.to_numeric(_col(x, "rs_60d_vs_bench"), errors="coerce").fillna(-999)
    accel = pd.to_numeric(_col(x, "acceleration"), errors="coerce").fillna(-999)
    rs_accel = pd.to_numeric(x["rs_acceleration"], errors="coerce").fillna(-999)
    ma20_slope = pd.to_numeric(_col(x, "ma20_slope"), errors="coerce").fillna(-999)
    keynes = pd.to_numeric(_col(x, "keynes_v2"), errors="coerce").fillna(-999)
    ret5 = pd.to_numeric(_col(x, "ret_5d", 0.0), errors="coerce").fillna(0.0)
    trend = _col(x, "trend", "UNKNOWN").fillna("UNKNOWN").astype(str)
    rs20_filled = rs20.fillna(-999)

    broken = (
        trend.eq("BEAR")
        & (ma20_slope <= 0)
        & (rs20_filled < 0)
        & (rs_accel <= 0)
    )
    persistent = trend.eq("STRONG_UP") & (rs20_filled > 0) & (rs60 > 0)
    pullback = trend.eq("PULLBACK") & (rs20_filled > 0)
    confirmed = trend.eq("STRONG_UP") & (rs20_filled > 0)

    # EARLY is deliberately stricter than a generic "improving" label. It must
    # already be a REBOUND, have a rising MA20 and improving relative strength,
    # then pass at least two of three supporting signals. BEAR names cannot qualify.
    early_votes = (
        (accel > 0).astype(int)
        + (rs20_filled > 0).astype(int)
        + (keynes > 0).astype(int)
    )
    early = (
        trend.eq("REBOUND")
        & (ma20_slope > 0)
        & (rs_accel > 0)
        & (early_votes >= 2)
    )

    x["trend_stage"] = "WATCH"
    x.loc[broken, "trend_stage"] = "BROKEN"
    x.loc[early, "trend_stage"] = "EARLY"
    x.loc[confirmed, "trend_stage"] = "CONFIRMED"
    x.loc[pullback, "trend_stage"] = "PULLBACK"
    x.loc[persistent, "trend_stage"] = "PERSISTENT"

    # Compatibility surface for existing downstream consumers. EXTENDED is no
    # longer a lifecycle state; it lives only in extension_risk.
    x["reaction_state"] = x["trend_stage"].map({
        "BROKEN": "BROKEN",
        "EARLY": "PRE_CONFIRMATION",
        "CONFIRMED": "CONFIRMING",
        "PULLBACK": "PULLBACK",
        "PERSISTENT": "PERSISTENT",
        "WATCH": "UNKNOWN",
    }).fillna("UNKNOWN")
    x["extension_risk"] = np.where((bias > 0.20) | (ret5 > 0.25), "EXTENDED", "NORMAL")
    # Legacy compatibility only: old consumers still recognize reaction_state=EXTENDED.
    # trend_stage is the canonical lifecycle field and is never overwritten.
    x.loc[x["extension_risk"].eq("EXTENDED"), "reaction_state"] = "EXTENDED"
    return x


def _ensure_selection_columns(stocks: pd.DataFrame) -> pd.DataFrame:
    """Compatibility for tests/archived snapshots created before scanner vNext."""
    x = stocks.copy()
    if "trend_stage" not in x.columns:
        legacy = _col(x, "reaction_state", "UNKNOWN").fillna("UNKNOWN").astype(str)
        x["trend_stage"] = legacy.map({
            "BROKEN": "BROKEN",
            "PRE_CONFIRMATION": "EARLY",
            "CONFIRMING": "CONFIRMED",
            "PERSISTENT": "PERSISTENT",
            "PULLBACK": "PULLBACK",
            "EXTENDED": "WATCH",
        }).fillna("WATCH")
    if "extension_risk" not in x.columns:
        legacy = _col(x, "reaction_state", "UNKNOWN").fillna("UNKNOWN").astype(str)
        x["extension_risk"] = np.where(legacy.eq("EXTENDED"), "EXTENDED", "NORMAL")
    if "rs_acceleration" not in x.columns:
        rs5 = pd.to_numeric(_col(x, "rs_5d_vs_bench"), errors="coerce")
        rs20 = pd.to_numeric(_col(x, "rs_20d_vs_bench"), errors="coerce")
        x["rs_acceleration"] = rs5 - rs20 / 4.0
    if "taiwan_early_score_v3" not in x.columns:
        x["taiwan_early_score_v3"] = pd.to_numeric(
            _col(x, "taiwan_early_score_v2"), errors="coerce"
        )
    return x


def _eligibility_masks(x: pd.DataFrame, cfg: TaiwanScanConfig) -> tuple[pd.Series, pd.Series, pd.Series]:
    avg_turnover = pd.to_numeric(_col(x, "avg_turnover20_twd", 0), errors="coerce").fillna(0)
    avg_liquid = avg_turnover > cfg.min_turnover20

    # Archived/test rows from before scanner vNext do not have the median field.
    # For backward compatibility only, fall back to their already-known mean.
    # Live scans always populate median_turnover20_twd and therefore use the stricter gate.
    median_raw = pd.to_numeric(_col(x, "median_turnover20_twd", np.nan), errors="coerce")
    median_turnover = median_raw.where(median_raw.notna(), avg_turnover)
    median_liquid = median_turnover >= cfg.min_median_turnover20

    liquid = avg_liquid & median_liquid
    price_ok = pd.to_numeric(_col(x, "price", 0), errors="coerce").fillna(0) >= cfg.min_price
    stage = _col(x, "trend_stage", "WATCH").fillna("WATCH").astype(str)
    admitted = stage.isin(["EARLY", "CONFIRMED", "PULLBACK", "PERSISTENT"])
    return liquid, price_ok, admitted


def select_taiwan_candidates(stocks: pd.DataFrame, cfg: TaiwanScanConfig) -> pd.DataFrame:
    """Select only truly admitted candidates, capped by research capacity.

    Qualification and ranking are deliberately separate. Mature trend stages are
    admitted by their structural definition. EARLY must already have passed the
    stricter reversal gate in add_taiwan_candidate_score. Rejected names disappear.
    If admitted names exceed capacity, EARLY has a ceiling but no reserved quota.
    """
    x = _ensure_selection_columns(stocks)
    liquid, price_ok, admitted = _eligibility_masks(x, cfg)
    x["candidate_eligible"] = liquid & price_ok & admitted
    meaningful = x[x["candidate_eligible"]].copy()
    if meaningful.empty:
        return meaningful

    confirmed_mask = meaningful["trend_stage"].isin(["CONFIRMED", "PULLBACK", "PERSISTENT"])
    meaningful["research_priority_score"] = np.where(
        confirmed_mask,
        pd.to_numeric(_col(meaningful, "taiwan_candidate_score_v1"), errors="coerce").fillna(0.0),
        pd.to_numeric(_col(meaningful, "taiwan_early_score_v3"), errors="coerce").fillna(0.0),
    )
    meaningful["candidate_bucket"] = np.where(confirmed_mask, "CONFIRMED", "EARLY")
    ordered = meaningful.sort_values(
        ["research_priority_score", "candidate_bucket", "ticker"],
        ascending=[False, True, True],
    )

    n = max(0, int(cfg.top_candidates))
    if n == 0:
        return ordered.iloc[0:0].copy()
    if len(ordered) <= n:
        out = ordered.copy()
    else:
        early_max = int(n * float(cfg.early_max_fraction))
        mature_pool = ordered[ordered["candidate_bucket"].eq("CONFIRMED")].head(n)
        early_pool = ordered[ordered["candidate_bucket"].eq("EARLY")].head(early_max)
        out = pd.concat([mature_pool, early_pool], ignore_index=True).sort_values(
            ["research_priority_score", "candidate_bucket", "ticker"],
            ascending=[False, True, True],
        ).head(n)

    out = out.drop_duplicates("ticker", keep="first").reset_index(drop=True)
    out["candidate_rank"] = np.arange(1, len(out) + 1)
    return out


def run_taiwan_scan(cfg: TaiwanScanConfig = TaiwanScanConfig(), cached_universe: str = "output/taiwan_universe.csv"):
    cache = Path(cached_universe)
    try:
        uni = fetch_taiwan_universe()
        uni_source_status = "LIVE_OFFICIAL"
        cache.parent.mkdir(parents=True, exist_ok=True)
        uni.to_csv(cache, index=False)
    except Exception as exc:
        if cache.exists():
            uni = pd.read_csv(cache, dtype={"code": str})
            uni_source_status = f"CACHED_FALLBACK: {type(exc).__name__}"
        else:
            raise RuntimeError(f"Taiwan universe fetch failed and no cache exists: {exc}") from exc

    bench_raw = yf.Ticker(cfg.benchmark).history(period=cfg.lookback, auto_adjust=False)
    if bench_raw is None or bench_raw.empty:
        raise RuntimeError(f"Taiwan benchmark {cfg.benchmark} unavailable")
    from scanner_core import closed_history
    bench_raw = closed_history(bench_raw, cfg.benchmark)
    bench_close = _price_series(bench_raw)

    data = _download_chunked(uni["ticker"].tolist(), cfg.lookback, cfg.batch_size)
    data = {t: closed_history(h, t) for t, h in data.items()}
    rows = []
    for _, meta in uni.iterrows():
        t = str(meta["ticker"])
        hist = data.get(t)
        if hist is None or hist.empty or len(hist.dropna(subset=["Close"])) < cfg.min_obs:
            continue
        f = extract_features(hist, bench_close)
        if not f:
            continue
        _add_turnover_feature(hist, f)
        row = meta.to_dict()
        row.update(f)
        rows.append(row)

    stocks = pd.DataFrame(rows)
    if stocks.empty:
        raise RuntimeError("No Taiwan stock features produced")
    stocks = add_taiwan_candidate_score(stocks)
    stocks = stocks.sort_values("taiwan_candidate_score_v1", ascending=False)
    candidates = select_taiwan_candidates(stocks, cfg)
    breadth_input = stocks.rename(columns={"industry": "theme"}) if "theme" not in stocks.columns else stocks
    breadth = compute_theme_breadth(breadth_input)
    return {
        "histories": data,
        "stocks": stocks,
        "candidates": candidates,
        "breadth": breadth,
        "universe": uni,
        "universe_source_status": uni_source_status,
    }
