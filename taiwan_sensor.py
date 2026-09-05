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
    top_candidates: int = 150
    min_price: float = 5.0
    min_turnover20: float = 10_000_000.0
    output_dir: str = "output"


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
        # Strictly ordinary 4-digit common-share codes; excludes ETFs, ETNs,
        # warrants, bonds, preferred-share letter suffixes and most structured products.
        if not re.fullmatch(r"\d{4}", code):
            continue
        industry = str(r.get(industry_col, "未分類")).strip() if industry_col else "未分類"
        cfi = str(r.get(cfi_col, "")).strip().upper() if cfi_col else ""
        # CFI codes beginning with ES denote common/ordinary equity shares.
        # This excludes numeric-code ETFs such as 0050/0056 that would otherwise pass the 4-digit filter.
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
    except Exception:
        f["avg_turnover20_twd"] = np.nan


def add_taiwan_candidate_score(df: pd.DataFrame) -> pd.DataFrame:
    """Transparent, deliberately non-optimized Taiwan discovery score.

    Unlike Global Leader Score, this places more weight on acceleration and trend quality,
    because Taiwan Sensor is looking for improving / not-yet-fully-priced candidates.
    It is a discovery heuristic, NOT a buy signal.
    """
    x = add_cross_section_scores(df)
    x["r_turnover"] = x["avg_turnover20_twd"].rank(pct=True, method="average")
    # Favor reasonable proximity to highs without rewarding extreme extension.
    bias = x["bias20"].astype(float)
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

    # v2.5 separates price confirmation from economic causality. This prevents the
    # candidate funnel from becoming a hidden "must already be strong" gate.
    rs20 = x["rs_20d_vs_bench"].fillna(-999)
    rs60 = x["rs_60d_vs_bench"].fillna(-999)
    accel = x["acceleration"].fillna(-999)
    bias20 = x["bias20"].fillna(0)
    ret5 = x["ret_5d"].fillna(0)
    trend = x["trend"].fillna("UNKNOWN")

    x["reaction_state"] = "UNKNOWN"
    x.loc[(trend == "BEAR") & (rs20 < 0), "reaction_state"] = "BROKEN"
    x.loc[(rs20 <= 0) & (accel > 0) & (trend != "BEAR"), "reaction_state"] = "PRE_CONFIRMATION"
    x.loc[(rs20 > 0) & (accel > 0), "reaction_state"] = "CONFIRMING"
    x.loc[(rs20 > 0) & (rs60 > 0) & (trend == "STRONG_UP"), "reaction_state"] = "PERSISTENT"
    x.loc[(rs20 > 0) & (accel <= 0) & (trend == "PULLBACK"), "reaction_state"] = "PULLBACK"
    x.loc[(bias20 > 0.20) | (ret5 > 0.25), "reaction_state"] = "EXTENDED"

    # A separate early-discovery score favors acceleration/quality without requiring
    # already-positive RS20. It is used only to preserve lead-lag candidates.
    x["taiwan_early_score_v2"] = (
        0.30 * x["r_accel"]
        + 0.25 * x["r_quality"]
        + 0.15 * x["r_slope"]
        + 0.10 * x["r_volume"]
        + 0.10 * x["r_turnover"]
        + 0.10 * x["r_extension"]
    )
    return x


def select_taiwan_candidates(stocks: pd.DataFrame, cfg: TaiwanScanConfig) -> pd.DataFrame:
    """Balanced discovery funnel.

    v2.5 deliberately reserves room for PRE_CONFIRMATION names so the system does
    not only discover stocks after the move is already obvious. EXTENDED names are
    still visible but cannot dominate the entire list.
    """
    x = stocks.copy()
    liquid = x["avg_turnover20_twd"].fillna(0) >= cfg.min_turnover20
    price_ok = x["price"].fillna(0) >= cfg.min_price
    improving = (
        (x["acceleration"].fillna(-999) > 0)
        | (x["rs_20d_vs_bench"].fillna(-999) > 0)
        | (x["keynes_v2"].fillna(-999) > 0)
    )
    x["candidate_eligible"] = liquid & price_ok & improving & x["reaction_state"].ne("BROKEN")
    x = x[x["candidate_eligible"]].copy()

    n = int(cfg.top_candidates)
    n_early = max(20, int(n * 0.30))
    n_extended = max(10, int(n * 0.15))
    n_confirmed = max(1, n - n_early - n_extended)

    confirmed = x[x["reaction_state"].isin(["CONFIRMING", "PERSISTENT", "PULLBACK"])].sort_values(
        "taiwan_candidate_score_v1", ascending=False
    ).head(n_confirmed)
    early = x[x["reaction_state"].isin(["PRE_CONFIRMATION", "UNKNOWN"])].sort_values(
        "taiwan_early_score_v2", ascending=False
    ).head(n_early)
    extended = x[x["reaction_state"].eq("EXTENDED")].sort_values(
        "taiwan_candidate_score_v1", ascending=False
    ).head(n_extended)

    out = pd.concat([confirmed, early, extended], ignore_index=True).drop_duplicates("ticker", keep="first")
    if len(out) < n:
        filler = x[~x["ticker"].isin(out["ticker"])].sort_values("taiwan_candidate_score_v1", ascending=False).head(n-len(out))
        out = pd.concat([out, filler], ignore_index=True)
    out["candidate_bucket"] = out["reaction_state"].map({
        "PRE_CONFIRMATION": "EARLY", "UNKNOWN": "EARLY", "EXTENDED": "EXTENDED",
        "CONFIRMING": "CONFIRMED", "PERSISTENT": "CONFIRMED", "PULLBACK": "CONFIRMED"
    }).fillna("OTHER")
    out = out.sort_values(["candidate_bucket", "taiwan_candidate_score_v1"], ascending=[True, False])
    out["candidate_rank"] = np.arange(1, len(out) + 1)
    return out.head(n)


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
    bench_close = _price_series(bench_raw)

    data = _download_chunked(uni["ticker"].tolist(), cfg.lookback, cfg.batch_size)
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
        "stocks": stocks,
        "candidates": candidates,
        "breadth": breadth,
        "universe": uni,
        "universe_source_status": uni_source_status,
    }
