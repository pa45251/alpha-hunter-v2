from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path("output")
INDUSTRY_MAP = Path("config/manual_industry_map.csv")
INDUSTRY_MAP_SUPPLEMENT = Path("config/manual_industry_map_supplement.csv")
INDUSTRY_MAP_CORRECTIONS = Path("config/manual_industry_map_corrections.csv")
PEER_MAP = Path("config/manual_global_peers.csv")
PEER_MAP_SUPPLEMENT = Path("config/manual_global_peers_supplement.csv")
PEER_MAP_CORRECTIONS = Path("config/manual_global_peers_corrections.csv")
PEER_EXCLUSIONS = Path("config/manual_global_peer_exclusions.csv")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_code(value) -> str:
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(4)


def load_industry_map() -> pd.DataFrame:
    """Load curated base mappings plus researched supplements and audited corrections.

    Later layers override earlier rows for the same Taiwan company code. This preserves
    a stable curated base while allowing researched scan-specific coverage and small
    post-audit corrections without rewriting the whole ontology.
    """
    frames = [pd.read_csv(INDUSTRY_MAP, dtype={"code": str})]
    for path in (INDUSTRY_MAP_SUPPLEMENT, INDUSTRY_MAP_CORRECTIONS):
        if path.exists():
            frames.append(pd.read_csv(path, dtype={"code": str}))
    out = pd.concat(frames, ignore_index=True)
    out["code"] = out["code"].map(_norm_code)
    out["secondary_driver_ids"] = out["secondary_driver_ids"].fillna("")
    return out.drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)


def load_peer_map() -> pd.DataFrame:
    """Load peer baskets, apply audited corrections, and remove known stale symbols."""
    frames = [pd.read_csv(PEER_MAP)]
    for path in (PEER_MAP_SUPPLEMENT, PEER_MAP_CORRECTIONS):
        if path.exists():
            frames.append(pd.read_csv(path))
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["driver_id", "ticker"], keep="last").reset_index(drop=True)
    if PEER_EXCLUSIONS.exists():
        exclusions = pd.read_csv(PEER_EXCLUSIONS)
        excluded = set(exclusions["ticker"].dropna().astype(str))
        out = out[~out["ticker"].astype(str).isin(excluded)].reset_index(drop=True)
    return out


def _ret(close: pd.Series, periods: int) -> float:
    x = pd.to_numeric(close, errors="coerce").dropna()
    if len(x) <= periods:
        return np.nan
    return float(x.iloc[-1] / x.iloc[-periods - 1] - 1.0)


def _extract_close(raw: pd.DataFrame, ticker: str, multi: bool) -> pd.Series:
    try:
        if multi:
            frame = raw[ticker]
        else:
            frame = raw
        if "Close" not in frame:
            return pd.Series(dtype=float)
        return pd.to_numeric(frame["Close"], errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)


