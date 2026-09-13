from __future__ import annotations

import json
from pathlib import Path

PACKET = Path("output/deep_review_packet_v4.json")
REVIEW = Path("output/candidate_challenger_v4.json")
OUT = Path("output/final_candidate_review_v4.json")
CONTRACT = "ALPHA_HUNTER_FINAL_CANDIDATE_REVIEW_V4"


def _downgrade(action: str, verdict: str) -> str:
    if verdict == "CONFIRM":
        return action
    if verdict == "MORE_EVIDENCE_REQUIRED":
        return "WAIT"
    if verdict == "DOWNGRADE":
        return {"BUY": "WAIT", "EARLY BUY": "WAIT", "WAIT": "PASS"}.get(action, action)
    raise ValueError("INVALID_REVIEW_VERDICT")


def merge(packet: dict, review: dict) -> dict:
    from openai_candidate_challenger_v4 import packet_sha, validate

    run_id = str(packet.get("run_id") or "")
    if packet.get("contract") != "ALPHA_HUNTER_DEEP_REVIEW_PACKET_V4" or packet.get("status") != "PASS":
        raise RuntimeError("FINAL_REVIEW_PACKET_INVALID")
    if review.get("status") == "NO_TARGETS" and not packet.get("targets"):
        return {
            "contract": CONTRACT,
            "status": "PASS_NO_TARGETS",
            "run_id": run_id,
            "packet_sha256": packet_sha(packet),
            "auto_trade_allowed": False,
            "results": [],
        }
    errors = validate(review, packet)
    if errors or review.get("status") != "PASS":
        raise RuntimeError("FINAL_REVIEW_INVALID:" + ",".join(errors or review.get("validation_errors") or []))

    reviews = {str(x.get("thesis_id")): x for x in review.get("reviews") or []}
    results = []
    for target in packet.get("targets") or []:
        thesis = str(target.get("thesis_id") or "")
        item = reviews[thesis]
        canonical = str(target.get("canonical_action") or "")
        final_action = _downgrade(canonical, str(item.get("verdict") or ""))
        if canonical == "WAIT" and final_action not in {"WAIT", "PASS"}:
            raise RuntimeError("FINAL_REVIEW_UPGRADE_FORBIDDEN")
        if canonical == "EARLY BUY" and final_action == "BUY":
            raise RuntimeError("FINAL_REVIEW_UPGRADE_FORBIDDEN")
        results.append({
            "thesis_id": thesis,
            "ticker": target.get("ticker"),
            "canonical_action": canonical,
            "challenger_verdict": item.get("verdict"),
            "final_action": final_action,
            "evidence_ids": item.get("evidence_ids") or [],
            "rationale": item.get("rationale"),
            "auto_trade_allowed": False,
        })
    return {
        "contract": CONTRACT,
        "status": "PASS",
        "run_id": run_id,
        "packet_sha256": packet_sha(packet),
        "auto_trade_allowed": False,
        "results": results,
    }


def main() -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    payload = merge(packet, review)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"final candidate review: status={payload['status']} results={len(payload['results'])}")


if __name__ == "__main__":
    main()
