from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

TAIPEI = ZoneInfo("Asia/Taipei")
EXPECTED_REPOSITORY = "pa45251/alpha-hunter-v2"
EXPECTED_BRANCH = "main"
EXPECTED_SCHEMA = "2.6"
EXPECTED_SCANNER_PREFIX = "2.6"
REQUIRED_RUN_ID_FILES = (
    "causal_research_queue.csv",
    "structural_matches.csv",
    "causal_graph_audit.csv",
)


@dataclass
class GateCheck:
    name: str
    passed: bool
    detail: str
    severity: str = "HARD"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_dt(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=TAIPEI)
        return d.astimezone(TAIPEI)
    except Exception:
        return None


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def validate_canonical_snapshot(out_dir: str | Path = "output") -> dict[str, Any]:
    out = Path(out_dir)
    manifest_path = out / "manifest.json"
    checks: list[GateCheck] = []

    if not manifest_path.exists():
        return {
            "contract": "ALPHA_HUNTER_V2_6_DETERMINISTIC_GATE",
            "gate_status": "FAIL",
            "failure_code": "MANIFEST_MISSING",
            "checks": [asdict(GateCheck("manifest_exists", False, str(manifest_path)))],
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "contract": "ALPHA_HUNTER_V2_6_DETERMINISTIC_GATE",
            "gate_status": "FAIL",
            "failure_code": "MANIFEST_INVALID_JSON",
            "checks": [asdict(GateCheck("manifest_json", False, repr(exc)))],
        }

    def add(name: str, passed: bool, detail: str, severity: str = "HARD") -> None:
        checks.append(GateCheck(name, bool(passed), detail, severity))

    add("repository_identity", manifest.get("repository") == EXPECTED_REPOSITORY,
        f"expected={EXPECTED_REPOSITORY}; actual={manifest.get('repository')}")
    add("branch_identity", manifest.get("branch") == EXPECTED_BRANCH,
        f"expected={EXPECTED_BRANCH}; actual={manifest.get('branch')}")
    add("schema_version", str(manifest.get("schema_version")) == EXPECTED_SCHEMA,
        f"expected={EXPECTED_SCHEMA}; actual={manifest.get('schema_version')}")
    scanner_version = str(manifest.get("scanner_version", ""))
    add("scanner_version", scanner_version.startswith(EXPECTED_SCANNER_PREFIX),
        f"expected_prefix={EXPECTED_SCANNER_PREFIX}; actual={scanner_version}")
    add("manifest_status", manifest.get("status") == "PASS", f"actual={manifest.get('status')}")

    missing = manifest.get("missing_required_files")
    add("missing_required_files", isinstance(missing, list) and len(missing) == 0, f"actual={missing}")

    pipeline = manifest.get("pipeline_checks")
    pipeline_ok = isinstance(pipeline, dict) and bool(pipeline) and all(v is True for v in pipeline.values())
    add("pipeline_checks", pipeline_ok, json.dumps(pipeline, ensure_ascii=False, sort_keys=True))

    run_id = str(manifest.get("run_id", "")).strip()
    add("manifest_run_id", bool(run_id), f"run_id={run_id or '<missing>'}")

    canonical_url = manifest.get("canonical_manifest_raw_url")
    expected_url = f"https://raw.githubusercontent.com/{EXPECTED_REPOSITORY}/{EXPECTED_BRANCH}/output/manifest.json"
    add("canonical_manifest_url", canonical_url == expected_url, f"expected={expected_url}; actual={canonical_url}")

    generated = _parse_dt(manifest.get("generated_at_taipei"))
    if generated is None:
        add("generation_freshness", False, "generated_at_taipei is invalid")
    else:
        age_h = (datetime.now(TAIPEI) - generated).total_seconds() / 3600.0
        # This checks that the pipeline itself ran recently. Market holidays are handled separately
        # through benchmark/reference dates and therefore do not cause a false stale failure here.
        add("generation_freshness", -0.25 <= age_h <= 96.0, f"age_hours={age_h:.2f}; max=96")

    # Verify every manifest-declared authoritative file exists and matches its cryptographic digest.
    declared = manifest.get("authoritative_files") or []
    declared_names: set[str] = set()
    hashes_ok = True
    hash_details: list[str] = []
    for item in declared:
        name = str(item.get("name", ""))
        declared_names.add(name)
        p = out / name
        expected_hash = str(item.get("sha256", ""))
        if not p.exists():
            hashes_ok = False
            hash_details.append(f"{name}:MISSING")
            continue
        actual_hash = _sha256(p)
        if not expected_hash or actual_hash != expected_hash:
            hashes_ok = False
            hash_details.append(f"{name}:HASH_MISMATCH")
    add("authoritative_file_hashes", hashes_ok and bool(declared),
        "; ".join(hash_details) if hash_details else f"verified={len(declared)}")

    # Run consistency: no mixed snapshots are allowed.
    run_consistency_ok = bool(run_id)
    run_details: list[str] = []
    for name in REQUIRED_RUN_ID_FILES:
        p = out / name
        if not p.exists():
            run_consistency_ok = False
            run_details.append(f"{name}:MISSING")
            continue
        try:
            d = pd.read_csv(p, usecols=["run_id"])
            values = set(d["run_id"].dropna().astype(str).unique())
            if values != {run_id}:
                run_consistency_ok = False
                run_details.append(f"{name}:{sorted(values)}")
        except Exception as exc:
            run_consistency_ok = False
            run_details.append(f"{name}:{type(exc).__name__}")
    add("run_consistency", run_consistency_ok,
        "; ".join(run_details) if run_details else f"all={run_id}")

    # Cross-file causal integrity.
    taxonomy = _read_csv(out / "causal_driver_taxonomy.csv")
    graph = _read_csv(out / "structural_exposure_graph.csv", dtype={"taiwan_code": str})
    queue = _read_csv(out / "causal_research_queue.csv")
    matches = _read_csv(out / "structural_matches.csv", dtype={"taiwan_code": str})
    audit = _read_csv(out / "causal_graph_audit.csv", dtype={"taiwan_code": str})
    candidates = _read_csv(out / "taiwan_candidates.csv", dtype={"code": str})

    taxonomy_ids = set(taxonomy.get("driver_id", pd.Series(dtype=str)).dropna().astype(str))
    graph_ids = set(graph.get("driver_id", pd.Series(dtype=str)).dropna().astype(str))
    queue_ids = set(queue.get("driver_id", pd.Series(dtype=str)).dropna().astype(str))
    match_ids = set(matches.get("driver_id", pd.Series(dtype=str)).dropna().astype(str))
    causal_ids_ok = bool(taxonomy_ids) and graph_ids.issubset(taxonomy_ids) and queue_ids.issubset(taxonomy_ids) and match_ids.issubset(taxonomy_ids)
    add("causal_driver_id_integrity", causal_ids_ok,
        f"taxonomy={len(taxonomy_ids)} graph_unknown={sorted(graph_ids-taxonomy_ids)[:5]} queue_unknown={sorted(queue_ids-taxonomy_ids)[:5]} match_unknown={sorted(match_ids-taxonomy_ids)[:5]}")

    audit_ok = (not graph.empty) and len(audit) == len(graph)
    add("graph_audit_completeness", audit_ok, f"graph_rows={len(graph)} audit_rows={len(audit)}")

    queue_state_ok = (not queue.empty) and "activation_state" in queue.columns and queue["activation_state"].astype(str).eq("UNRESOLVED_RESEARCH_REQUIRED").all()
    add("price_does_not_activate_queue", queue_state_ok,
        "all queue rows unresolved" if queue_state_ok else "queue contains non-unresolved activation state")

    decision_ok = True
    if "decision_eligible" in matches.columns and not matches.empty:
        decision_ok = not matches["decision_eligible"].fillna(False).astype(bool).any()
    add("scanner_cannot_make_trade_decision", decision_ok, "decision_eligible must never be true in scanner output")

    candidate_unique = (not candidates.empty) and "ticker" in candidates.columns and not candidates["ticker"].astype(str).duplicated().any()
    add("candidate_uniqueness", candidate_unique, f"rows={len(candidates)}")

    # Market-source freshness: generous holiday-safe bounds, strict enough to catch months-old data.
    now_date = datetime.now(TAIPEI).date()
    for section, max_days in (("global", 10), ("taiwan", 16)):
        latest = (manifest.get(section) or {}).get("latest_price_date")
        try:
            age_days = (now_date - pd.Timestamp(latest).date()).days
            ok = -1 <= age_days <= max_days
            add(f"{section}_market_date_freshness", ok, f"latest={latest}; age_days={age_days}; max={max_days}")
        except Exception:
            add(f"{section}_market_date_freshness", False, f"invalid latest_price_date={latest}")

    hard_failures = [c for c in checks if c.severity == "HARD" and not c.passed]
    status = "PASS" if not hard_failures else "FAIL"
    failure_code = None
    if hard_failures:
        names = {c.name for c in hard_failures}
        if "run_consistency" in names:
            failure_code = "MIXED_SNAPSHOT_DATA"
        elif "authoritative_file_hashes" in names:
            failure_code = "HASH_OR_FILE_INTEGRITY_FAILED"
        elif any("freshness" in n for n in names):
            failure_code = "DATA_QUALITY_WARNING"
        else:
            failure_code = "DATA_ACCESS_FAILED"

    return {
        "contract": "ALPHA_HUNTER_V2_6_DETERMINISTIC_GATE",
        "gate_version": "1.0",
        "gate_status": status,
        "failure_code": failure_code,
        "validated_at_taipei": datetime.now(TAIPEI).isoformat(),
        "repository": manifest.get("repository"),
        "branch": manifest.get("branch"),
        "schema_version": manifest.get("schema_version"),
        "scanner_version": manifest.get("scanner_version"),
        "run_id": run_id,
        "manifest_sha256": _sha256(manifest_path),
        "checks": [asdict(c) for c in checks],
        "hard_failure_count": len(hard_failures),
    }


