from __future__ import annotations

import json
import os
from pathlib import Path


RESULT = Path("output/research_result_v3.json")
DEFAULT_TRANSPORT = Path("/tmp/research_prefetch_v3.json")
TRANSPORT_CONTRACT = "ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH"


def _transport_quality(path: Path, run_id: str, target_count: int) -> dict:
    base = {
        "transport_present": False,
        "transport_status": "MISSING",
        "transport_pass": False,
        "query_attempt_count": 0,
        "successful_query_count": 0,
        "candidate_source_count": 0,
        "sourced_target_count": 0,
    }
    if not path.exists():
        return base
    base["transport_present"] = True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        base["transport_status"] = "INVALID_JSON"
        return base

    base["transport_status"] = str(data.get("status", ""))
    if data.get("contract") != TRANSPORT_CONTRACT:
        base["transport_status"] = "CONTRACT_MISMATCH"
        return base
    if str(data.get("research_run_id", "")) != str(run_id):
        base["transport_status"] = "RUN_ID_MISMATCH"
        return base

    try:
        transport_targets = int(data.get("target_count", 0) or 0)
        queries = int(data.get("query_attempt_count", 0) or 0)
        successful = int(data.get("successful_query_count", 0) or 0)
        candidates = int(data.get("candidate_source_count", 0) or 0)
        sourced_targets = int(data.get("sourced_target_count", 0) or 0)
    except Exception:
        base["transport_status"] = "INVALID_COUNTS"
        return base

    base.update(
        {
            "query_attempt_count": queries,
            "successful_query_count": successful,
            "candidate_source_count": candidates,
            "sourced_target_count": sourced_targets,
        }
    )
    base["transport_pass"] = bool(
        base["transport_status"] == "PASS"
        and target_count > 0
        and transport_targets == target_count
        and queries >= 2 * target_count
        and successful > 0
        and candidates > 0
        and sourced_targets > 0
    )
    return base


def evaluate(path: Path = RESULT, transport_path: Path | None = None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results") or []
    total_sources = 0
    sourced_drivers = 0
    active_or_inactive = 0
    for row in results:
        try:
            source_count = int(row.get("source_count", 0) or 0)
        except Exception:
            source_count = 0
        total_sources += max(source_count, 0)
        if source_count > 0:
            sourced_drivers += 1
        if str(row.get("state", "UNKNOWN")).upper() in {"ACTIVE", "INACTIVE"}:
            active_or_inactive += 1

    status = str(data.get("status", ""))
    evidence_pass = total_sources > 0 and sourced_drivers > 0
    run_id = str(data.get("research_run_id", ""))
    if transport_path is None:
        transport_path = Path(os.getenv("ALPHA_HUNTER_RESEARCH_TRANSPORT_PATH", str(DEFAULT_TRANSPORT)))
    transport = _transport_quality(transport_path, run_id, len(results))

    quality_pass = bool(
        status == "PASS"
        and len(results) > 0
        and (evidence_pass or transport["transport_pass"])
    )
    return {
        "status": status,
        "target_count": len(results),
        "total_sources": total_sources,
        "sourced_drivers": sourced_drivers,
        "active_or_inactive": active_or_inactive,
        "evidence_pass": evidence_pass,
        "quality_pass": quality_pass,
        **transport,
    }


def main() -> None:
    q = evaluate()
    print(
        "research quality: "
        f"status={q['status']} targets={q['target_count']} total_sources={q['total_sources']} "
        f"sourced_drivers={q['sourced_drivers']} resolved={q['active_or_inactive']} "
        f"transport={q['transport_status']} searches={q['query_attempt_count']} "
        f"candidate_sources={q['candidate_source_count']} sourced_targets={q['sourced_target_count']}"
    )
    if not q["quality_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
