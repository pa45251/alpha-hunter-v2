from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from causal_engine import CausalConfig, validate_driver_activation_file
from research_quality_gate_v3 import evaluate as evaluate_research_quality


OUT = Path("output")


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
    if q["status"] == "PASS" and q["evidence_pass"]:
        print(
            "decision-source evidence gate PASS via autonomous research evidence: "
            f"total_sources={q['total_sources']} sourced_drivers={q['sourced_drivers']}"
        )
        return

    if q["status"] == "PASS" and q["transport_pass"]:
        print(
            "decision-source evidence gate PASS via deterministic external-search transport: "
            f"searches={q['query_attempt_count']} candidate_sources={q['candidate_source_count']} "
            f"sourced_targets={q['sourced_target_count']}; autonomous_sources={q['total_sources']}. "
            "This authorizes downstream fail-closed evaluation only; causal activation still requires "
            "source-backed ACTIVE/INACTIVE research rows."
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
