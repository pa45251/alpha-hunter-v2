from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scanner_core import TAIPEI_TZ, ScanConfig, append_audit_log, run_scan, write_outputs
from taiwan_sensor import TaiwanScanConfig, run_taiwan_scan

OUT = Path("output")
OUT.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _global_theme_strength(global_stocks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for theme, g in global_stocks.groupby("theme"):
        if g.empty:
            continue
        rows.append({
            "global_theme": theme,
            "global_n": len(g),
            "global_median_rs20": float(g["rs_20d_vs_bench"].median()),
            "global_positive_rs20_pct": float((g["rs_20d_vs_bench"] > 0).mean()),
            "global_max_leader_score": float(g["leader_score_v1"].max()),
        })
    x = pd.DataFrame(rows)
    if x.empty:
        return x
    for col in ["global_median_rs20", "global_positive_rs20_pct", "global_max_leader_score"]:
        x[f"r_{col}"] = x[col].rank(pct=True, method="average")
    x["global_theme_strength_v1"] = (
        0.40 * x["r_global_median_rs20"]
        + 0.30 * x["r_global_positive_rs20_pct"]
        + 0.30 * x["r_global_max_leader_score"]
    )
    return x.sort_values("global_theme_strength_v1", ascending=False)


def build_transmission_watchlist(global_stocks: pd.DataFrame, taiwan_candidates: pd.DataFrame) -> pd.DataFrame:
    """Hypothesis generator only; never treated as causal confirmation."""
    map_path = Path("config/transmission_map.csv")
    if not map_path.exists() or taiwan_candidates.empty:
        return pd.DataFrame()
    mapping = pd.read_csv(map_path)
    gs = _global_theme_strength(global_stocks)
    if gs.empty:
        return pd.DataFrame()
    rows = []
    for _, m in mapping.iterrows():
        theme = m["global_theme"]
        hit = gs[gs["global_theme"] == theme]
        if hit.empty:
            continue
        g = hit.iloc[0]
        # Only promote relatively strong global themes into transmission hypotheses.
        if float(g["global_theme_strength_v1"]) < 0.55:
            continue
        pattern = str(m["taiwan_industry_pattern"])
        tw = taiwan_candidates[
            taiwan_candidates["industry"].astype(str).str.contains(pattern, regex=True, na=False)
        ].head(12)
        for _, r in tw.iterrows():
            combined = 0.55 * float(g["global_theme_strength_v1"]) + 0.45 * float(r["taiwan_candidate_score_v1"])
            rows.append({
                "global_theme": theme,
                "global_theme_strength_v1": float(g["global_theme_strength_v1"]),
                "linkage_type": m["linkage_type"],
                "taiwan_code": str(r["code"]),
                "taiwan_ticker": r["ticker"],
                "taiwan_name": r["name"],
                "taiwan_industry": r["industry"],
                "taiwan_candidate_score_v1": float(r["taiwan_candidate_score_v1"]),
                "taiwan_rs20": float(r.get("rs_20d_vs_bench", np.nan)),
                "taiwan_acceleration": float(r.get("acceleration", np.nan)),
                "taiwan_keynes_v2": float(r.get("keynes_v2", np.nan)),
                "combined_hypothesis_score_v1": combined,
                "status": "HYPOTHESIS_ONLY",
                "research_required": True,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("combined_hypothesis_score_v1", ascending=False).head(120)



def append_taiwan_candidate_history(candidates: pd.DataFrame, path: str = "output/taiwan_candidate_history.csv") -> None:
    x = candidates.copy()
    x["snapshot_date_taipei"] = datetime.now(TAIPEI_TZ).date().isoformat()
    keep = [
        "snapshot_date_taipei","last_price_date","candidate_rank","code","ticker","name","exchange","industry",
        "price","ret_5d","ret_20d","ret_60d","rs_20d_vs_bench","rs_60d_vs_bench","acceleration",
        "er20","vol20","maxdd20","keynes_legacy","keynes_v2","avg_turnover20_twd","taiwan_candidate_score_v1"
    ]
    x = x[[c for c in keep if c in x.columns]]
    p = Path(path)
    if p.exists():
        try:
            old = pd.read_csv(p, dtype={"code": str})
            x = pd.concat([old, x], ignore_index=True)
        except Exception:
            pass
    x = x.drop_duplicates(["snapshot_date_taipei","ticker"], keep="last")
    x.to_csv(p, index=False)


def write_taiwan_outputs(tw: dict) -> None:
    tw["candidates"].to_csv(OUT / "taiwan_candidates.csv", index=False)
    tw["breadth"].to_csv(OUT / "taiwan_industry_breadth.csv", index=False)
    tw["universe"].to_csv(OUT / "taiwan_universe.csv", index=False)


def build_manifest(global_results: dict, tw: dict, transmission: pd.DataFrame) -> None:
    repo = os.getenv("GITHUB_REPOSITORY", "pa45251/alpha-hunter-v2")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    required = [
        "market_snapshot.csv",
        "theme_breadth.csv",
        "leader_registry.csv",
        "feature_history.csv",
        "market_snapshot.json",
        "taiwan_candidates.csv",
        "taiwan_candidate_history.csv",
        "taiwan_industry_breadth.csv",
        "taiwan_universe.csv",
        "transmission_watchlist.csv",
    ]
    files = []
    missing = []
    for name in required:
        p = OUT / name
        if p.exists():
            files.append({
                "name": name,
                "relative_path": f"output/{name}",
                "raw_url": f"https://raw.githubusercontent.com/{repo}/{branch}/output/{name}",
                "sha256": _sha256(p),
                "bytes": p.stat().st_size,
            })
        else:
            missing.append(name)

    g = global_results["stocks"]
    t = tw["stocks"]
    status = "PASS" if not missing and len(g) >= 90 and len(t) >= 1000 else "WARNING"
    manifest = {
        "contract": "ALPHA_HUNTER_CANONICAL_DATA_CONTRACT",
        "schema_version": "2.3",
        "scanner_version": "2.3",
        "repository": repo,
        "branch": branch,
        "canonical_output_directory": f"https://github.com/{repo}/tree/{branch}/output",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_taipei": datetime.now(TAIPEI_TZ).isoformat(),
        "status": status,
        "missing_required_files": missing,
        "global": {
            "scanned_count": int(len(g)),
            "theme_count": int(g["theme"].nunique()),
            "latest_price_date": str(g["last_price_date"].max()),
            "earliest_price_date": str(g["last_price_date"].min()),
        },
        "taiwan": {
            "universe_source_status": tw["universe_source_status"],
            "universe_count": int(len(tw["universe"])),
            "scanned_count": int(len(t)),
            "candidate_count": int(len(tw["candidates"])),
            "industry_count": int(t["industry"].nunique()),
            "latest_price_date": str(t["last_price_date"].max()),
            "earliest_price_date": str(t["last_price_date"].min()),
            "benchmark": "^TWII",
        },
        "transmission": {
            "candidate_count": int(len(transmission)),
            "status": "HYPOTHESIS_ONLY",
            "rule": "Requires causal/fundamental validation by Research Layer before any decision use.",
        },
        "authoritative_files": files,
        "hard_gate": {
            "instruction": "Research agents must read manifest.json first. If status is not PASS, identity mismatches, required files are missing, or freshness fails: DATA ACCESS FAILED / DATA QUALITY WARNING and STOP decision inference.",
            "do_not_substitute": "Do not substitute similarly named GitHub repositories, Streamlit tables, search snippets, or external price websites for scanner outputs.",
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    # Global sensor
    gcfg = ScanConfig(lookback="2y", min_obs=140, benchmark="SPY", output_dir="output")
    global_results = run_scan("config/universe.csv", gcfg)
    write_outputs(global_results, gcfg.output_dir)
    append_audit_log(global_results, "output/feature_history.csv")

    # Taiwan full-market sensor
    tcfg = TaiwanScanConfig(
        lookback="1y",
        min_obs=140,
        benchmark="^TWII",
        batch_size=80,
        top_candidates=150,
        output_dir="output",
    )
    tw = run_taiwan_scan(tcfg, "output/taiwan_universe.csv")
    write_taiwan_outputs(tw)
    append_taiwan_candidate_history(tw["candidates"], "output/taiwan_candidate_history.csv")

    # Global -> Taiwan hypothesis layer
    transmission = build_transmission_watchlist(global_results["stocks"], tw["candidates"])
    transmission.to_csv(OUT / "transmission_watchlist.csv", index=False)

    # Canonical contract is written last so PASS means all upstream files exist.
    build_manifest(global_results, tw, transmission)

    print(f"Global: {len(global_results['stocks'])} securities / {global_results['stocks']['theme'].nunique()} themes")
    print(f"Taiwan: {len(tw['stocks'])}/{len(tw['universe'])} common stocks / {tw['stocks']['industry'].nunique()} industries")
    print(f"Taiwan candidates: {len(tw['candidates'])}; transmission hypotheses: {len(transmission)}")
    print(f"Taiwan universe source: {tw['universe_source_status']}")
