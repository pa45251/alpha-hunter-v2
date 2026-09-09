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
