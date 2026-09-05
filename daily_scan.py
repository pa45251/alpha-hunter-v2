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


def _tier_weight(tier: str) -> float:
    return {
        "DIRECT": 1.00,
        "STRONG": 0.85,
        "SECOND_ORDER": 0.60,
        "SPECULATIVE": 0.30,
    }.get(str(tier).upper(), 0.0)


def _industry_breadth_support(taiwan_breadth: pd.DataFrame, industry: str) -> float:
    if taiwan_breadth is None or taiwan_breadth.empty:
        return 0.5
    col = "theme" if "theme" in taiwan_breadth.columns else "industry"
    hit = taiwan_breadth[taiwan_breadth[col].astype(str) == str(industry)]
    if hit.empty:
        return 0.5
    r = hit.iloc[0]
    vals = []
    for c in ["above_ma20_pct", "positive_rs20_pct", "near_20d_high_pct"]:
        try:
            vals.append(float(r[c]))
        except Exception:
            pass
    return float(np.mean(vals)) if vals else 0.5


def build_transmission_watchlist(
    global_stocks: pd.DataFrame,
    taiwan_candidates: pd.DataFrame,
    taiwan_breadth: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build v2.4 Economic Linkage Graph hypotheses.

    Unlike v2.3, this function does NOT infer causal transmission from a broad TWSE
    industry label. A Taiwan stock must have an explicit company-level linkage edge
    in config/economic_linkage_graph.csv. Broad industry fallback is disabled.

    Output remains HYPOTHESIS_ONLY and requires Research Layer validation.
    """
    graph_path = Path("config/economic_linkage_graph.csv")
    if not graph_path.exists() or taiwan_candidates.empty:
        return pd.DataFrame(), pd.DataFrame()

    graph = pd.read_csv(graph_path, dtype={"taiwan_code": str})
    graph["taiwan_code"] = graph["taiwan_code"].astype(str).str.zfill(4)
    if "enabled" in graph.columns:
        graph = graph[graph["enabled"].fillna(0).astype(int) == 1].copy()

    # Hard filter: speculative or low-confidence edges are kept in the audit table
    # but are not promoted to the actionable research watchlist.
    graph["tier_weight"] = graph["linkage_tier"].map(_tier_weight)
    graph["linkage_confidence"] = pd.to_numeric(graph["linkage_confidence"], errors="coerce")

    gs = _global_theme_strength(global_stocks)
    if gs.empty:
        return pd.DataFrame(), pd.DataFrame()

    candidates = taiwan_candidates.copy()
    candidates["code"] = candidates["code"].astype(str).str.zfill(4)
    cand_by_code = candidates.set_index("code", drop=False)

    audit_rows = []
    rows = []
    for _, edge in graph.iterrows():
        theme = str(edge["global_theme"])
        g_hit = gs[gs["global_theme"].astype(str) == theme]
        code = str(edge["taiwan_code"]).zfill(4)
        in_candidate = code in cand_by_code.index
        global_strength = float(g_hit.iloc[0]["global_theme_strength_v1"]) if not g_hit.empty else np.nan
        eligible_theme = bool(not g_hit.empty and global_strength >= 0.55)
        tier = str(edge["linkage_tier"]).upper()
        conf = float(edge["linkage_confidence"]) if pd.notna(edge["linkage_confidence"]) else 0.0
        edge_pass = tier != "SPECULATIVE" and conf >= 0.55

        audit_rows.append({
            "global_theme": theme,
            "taiwan_code": code,
            "taiwan_name_seed": edge.get("taiwan_name_seed", ""),
            "economic_role": edge.get("economic_role", ""),
            "linkage_tier": tier,
            "linkage_confidence": conf,
            "global_theme_strength_v1": global_strength,
            "global_theme_eligible": eligible_theme,
            "in_taiwan_candidate_funnel": in_candidate,
            "edge_passes_hard_gate": edge_pass,
            "audit_status": (
                "PROMOTED" if eligible_theme and in_candidate and edge_pass else
                "NO_GLOBAL_CONFIRMATION" if not eligible_theme else
                "NOT_IN_TAIWAN_FUNNEL" if not in_candidate else
                "LINKAGE_TOO_WEAK"
            ),
        })

        if not (eligible_theme and in_candidate and edge_pass):
            continue

        r = cand_by_code.loc[code]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        breadth_support = _industry_breadth_support(taiwan_breadth, r.get("industry", ""))
        tier_weight = _tier_weight(tier)
        linkage_score = conf * tier_weight
        combined = (
            0.35 * global_strength
            + 0.25 * float(r["taiwan_candidate_score_v1"])
            + 0.25 * linkage_score
            + 0.15 * breadth_support
        )
        # Explicit contradiction flag: transmission may still be researched, but
        # negative RS20 materially reduces confidence.
        rs20 = float(r.get("rs_20d_vs_bench", np.nan))
        accel = float(r.get("acceleration", np.nan))
        contradiction = bool((pd.notna(rs20) and rs20 < 0) and (pd.notna(accel) and accel < 0))
        if contradiction:
            combined *= 0.82

        rows.append({
            "global_theme": theme,
            "global_theme_strength_v1": global_strength,
            "taiwan_code": code,
            "taiwan_ticker": r["ticker"],
            "taiwan_name": r["name"],
            "taiwan_industry": r["industry"],
            "economic_role": edge.get("economic_role", ""),
            "linkage_tier": tier,
            "linkage_confidence": conf,
            "linkage_score": linkage_score,
            "link_mechanism": edge.get("link_mechanism", ""),
            "evidence_required": edge.get("evidence_required", ""),
            "taiwan_candidate_score_v1": float(r["taiwan_candidate_score_v1"]),
            "taiwan_rs20": rs20,
            "taiwan_acceleration": accel,
            "taiwan_keynes_v2": float(r.get("keynes_v2", np.nan)),
            "taiwan_industry_breadth_support": breadth_support,
            "contradiction_flag": contradiction,
            "combined_hypothesis_score_v2": combined,
            "status": "HYPOTHESIS_ONLY",
            "research_required": True,
        })

    watch = pd.DataFrame(rows)
    audit = pd.DataFrame(audit_rows)
    if not watch.empty:
        watch = watch.sort_values(["combined_hypothesis_score_v2", "linkage_confidence"], ascending=False).head(120)
    if not audit.empty:
        audit = audit.sort_values(["audit_status", "global_theme", "taiwan_code"])
    return watch, audit



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
    graph = Path("config/economic_linkage_graph.csv")
    if graph.exists():
        pd.read_csv(graph, dtype={"taiwan_code": str}).to_csv(OUT / "economic_linkage_graph.csv", index=False)


def build_manifest(global_results: dict, tw: dict, transmission: pd.DataFrame, linkage_audit: pd.DataFrame) -> None:
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
        "transmission_linkage_audit.csv",
        "economic_linkage_graph.csv",
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
        "schema_version": "2.4",
        "scanner_version": "2.4",
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
            "linkage_graph_edges": int(len(linkage_audit)),
            "promoted_edges": int((linkage_audit["audit_status"] == "PROMOTED").sum()) if not linkage_audit.empty and "audit_status" in linkage_audit else 0,
            "status": "HYPOTHESIS_ONLY",
            "engine": "ECONOMIC_LINKAGE_GRAPH_V2",
            "broad_industry_fallback": False,
            "rule": "Company-level Economic Linkage Graph only. Broad-industry causal inference is disabled. Requires causal/fundamental validation by Research Layer before any decision use.",
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
    transmission, linkage_audit = build_transmission_watchlist(
        global_results["stocks"], tw["candidates"], tw["breadth"]
    )
    transmission.to_csv(OUT / "transmission_watchlist.csv", index=False)
    linkage_audit.to_csv(OUT / "transmission_linkage_audit.csv", index=False)

    # Canonical contract is written last so PASS means all upstream files exist.
    build_manifest(global_results, tw, transmission, linkage_audit)

    print(f"Global: {len(global_results['stocks'])} securities / {global_results['stocks']['theme'].nunique()} themes")
    print(f"Taiwan: {len(tw['stocks'])}/{len(tw['universe'])} common stocks / {tw['stocks']['industry'].nunique()} industries")
    print(f"Taiwan candidates: {len(tw['candidates'])}; transmission hypotheses: {len(transmission)}; linkage audit edges: {len(linkage_audit)}")
    print(f"Taiwan universe source: {tw['universe_source_status']}")
