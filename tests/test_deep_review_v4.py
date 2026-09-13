from __future__ import annotations

from candidate_review_merge_v4 import merge
from openai_candidate_challenger_v4 import packet_sha, validate


def _packet(action="EARLY BUY"):
    return {
        "contract": "ALPHA_HUNTER_DEEP_REVIEW_PACKET_V4",
        "status": "PASS",
        "run_id": "run-1",
        "targets": [{
            "thesis_id": "t1",
            "ticker": "1111.TW",
            "canonical_action": action,
            "evidence": [
                {"evidence_id": "E_1", "scope": "EXPOSURE", "claim": "product exposure", "source_url": "https://example.com/a"},
                {"evidence_id": "E_2", "scope": "DRIVER_CURRENT", "claim": "driver active", "source_url": "https://example.com/b"},
            ],
        }],
    }


def _review(packet, verdict="CONFIRM"):
    return {
        "contract": "ALPHA_HUNTER_CANDIDATE_CHALLENGER_V4",
        "status": "PASS",
        "run_id": "run-1",
        "packet_sha256": packet_sha(packet),
        "reviews": [{
            "thesis_id": "t1",
            "verdict": verdict,
            "evidence_ids": ["E_1", "E_2"],
            "thesis_identity_ok": True,
            "evidence_independence_ok": True,
            "transmission_ok": True,
            "counter_evidence_reviewed": True,
            "risk_plan_consistent": True,
            "rationale": "Supported by supplied evidence.",
        }],
    }


def test_challenger_cannot_cite_unknown_evidence():
    packet = _packet()
    review = _review(packet)
    review["reviews"][0]["evidence_ids"] = ["E_FAKE"]
    assert any("UNKNOWN_EVIDENCE_ID" in e for e in validate(review, packet))


def test_downgrade_never_upgrades_early_buy():
    packet = _packet("EARLY BUY")
    result = merge(packet, _review(packet, "DOWNGRADE"))
    assert result["results"][0]["final_action"] == "WAIT"


def test_more_evidence_for_buy_becomes_wait():
    packet = _packet("BUY")
    review = _review(packet, "MORE_EVIDENCE_REQUIRED")
    review["reviews"][0]["evidence_ids"] = []
    result = merge(packet, review)
    assert result["results"][0]["final_action"] == "WAIT"


def test_confirm_preserves_canonical_action():
    packet = _packet("EARLY BUY")
    result = merge(packet, _review(packet, "CONFIRM"))
    assert result["results"][0]["final_action"] == "EARLY BUY"


def test_wait_downgrade_can_only_move_to_pass():
    packet = _packet("WAIT")
    result = merge(packet, _review(packet, "DOWNGRADE"))
    assert result["results"][0]["final_action"] == "PASS"
