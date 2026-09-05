from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
import uuid
from pathlib import Path

import pandas as pd

from causal_engine import (
    CausalConfig,
    apply_driver_activation,
    build_causal_research_queue,
    build_structural_matches,
    graph_audit,
    validate_driver_activation_file,
)
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


def append_taiwan_candidate_history(candidates: pd.DataFrame, path: str = "output/taiwan_candidate_history.csv") -> None:
    x = candidates.copy()
    x["snapshot_date_taipei"] = datetime.now(TAIPEI_TZ).date().isoformat()
    keep = [
        "snapshot_date_taipei", "last_price_date", "candidate_rank", "candidate_bucket", "reaction_state",
        "code", "ticker", "name", "exchange", "industry", "price", "ret_5d", "ret_20d", "ret_60d",
        "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration", "er20", "vol20", "maxdd20",
        "keynes_legacy", "keynes_v2", "bias20", "avg_turnover20_twd", "taiwan_candidate_score_v1",
        "taiwan_early_score_v2",
    ]
    x = x[[c for c in keep if c in x.columns]]
    p = Path(path)
    if p.exists():
        try:
            old = pd.read_csv(p, dtype={"code": str})
            x = pd.concat([old, x], ignore_index=True)
        except Exception:
            pass
    x = x.drop_duplicates(["snapshot_date_taipei", "ticker"], keep="last")
    x.to_csv(p, index=False)


def write_taiwan_outputs(tw: dict) -> None:
    tw["candidates"].to_csv(OUT / "taiwan_candidates.csv", index=False)
    tw["breadth"].to_csv(OUT / "taiwan_industry_breadth.csv", index=False)
    tw["universe"].to_csv(OUT / "taiwan_universe.csv", index=False)


def _copy_causal_configs_to_output() -> None:
    for src_name, out_name in [
        ("config/causal_driver_taxonomy.csv", "causal_driver_taxonomy.csv"),
        ("config/structural_exposure_graph.csv", "structural_exposure_graph.csv"),
    ]:
        p = Path(src_name)
        if p.exists():
            pd.read_csv(p, dtype={"taiwan_code": str}).to_csv(OUT / out_name, index=False)


