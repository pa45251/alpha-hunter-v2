import json

import research_quality_gate_v3 as qg


def test_partial_status_can_continue_with_valid_transport(tmp_path):
    result = tmp_path / "research.json"
    transport = tmp_path / "transport.json"
    result.write_text(json.dumps({
        "status": qg.PARTIAL_STATUS,
        "research_run_id": "run-1",
        "results": [
            {"state": "UNKNOWN", "source_count": 0},
            {"state": "UNKNOWN", "source_count": 1},
            {"state": "UNKNOWN", "source_count": 1},
        ],
    }), encoding="utf-8")
    transport.write_text(json.dumps({
        "contract": "ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH",
        "status": "PASS",
        "research_run_id": "run-1",
        "target_count": 3,
        "query_attempt_count": 6,
        "successful_query_count": 6,
        "candidate_source_count": 9,
        "sourced_target_count": 2,
    }), encoding="utf-8")

    q = qg.evaluate(result, transport)
    assert q["quality_pass"] is True
    assert q["transport_pass"] is True


def test_partial_status_still_rejects_stale_transport_without_evidence(tmp_path):
    result = tmp_path / "research.json"
    transport = tmp_path / "transport.json"
    result.write_text(json.dumps({
        "status": qg.PARTIAL_STATUS,
        "research_run_id": "run-1",
        "results": [{"state": "UNKNOWN", "source_count": 0}],
    }), encoding="utf-8")
    transport.write_text(json.dumps({
        "contract": "ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH",
        "status": "PASS",
        "research_run_id": "stale-run",
        "target_count": 1,
        "query_attempt_count": 2,
        "successful_query_count": 2,
        "candidate_source_count": 2,
        "sourced_target_count": 1,
    }), encoding="utf-8")

    q = qg.evaluate(result, transport)
    assert q["quality_pass"] is False
    assert q["transport_status"] == "RUN_ID_MISMATCH"
