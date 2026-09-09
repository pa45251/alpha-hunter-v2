from openai_frontier_research_v4 import extract_output_text, validate_frontier_payload


def test_extract_output_text_from_responses_shape():
    response = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": '{"ok":true}'}],
            }
        ]
    }
    assert extract_output_text(response) == '{"ok":true}'


def test_frontier_payload_accepts_unknown_without_sources():
    handoff = {"run_id": "run-1", "research_targets": [{"driver_id": "DRIVER_A"}]}
    payload = {
        "contract": "ALPHA_HUNTER_FRONTIER_RESEARCH_V4",
        "research_run_id": "run-1",
        "results": [
            {
                "driver_id": "DRIVER_A",
                "state": "UNKNOWN",
                "confidence": 0.2,
                "supporting_evidence": [],
                "counter_evidence": [],
                "source_count": 0,
            }
        ],
    }
    assert validate_frontier_payload(payload, handoff) == []


def test_frontier_payload_rejects_active_without_source():
    handoff = {"run_id": "run-1", "research_targets": [{"driver_id": "DRIVER_A"}]}
    payload = {
        "contract": "ALPHA_HUNTER_FRONTIER_RESEARCH_V4",
        "research_run_id": "run-1",
        "results": [
            {
                "driver_id": "DRIVER_A",
                "state": "ACTIVE",
                "confidence": 0.8,
                "supporting_evidence": [],
                "counter_evidence": [],
                "source_count": 0,
            }
        ],
    }
    errors = validate_frontier_payload(payload, handoff)
    assert "SOURCE_REQUIRED_FOR_DECISIVE_STATE:DRIVER_A" in errors


def test_frontier_payload_rejects_run_mismatch():
    handoff = {"run_id": "run-1", "research_targets": [{"driver_id": "DRIVER_A"}]}
    payload = {
        "contract": "ALPHA_HUNTER_FRONTIER_RESEARCH_V4",
        "research_run_id": "run-2",
        "results": [
            {
                "driver_id": "DRIVER_A",
                "state": "UNKNOWN",
                "confidence": 0.1,
                "supporting_evidence": [],
                "counter_evidence": [],
                "source_count": 0,
            }
        ],
    }
    assert "RUN_ID_MISMATCH" in validate_frontier_payload(payload, handoff)


def test_frontier_payload_rejects_source_outside_deterministic_prefetch():
    handoff = {"run_id": "run-1", "research_targets": [{"driver_id": "DRIVER_A"}]}
    prefetch = {
        "research_run_id": "run-1",
        "targets": [
            {
                "driver_id": "DRIVER_A",
                "candidate_sources": [
                    {"source_url": "https://allowed.example/source"},
                ],
            }
        ],
    }
    payload = {
        "contract": "ALPHA_HUNTER_FRONTIER_RESEARCH_V4",
        "research_run_id": "run-1",
        "results": [
            {
                "driver_id": "DRIVER_A",
                "state": "ACTIVE",
                "confidence": 0.8,
                "supporting_evidence": [
                    {
                        "claim": "claim",
                        "source_title": "invented",
                        "source_url": "https://invented.example/source",
                        "published_at": "2026-09-09T00:00:00Z",
                        "event_date": None,
                        "evidence_type": "HIGH_QUALITY_REPORTING",
                    }
                ],
                "counter_evidence": [],
                "source_count": 1,
            }
        ],
    }
    errors = validate_frontier_payload(payload, handoff, prefetch)
    assert any(error.startswith("SOURCE_NOT_IN_DETERMINISTIC_PREFETCH:DRIVER_A:") for error in errors)