def build_manifest(
    global_results: dict,
    tw: dict,
    research_queue: pd.DataFrame,
    structural_matches: pd.DataFrame,
    graph_audit_df: pd.DataFrame,
    activations: pd.DataFrame,
    run_id: str,
    pipeline_checks: dict,
) -> None:
    repo = os.getenv("GITHUB_REPOSITORY", "pa45251/alpha-hunter-v2")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    required = [
        "market_snapshot.csv", "theme_breadth.csv", "leader_registry.csv", "feature_history.csv",
        "market_snapshot.json", "taiwan_candidates.csv", "taiwan_candidate_history.csv",
        "taiwan_industry_breadth.csv", "taiwan_universe.csv", "causal_research_queue.csv",
        "structural_matches.csv", "causal_graph_audit.csv", "causal_driver_taxonomy.csv",
        "structural_exposure_graph.csv",
    ]
    files, missing = [], []
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
    coverage = len(t) / max(1, len(tw["universe"]))
    checks_pass = all(bool(v) for v in pipeline_checks.values())
    status = "PASS" if not missing and len(g) >= 90 and coverage >= 0.97 and checks_pass else "WARNING"

    active_count = 0
    if not structural_matches.empty and "dynamic_driver_state" in structural_matches.columns:
        active_count = int(structural_matches["dynamic_driver_state"].eq("ACTIVE_RESEARCH_VALIDATED").sum())

    manifest = {
        "contract": "ALPHA_HUNTER_CANONICAL_DATA_CONTRACT",
        "schema_version": "2.5",
        "scanner_version": "2.5.1",
        "run_id": run_id,
        "repository": repo,
        "branch": branch,
        "canonical_output_directory": f"https://github.com/{repo}/tree/{branch}/output",
        "canonical_manifest_raw_url": f"https://raw.githubusercontent.com/{repo}/{branch}/output/manifest.json",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_taipei": datetime.now(TAIPEI_TZ).isoformat(),
        "status": status,
        "missing_required_files": missing,
        "pipeline_checks": pipeline_checks,
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
            "coverage_pct": float(coverage),
            "candidate_count": int(len(tw["candidates"])),
            "industry_count": int(t["industry"].nunique()),
            "latest_price_date": str(t["last_price_date"].max()),
            "earliest_price_date": str(t["last_price_date"].min()),
            "benchmark": "^TWII",
        },
        "causal_engine": {
            "engine": "DYNAMIC_CAUSAL_TRANSMISSION_V1",
            "research_queue_count": int(len(research_queue)),
            "structural_match_count": int(len(structural_matches)),
            "driver_activation_input_present": bool(not activations.empty),
            "active_research_validated_matches": active_count,
            "price_can_create_causality": False,
            "broad_industry_causal_fallback": False,
            "decision_eligible_by_scanner": False,
            "rule": (
                "Price nominates research; it cannot activate a causal driver or create a structural edge. "
                "Structural exposure and dynamic driver activation are separate. Final investment decisions remain downstream."
            ),
        },
        "known_model_risks": [
            "Dynamic driver research can hallucinate or become stale; activation requires explicit evidence and timestamping.",
            "Structural exposure graph can drift as customer/product mixes change; edges have review/provenance fields.",
            "Price-derived global strength, Taiwan reaction and breadth are correlated; v2.5 does not combine them into a trade score.",
            "Candidate funnels can create confirmation bias; structural matches are built from the full Taiwan scan, not only top candidates.",
            "A company may have multiple simultaneous drivers or offsets; v2.5 preserves driver-level rows and polarity.",
        ],
        "authoritative_files": files,
        "hard_gate": {
            "instruction": (
                "Research agents must read the exact canonical_manifest_raw_url first. If status is not PASS, repository/branch/schema identity mismatches, "
                "pipeline_checks are not all true, required files are missing, or freshness fails: DATA ACCESS FAILED / DATA QUALITY WARNING and STOP decision inference."
            ),
            "causal_rule": (
                "Do not infer an active driver from price alone. causal_research_queue.csv contains unresolved research tasks. "
                "structural_matches.csv is not a buy list and is not causally activated unless external research validates the driver."
            ),
            "do_not_substitute": "Do not substitute similarly named repositories, Streamlit tables, search snippets, or external prices for scanner outputs.",
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run_id = f"{datetime.now(TAIPEI_TZ).strftime('%Y%m%dT%H%M%S%z')}-{uuid.uuid4().hex[:8]}"

    # 1) Global market-structure sensor
    gcfg = ScanConfig(lookback="2y", min_obs=140, benchmark="SPY", output_dir="output")
    global_results = run_scan("config/universe.csv", gcfg)
    write_outputs(global_results, gcfg.output_dir)
    append_audit_log(global_results, "output/feature_history.csv")

    # 2) Taiwan full-market sensor
    tcfg = TaiwanScanConfig(
        lookback="1y", min_obs=140, benchmark="^TWII", batch_size=80,
        top_candidates=150, output_dir="output",
    )
    tw = run_taiwan_scan(tcfg, "output/taiwan_universe.csv")
    write_taiwan_outputs(tw)
    append_taiwan_candidate_history(tw["candidates"], "output/taiwan_candidate_history.csv")

    # 3) Causal architecture: broad price themes nominate research, but cannot select the driver.
    taxonomy = pd.read_csv("config/causal_driver_taxonomy.csv")
    exposures = pd.read_csv("config/structural_exposure_graph.csv", dtype={"taiwan_code": str})
    ccfg = CausalConfig()

    research_queue = build_causal_research_queue(global_results["stocks"], taxonomy, ccfg)
    research_queue.insert(0, "run_id", run_id)
    research_queue.to_csv(OUT / "causal_research_queue.csv", index=False)

    # Structural matching uses the full Taiwan scan, preventing top-candidate confirmation bias.
    structural = build_structural_matches(
        global_results["stocks"], tw["stocks"], tw["candidates"], tw["breadth"], exposures, taxonomy, ccfg
    )

    # Optional future bridge: a Research Agent may write driver activations, but only canonical driver_ids are accepted.
    activations = validate_driver_activation_file(Path("input/driver_activation.csv"), research_queue, ccfg)
    structural = apply_driver_activation(structural, activations)
    structural.insert(0, "run_id", run_id)
    structural.to_csv(OUT / "structural_matches.csv", index=False)

    ga = graph_audit(exposures)
    ga.insert(0, "run_id", run_id)
    ga.to_csv(OUT / "causal_graph_audit.csv", index=False)
    _copy_causal_configs_to_output()

    # Integration contract checks: prove the causal files were rebuilt in THIS run, not merely left over from an older snapshot.
    pipeline_checks = {
        "global_outputs_generated": (OUT / "market_snapshot.csv").exists() and len(global_results["stocks"]) > 0,
        "taiwan_outputs_generated": (OUT / "taiwan_candidates.csv").exists() and len(tw["stocks"]) > 0,
        "causal_queue_rebuilt_this_run": (not research_queue.empty) and research_queue["run_id"].eq(run_id).all(),
        "structural_matches_rebuilt_this_run": (not structural.empty) and structural["run_id"].eq(run_id).all(),
        "graph_audit_rebuilt_this_run": (not ga.empty) and ga["run_id"].eq(run_id).all(),
        "causal_taxonomy_snapshot_present": (OUT / "causal_driver_taxonomy.csv").exists(),
        "structural_graph_snapshot_present": (OUT / "structural_exposure_graph.csv").exists(),
    }

    build_manifest(global_results, tw, research_queue, structural, ga, activations, run_id, pipeline_checks)

    print(f"Global: {len(global_results['stocks'])} securities / {global_results['stocks']['theme'].nunique()} themes")
    print(f"Taiwan: {len(tw['stocks'])}/{len(tw['universe'])} common stocks / {tw['stocks']['industry'].nunique()} industries")
    print(f"Taiwan candidates: {len(tw['candidates'])}")
    print(f"Causal research queue: {len(research_queue)} unresolved driver tasks")
    print(f"Structural matches: {len(structural)}; activated by external research: {int(structural.get('dynamic_driver_state', pd.Series(dtype=str)).eq('ACTIVE_RESEARCH_VALIDATED').sum()) if not structural.empty else 0}")
    print(f"Taiwan universe source: {tw['universe_source_status']}")
