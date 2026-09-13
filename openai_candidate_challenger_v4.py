from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6"
CONTRACT = "ALPHA_HUNTER_CANDIDATE_CHALLENGER_V4"
VERDICTS = {"CONFIRM", "DOWNGRADE", "MORE_EVIDENCE_REQUIRED"}

DEVELOPER_INSTRUCTIONS = """You are Alpha Hunter's final adversarial reviewer, not its trading engine.
The supplied deep-review packet is the complete system of record.

Rules:
1. Do not browse, invent sources, infer missing company facts, or introduce new evidence.
2. Use only evidence_id values present in the candidate packet.
3. Price cannot create causality. You may inspect price/risk only for consistency with the already-computed plan.
4. You cannot change entry, stop, risk, size, driver identity, or canonical action.
5. You cannot upgrade an action. Your verdict is only CONFIRM, DOWNGRADE, or MORE_EVIDENCE_REQUIRED.
6. UNKNOWN or MORE_EVIDENCE_REQUIRED is preferable to filling gaps with a narrative.
7. Focus on thesis identity, evidence independence, company transmission, strongest counter-evidence, and whether the canonical action is supported.
8. Return JSON only.

Return contract ALPHA_HUNTER_CANDIDATE_CHALLENGER_V4, the exact run_id and packet_sha256, and one review per target in input order. Each review requires thesis_id, verdict, evidence_ids, thesis_identity_ok, evidence_independence_ok, transmission_ok, counter_evidence_reviewed, risk_plan_consistent, and concise rationale. Evidence_ids may be empty only for MORE_EVIDENCE_REQUIRED.
"""


def packet_sha(packet: dict[str, Any]) -> str:
    raw = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_text(body: dict[str, Any]) -> str:
    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks = []
    for item in body.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def validate(payload: dict[str, Any], packet: dict[str, Any]) -> list[str]:
    errors = []
    run_id = str(packet.get("run_id") or "")
    digest = packet_sha(packet)
    if payload.get("contract") != CONTRACT:
        errors.append("CONTRACT_MISMATCH")
    if str(payload.get("run_id") or "") != run_id:
        errors.append("RUN_ID_MISMATCH")
    if str(payload.get("packet_sha256") or "") != digest:
        errors.append("PACKET_HASH_MISMATCH")

    targets = packet.get("targets") or []
    target_ids = [str(x.get("thesis_id") or "") for x in targets]
    evidence_by_thesis = {
        str(x.get("thesis_id") or ""): {str(e.get("evidence_id")) for e in x.get("evidence") or []}
        for x in targets
    }
    reviews = payload.get("reviews")
    if not isinstance(reviews, list):
        return errors + ["REVIEWS_NOT_LIST"]
    review_ids = [str(x.get("thesis_id") or "") for x in reviews if isinstance(x, dict)]
    if review_ids != target_ids:
        errors.append("TARGET_ORDER_OR_COVERAGE_MISMATCH")

    for row in reviews:
        if not isinstance(row, dict):
            errors.append("REVIEW_NOT_OBJECT")
            continue
        thesis = str(row.get("thesis_id") or "")
        verdict = str(row.get("verdict") or "")
        if verdict not in VERDICTS:
            errors.append(f"INVALID_VERDICT:{thesis}")
        ids = row.get("evidence_ids")
        if not isinstance(ids, list):
            errors.append(f"EVIDENCE_IDS_NOT_LIST:{thesis}")
            continue
        unknown = sorted(set(map(str, ids)) - evidence_by_thesis.get(thesis, set()))
        if unknown:
            errors.append(f"UNKNOWN_EVIDENCE_ID:{thesis}:{unknown[:3]}")
        if verdict in {"CONFIRM", "DOWNGRADE"} and not ids:
            errors.append(f"CITED_EVIDENCE_REQUIRED:{thesis}")
        for field in (
            "thesis_identity_ok", "evidence_independence_ok", "transmission_ok",
            "counter_evidence_reviewed", "risk_plan_consistent",
        ):
            if not isinstance(row.get(field), bool):
                errors.append(f"BOOLEAN_CHECK_REQUIRED:{thesis}:{field}")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            errors.append(f"RATIONALE_REQUIRED:{thesis}")
        if verdict == "CONFIRM" and not all(row.get(field) is True for field in (
            "thesis_identity_ok", "evidence_independence_ok", "transmission_ok",
            "counter_evidence_reviewed", "risk_plan_consistent",
        )):
            errors.append(f"CONFIRM_REQUIRES_ALL_CHECKS:{thesis}")
    return errors


def call_openai(packet: dict[str, Any], model: str, effort: str) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    digest = packet_sha(packet)
    user = {
        "run_id": packet.get("run_id"),
        "packet_sha256": digest,
        "deep_review_packet": packet,
        "instruction": "Adversarially review every target. Do not add evidence or change canonical trading fields.",
    }
    request = {
        "model": model,
        "reasoning": {"effort": effort},
        "store": False,
        "input": [
            {"role": "developer", "content": [{"type": "input_text", "text": DEVELOPER_INSTRUCTIONS}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(user, ensure_ascii=False)}]},
        ],
    }
    response = requests.post(
        RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=request,
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    text = _extract_text(body)
    if not text:
        raise RuntimeError("OpenAI response contained no output text")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAI output must be an object")
    payload["provider"] = "OPENAI_RESPONSES_API"
    payload["model"] = model
    payload["reasoning_effort"] = effort
    payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    payload["response_id"] = body.get("id")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    if packet.get("contract") != "ALPHA_HUNTER_DEEP_REVIEW_PACKET_V4" or packet.get("status") != "PASS":
        raise RuntimeError("DEEP_REVIEW_PACKET_INVALID")
    if not packet.get("targets"):
        Path(args.out).write_text(json.dumps({
            "contract": CONTRACT,
            "run_id": packet.get("run_id"),
            "packet_sha256": packet_sha(packet),
            "status": "NO_TARGETS",
            "reviews": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("candidate challenger: NO_TARGETS")
        return 0

    model = os.environ.get("OPENAI_FRONTIER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    effort = os.environ.get("OPENAI_FRONTIER_REASONING_EFFORT", "high").strip() or "high"
    payload = call_openai(packet, model, effort)
    errors = validate(payload, packet)
    payload["status"] = "PASS" if not errors else "FAIL"
    payload["validation_errors"] = errors
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "PASS", "targets": len(packet["targets"]), "model": model}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