def build_research_packet(out_dir: str | Path, gate_report: dict[str, Any]) -> dict[str, Any]:
    if gate_report.get("gate_status") != "PASS":
        raise RuntimeError(f"Research packet forbidden: gate={gate_report.get('gate_status')} code={gate_report.get('failure_code')}")
    out = Path(out_dir)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    queue = pd.read_csv(out / "causal_research_queue.csv")
    matches = pd.read_csv(out / "structural_matches.csv", dtype={"taiwan_code": str})
    audit = pd.read_csv(out / "causal_graph_audit.csv", dtype={"taiwan_code": str})

    # Keep the packet bounded. It is a research handoff, not a duplicate data warehouse.
    q = queue.sort_values("research_priority", ascending=False).head(30) if "research_priority" in queue.columns else queue.head(30)
    m = matches.sort_values("research_priority_score", ascending=False).head(120) if "research_priority_score" in matches.columns else matches.head(120)
    weak = audit.copy()
    if "missing_provenance" in weak.columns:
        weak = weak[weak["missing_provenance"].fillna(False).astype(bool)]
    weak = weak.head(120)

    files = {x["name"]: {"raw_url": x["raw_url"], "sha256": x["sha256"]} for x in manifest.get("authoritative_files", [])}
    return {
        "contract": "ALPHA_HUNTER_V2_6_RESEARCH_PACKET",
        "research_packet_version": "1.0",
        "gate_status": "PASS",
        "run_id": manifest["run_id"],
        "schema_version": manifest["schema_version"],
        "scanner_version": manifest["scanner_version"],
        "generated_at_taipei": manifest["generated_at_taipei"],
        "canonical_manifest_raw_url": manifest["canonical_manifest_raw_url"],
        "manifest_sha256": gate_report["manifest_sha256"],
        "causal_rule": "PRICE_CANNOT_CREATE_CAUSALITY",
        "layer_contract": {
            "scanner": "WHAT_MOVED",
            "research": "WHY_AND_WHICH_EXACT_DRIVER",
            "structural_graph": "WHO_HAS_ECONOMIC_EXPOSURE_IF_DRIVER_ACTIVE",
            "taiwan_sensor": "PRICE_REACTION_STATE_ONLY",
            "downstream_decision": "ETF_STOCK_CASH_ENTRY_RISK_EXIT",
        },
        "authoritative_sources": files,
        "research_queue_top30": json.loads(q.to_json(orient="records", date_format="iso")),
        "structural_matches_top120": json.loads(m.to_json(orient="records", date_format="iso")),
        "weak_provenance_edges_top120": json.loads(weak.to_json(orient="records", date_format="iso")),
        "research_instructions": {
            "driver_states": ["ACTIVE", "INACTIVE", "UNKNOWN"],
            "active_requires": "time-consistent external evidence for the exact driver; distinguish industry-wide from company-specific; search counter-evidence",
            "unknown_rule": "insufficient or conflicting evidence => UNKNOWN",
            "hidden_dragon_rule": "ACTIVE exact driver + plausible edge + PRE_CONFIRMATION/early CONFIRMING/controlled PULLBACK + not fully priced + counter-evidence considered",
            "prohibited": ["price-created causality", "buy/sell", "position size", "price target", "stop", "portfolio weight"],
        },
    }


def run_gate(out_dir: str | Path = "output") -> dict[str, Any]:
    out = Path(out_dir)
    report = validate_canonical_snapshot(out)
    (out / "gate_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report.get("gate_status") != "PASS":
        packet = out / "research_packet.json"
        if packet.exists():
            packet.unlink()
        return report
    packet = build_research_packet(out, report)
    (out / "research_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run_gate("output")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("gate_status") != "PASS":
        raise SystemExit(2)
