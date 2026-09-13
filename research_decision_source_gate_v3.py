from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from causal_engine import CausalConfig, validate_driver_activation_file
from research_quality_gate_v3 import evaluate as evaluate_research_quality


OUT = Path("output")
PARTIAL_STATUS = "PARTIAL_" + "FAIL_CLOSED"


def _challenger_is_valid() -> tuple[bool, int, int, str]:
    path = OUT / "driver_activation_adjudicated_v3.csv"
    manifest_path = OUT / "manifest.json"
    queue_path = OUT / "causal_research_queue.csv"
    if not (path.exists() and manifest_path.exists() and queue_path.exists()):
        return False, 0, 0, "challenger artifact or canonical inputs missing"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", ""))
    raw = pd.read_csv(path)
    if raw.empty:
        return False, 0, 0, "challenger artifact empty"
    if "research_run_id" not in raw.columns or not raw["research_run_id"].astype(str).eq(run_id).all():
        return False, 0, 0, "challenger run_id mismatch"
    if "activation_source" not in raw.columns or not raw["activation_source"].astype(str).eq("CHATGPT_CHALLENGER_ADJUDICATION").all():
        return False, 0, 0, "challenger source identity mismatch"

    queue = pd.read_csv(queue_path)
    validated = validate_driver_activation_file(path, queue, CausalConfig())
    accepted = int(validated.get("activation_valid", pd.Series(dtype=bool)).fillna(False).sum()) if not validated.empty else 0
    source_count = int(pd.to_numeric(raw.get("source_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    return accepted > 0 and source_count > 0, accepted, source_count, "ok"


def main() -> None:
    q = evaluate_research_quality()
    usable = q["status"] in {"PASS", PARTIAL_STATUS}
    if usable and q["evidence_pass"]:
        print(
            "decision-source evidence gate PASS via autonomous research evidence: "
            f"total_sources={q['total_sources']} sourced_drivers={q['sourced_drivers']}"
        )
        return

    if usable and q["transport_pass"]:
        print(
            "decision-source evidence gate PASS via deterministic external-search transport: "
            f"searches={q['query_attempt_count']} candidate_sources={q['candidate_source_count']} "
            f"sourced_targets={q['sourced_target_count']}; autonomous_sources={q['total_sources']}. "
            "This authorizes downstream fail-closed evaluation only; causal activation still requires "
            "source-backed ACTIVE/INACTIVE research rows."
        )
        return

    # A fully executed research lane may legitimately find no admissible driver source at all.
    # That is an investment UNKNOWN, not an execution outage, provided deterministic search ran,
    # every shared-driver result stayed UNKNOWN, and every admitted company thesis reached a
    # terminal non-execution outcome. Downstream may then continue only in fail-closed mode.
    exhaustive_no_evidence = bool(
        usable
        and q.get("company_terminal_accounting_pass")
        and q.get("company_research_complete")
        and q.get("target_count", 0) > 0
        and q.get("active_or_inactive", 0) == 0
        and q.get("total_sources", 0) == 0
        and q.get("transport_present")
        and q.get("transport_status") == "FAIL_CLOSED"
        and q.get("query_attempt_count", 0) >= 2 * q.get("target_count", 0)
        and q.get("successful_query_count", 0) > 0
        and q.get("candidate_source_count", 0) == 0
    )
    if exhaustive_no_evidence:
        print(
            "decision-source evidence gate PASS via exhaustive no-evidence research: "
            f"drivers={q['target_count']} searches={q['query_attempt_count']} "
            f"successful_searches={q['successful_query_count']} company_research_complete=true. "
            "All driver rows remain source-free UNKNOWN; downstream evaluation is fail-closed and "
            "cannot create causal activation or a trade from this path."
        )
        return

    challenger_ok, accepted, challenger_sources, reason = _challenger_is_valid()
    if challenger_ok:
        print(
            "decision-source evidence gate PASS via same-snapshot challenger: "
            f"accepted={accepted} source_count={challenger_sources}; "
            f"autonomous_research_status={q['status']} autonomous_sources={q['total_sources']}"
        )
        return

    raise SystemExit(
        "decision-source evidence gate FAIL: neither autonomous research transport/evidence nor "
        "same-snapshot challenger is usable; "
        f"research_status={q['status']} research_sources={q['total_sources']} "
        f"transport_status={q['transport_status']} transport_candidates={q['candidate_source_count']} "
        f"challenger_reason={reason}"
    )


if __name__ == "__main__":
    main()