def build_peer_snapshot(peer_map: pd.DataFrame) -> pd.DataFrame:
    """Download a small, explicit peer universe and compute transparent price context.

    This is deliberately deterministic market-data processing. It does not call Copilot,
    OpenAI, Gemini, or any other paid model/API. The result is research context, not a
    recommendation or causal proof.
    """
    peers = peer_map.copy()
    tickers = sorted(set(peers["ticker"].dropna().astype(str)))
    benchmarks = sorted(set(peers["benchmark"].dropna().astype(str)))
    symbols = list(dict.fromkeys(tickers + benchmarks))
    if not symbols:
        return pd.DataFrame()

    try:
        raw = yf.download(
            symbols,
            period="9mo",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as exc:
        print(f"Warning: manual peer download failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    multi = len(symbols) > 1
    close_cache: Dict[str, pd.Series] = {
        symbol: _extract_close(raw, symbol, multi) for symbol in symbols
    }

    rows = []
    for r in peers.itertuples(index=False):
        ticker = str(r.ticker)
        benchmark = str(r.benchmark)
        close = close_cache.get(ticker, pd.Series(dtype=float))
        bench = close_cache.get(benchmark, pd.Series(dtype=float))
        if close.empty:
            continue
        price = float(close.iloc[-1])
        ma20 = float(close.tail(20).mean()) if len(close) >= 20 else np.nan
        ma60 = float(close.tail(60).mean()) if len(close) >= 60 else np.nan
        ret5 = _ret(close, 5)
        ret20 = _ret(close, 20)
        ret60 = _ret(close, 60)
        bench20 = _ret(bench, 20) if not bench.empty else np.nan
        rs20 = ret20 - bench20 if np.isfinite(ret20) and np.isfinite(bench20) else np.nan
        if np.isfinite(ma20) and np.isfinite(ma60) and price > ma20 > ma60:
            trend = "UP"
        elif np.isfinite(ma20) and np.isfinite(ma60) and price < ma20 < ma60:
            trend = "DOWN"
        else:
            trend = "MIXED"
        rows.append({
            "driver_id": r.driver_id,
            "driver_label": r.driver_label,
            "global_theme": r.global_theme,
            "ticker": ticker,
            "name": r.name,
            "region": r.region,
            "benchmark": benchmark,
            "peer_role": r.peer_role,
            "price": price,
            "ret_5d": ret5,
            "ret_20d": ret20,
            "ret_60d": ret60,
            "ma20": ma20,
            "ma60": ma60,
            "above_ma20": bool(np.isfinite(ma20) and price > ma20),
            "above_ma60": bool(np.isfinite(ma60) and price > ma60),
            "rs_20d_vs_local_benchmark": rs20,
            "trend": trend,
        })
    return pd.DataFrame(rows)


def build_driver_breadth(peer_snapshot: pd.DataFrame, peer_map: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for driver_id, configured in peer_map.groupby("driver_id", dropna=False):
        live = peer_snapshot[peer_snapshot["driver_id"].astype(str) == str(driver_id)].copy() if not peer_snapshot.empty else pd.DataFrame()
        peer_names = "; ".join(f"{r.ticker} {r.name}" for r in configured.itertuples(index=False))
        if live.empty:
            rows.append({
                "driver_id": driver_id,
                "driver_label": configured.iloc[0]["driver_label"],
                "global_theme": configured.iloc[0]["global_theme"],
                "configured_peer_count": int(len(configured)),
                "live_peer_count": 0,
                "peer_tickers": ";".join(configured["ticker"].astype(str)),
                "peer_names": peer_names,
                "above_ma20_pct": np.nan,
                "above_ma60_pct": np.nan,
                "positive_rs20_pct": np.nan,
                "median_ret20": np.nan,
                "median_rs20": np.nan,
                "peer_signal": "DATA_UNAVAILABLE",
            })
            continue
        above20 = float(live["above_ma20"].mean())
        above60 = float(live["above_ma60"].mean())
        rs = pd.to_numeric(live["rs_20d_vs_local_benchmark"], errors="coerce")
        positive_rs = float((rs.dropna() > 0).mean()) if rs.notna().any() else np.nan
        median_ret20 = float(pd.to_numeric(live["ret_20d"], errors="coerce").median())
        median_rs20 = float(rs.median()) if rs.notna().any() else np.nan
        # Missing relative-strength data must never be interpreted as either support
        # or weakness. A peer basket is only directional when every live peer has
        # both a usable 20D return and a usable benchmark-relative return.
        rs_complete = bool(rs.notna().all() and pd.to_numeric(live["ret_20d"], errors="coerce").notna().all())
        if not rs_complete:
            signal = "DATA_UNAVAILABLE"
        elif above20 >= 2 / 3 and positive_rs >= 0.5:
            signal = "BROADLY_POSITIVE"
        elif above20 <= 1 / 3 and positive_rs <= 0.5:
            signal = "BROADLY_WEAK"
        else:
            signal = "MIXED"
        rows.append({
            "driver_id": driver_id,
            "driver_label": configured.iloc[0]["driver_label"],
            "global_theme": configured.iloc[0]["global_theme"],
            "configured_peer_count": int(len(configured)),
            "live_peer_count": int(len(live)),
            "peer_tickers": ";".join(configured["ticker"].astype(str)),
            "peer_names": peer_names,
            "above_ma20_pct": above20,
            "above_ma60_pct": above60,
            "positive_rs20_pct": positive_rs,
            "median_ret20": median_ret20,
            "median_rs20": median_rs20,
            "peer_signal": signal,
        })
    return pd.DataFrame(rows)


def build_manual_queue(candidates: pd.DataFrame, industry_map: pd.DataFrame, driver_breadth: pd.DataFrame) -> pd.DataFrame:
    x = candidates.copy()
    x["code"] = x["code"].map(_norm_code)
    m = industry_map.copy()
    m["code"] = m["code"].map(_norm_code)
    keep = [
        "code", "economic_subindustry", "primary_driver_id", "secondary_driver_ids",
        "classification_confidence", "notes",
    ]
    x = x.merge(m[keep], on="code", how="left")
    x["economic_subindustry"] = x["economic_subindustry"].fillna("UNMAPPED")
    x["primary_driver_id"] = x["primary_driver_id"].fillna("UNMAPPED")
    x["secondary_driver_ids"] = x["secondary_driver_ids"].fillna("")
    x["classification_confidence"] = x["classification_confidence"].fillna("UNMAPPED")
    x["manual_deep_research_required"] = True

    if not driver_breadth.empty:
        bcols = [
            "driver_id", "driver_label", "global_theme", "configured_peer_count", "live_peer_count",
            "peer_tickers", "peer_names", "above_ma20_pct", "above_ma60_pct",
            "positive_rs20_pct", "median_ret20", "median_rs20", "peer_signal",
        ]
        x = x.merge(
            driver_breadth[bcols],
            left_on="primary_driver_id",
            right_on="driver_id",
            how="left",
        ).drop(columns=["driver_id"], errors="ignore")

    preferred = [
        "candidate_rank", "candidate_bucket", "reaction_state", "code", "ticker", "name", "industry",
        "economic_subindustry", "primary_driver_id", "secondary_driver_ids", "classification_confidence",
        "driver_label", "global_theme", "peer_tickers", "peer_names", "peer_signal",
        "configured_peer_count", "live_peer_count", "above_ma20_pct", "above_ma60_pct",
        "positive_rs20_pct", "median_ret20", "median_rs20", "price", "ret_5d", "ret_20d", "ret_60d",
        "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration", "keynes_v2", "bias20",
        "avg_turnover20_twd", "manual_deep_research_required", "notes",
    ]
    cols = [c for c in preferred if c in x.columns] + [c for c in x.columns if c not in preferred]
    x = x[cols]
    if "candidate_rank" in x.columns:
        x = x.sort_values("candidate_rank")
    return x


def write_handoff_summary(
    queue: pd.DataFrame,
    path: Path,
    *,
    run_id: str,
    source_candidates_sha256: str,
    mapping_inputs: list[Path],
    peer_inputs: list[Path],
) -> None:
    mapped = int(queue["primary_driver_id"].ne("UNMAPPED").sum()) if not queue.empty else 0
    payload = {
        "contract": "ALPHA_HUNTER_MANUAL_RESEARCH_HANDOFF_V1",
        "purpose": "Scanner shortlist plus deterministic international peer context for manual ChatGPT deep research.",
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_taiwan_candidates_sha256": source_candidates_sha256,
        "mapping_input_sha256": {
            str(p): _sha256(p) for p in mapping_inputs if p.exists()
        },
        "peer_input_sha256": {
            str(p): _sha256(p) for p in peer_inputs if p.exists()
        },
        "automated_model_research_enabled": False,
        "automated_trade_selection_enabled": False,
        "candidate_count": int(len(queue)),
        "mapped_candidate_count": mapped,
        "unmapped_candidate_count": int(len(queue) - mapped),
        "instruction": (
            "Use this handoff only to prioritize manual research. Peer price agreement is context, not causality and not a BUY signal. "
            "For every candidate, manually verify industry trend, exact company transmission, counter-evidence, valuation/expectations, and entry risk."
        ),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_manual_research_outputs(out_dir: str | Path, run_id: str) -> dict[str, bool]:
    """Fail closed unless mapping outputs are present and bound to this scanner run."""
    out = Path(out_dir)
    names = (
        "manual_global_peer_snapshot.csv",
        "manual_driver_breadth.csv",
        "manual_research_queue.csv",
        "manual_research_handoff.json",
    )
    checks = {"outputs_exist": all((out / name).exists() for name in names)}
    if not checks["outputs_exist"]:
        return {
            **checks,
            "csv_run_id_bound": False,
            "handoff_run_id_bound": False,
            "candidate_source_hash_matches": False,
            "handoff_counts_match": False,
            "mapping_columns_present": False,
        }

    try:
        csvs = [
            pd.read_csv(out / "manual_global_peer_snapshot.csv"),
            pd.read_csv(out / "manual_driver_breadth.csv"),
            pd.read_csv(out / "manual_research_queue.csv"),
        ]
        handoff = json.loads((out / "manual_research_handoff.json").read_text(encoding="utf-8"))
        candidates_path = out / "taiwan_candidates.csv"
        queue = csvs[2]
        csv_bound = all(
            "run_id" in frame.columns
            and set(frame["run_id"].dropna().astype(str)) in (set(), {str(run_id)})
            for frame in csvs
        )
        checks["csv_run_id_bound"] = csv_bound
        checks["handoff_run_id_bound"] = str(handoff.get("run_id", "")) == str(run_id)
        checks["candidate_source_hash_matches"] = (
            candidates_path.exists()
            and handoff.get("source_taiwan_candidates_sha256") == _sha256(candidates_path)
        )
        mapped = int(queue["primary_driver_id"].ne("UNMAPPED").sum()) if not queue.empty else 0
        checks["handoff_counts_match"] = (
            int(handoff.get("candidate_count", -1)) == len(queue)
            and int(handoff.get("mapped_candidate_count", -1)) == mapped
            and int(handoff.get("unmapped_candidate_count", -1)) == len(queue) - mapped
        )
        checks["mapping_columns_present"] = {
            "code",
            "economic_subindustry",
            "primary_driver_id",
            "classification_confidence",
            "peer_signal",
            "configured_peer_count",
            "live_peer_count",
        }.issubset(queue.columns)
    except (OSError, ValueError, TypeError, KeyError):
        checks.update({
            "csv_run_id_bound": False,
            "handoff_run_id_bound": False,
            "candidate_source_hash_matches": False,
            "handoff_counts_match": False,
            "mapping_columns_present": False,
        })
    return checks



def main(run_id: str | None = None) -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    candidates_path = OUT / "taiwan_candidates.csv"
    if not candidates_path.exists():
        raise SystemExit("output/taiwan_candidates.csv not found; run daily_scan.py first")

    if run_id is None:
        manifest_path = OUT / "manifest.json"
        if manifest_path.exists():
            try:
                run_id = str(json.loads(manifest_path.read_text(encoding="utf-8")).get("run_id") or "")
            except (OSError, ValueError, TypeError):
                run_id = ""
    run_id = str(run_id or "").strip()
    if not run_id:
        raise RuntimeError("manual research handoff requires a canonical scanner run_id")

    candidates = pd.read_csv(candidates_path, dtype={"code": str})
    industry_map = load_industry_map()
    peer_map = load_peer_map()

    peer_snapshot = build_peer_snapshot(peer_map)
    peer_snapshot.insert(0, "run_id", run_id)
    peer_snapshot.to_csv(OUT / "manual_global_peer_snapshot.csv", index=False)
    driver_breadth = build_driver_breadth(peer_snapshot.drop(columns=["run_id"]), peer_map)
    driver_breadth.insert(0, "run_id", run_id)
    driver_breadth.to_csv(OUT / "manual_driver_breadth.csv", index=False)
    queue = build_manual_queue(candidates, industry_map, driver_breadth.drop(columns=["run_id"]))
    queue.insert(0, "run_id", run_id)
    queue.to_csv(OUT / "manual_research_queue.csv", index=False)
    write_handoff_summary(
        queue,
        OUT / "manual_research_handoff.json",
        run_id=run_id,
        source_candidates_sha256=_sha256(candidates_path),
        mapping_inputs=[INDUSTRY_MAP, INDUSTRY_MAP_SUPPLEMENT, INDUSTRY_MAP_CORRECTIONS],
        peer_inputs=[PEER_MAP, PEER_MAP_SUPPLEMENT, PEER_MAP_CORRECTIONS, PEER_EXCLUSIONS],
    )

    print(
        f"manual research queue: {len(queue)} candidates; "
        f"mapped={int(queue['primary_driver_id'].ne('UNMAPPED').sum())}; "
        f"peer_rows={len(peer_snapshot)}"
    )
    return queue


if __name__ == "__main__":
    main()
