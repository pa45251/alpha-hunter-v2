from __future__ import annotations

"""OpenAI Responses API adapter for bounded Alpha Hunter v3 fact research.

This module is intentionally provider-only. It does not grant support, map drivers,
change price/risk fields, or write trading actions. Deterministic ingest remains the
authority for evidence validation and terminal research accounting.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from research_ingest_v3 import _extract_json

RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_EFFORT = "high"
PROVIDER_VERSION = "OPENAI_RESEARCH_PROVIDER_V1"
CONTRACT = "ALPHA_HUNTER_V3_AUTONOMOUS_RESEARCH"
FIELDS = (
    "results",
    "company_opportunities",
    "company_research_coverage",
    "exposure_resolutions",
    "company_execution_failures",
)


def provider_identity() -> dict[str, str]:
    return {
        "provider": "OPENAI_RESPONSES_API",
        "provider_version": PROVIDER_VERSION,
        "model": os.environ.get("OPENAI_RESEARCH_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "reasoning_effort": os.environ.get("OPENAI_RESEARCH_REASONING_EFFORT", DEFAULT_EFFORT).strip() or DEFAULT_EFFORT,
    }


def _extract_text(body: dict[str, Any]) -> str:
    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _write_log(log_dir: Path, call_id: str, data: dict[str, Any]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    safe = dict(data)
    # Logs are local workflow diagnostics only; never persist authorization material.
    safe.pop("api_key", None)
    (log_dir / f"{call_id}.openai.json").write_text(
        json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def invoke_research(
    handoff: dict[str, Any],
    prefetch: dict[str, Any],
    shared: list[dict[str, Any]],
    call_id: str,
    log_dir: Path,
    developer_instructions: str,
):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    identity = provider_identity()
    if not key:
        _write_log(log_dir, call_id, {**identity, "failure": "OPENAI_API_KEY_MISSING"})
        return None, ("TRANSPORT_FAILED", "OPENAI_API_KEY_MISSING")

    company_only = bool(handoff.get("company_research_targets")) and not handoff.get("research_targets")
    shared_only = bool(handoff.get("research_targets")) and not handoff.get("company_research_targets")
    task_instruction = (
        "This is one isolated company-thesis research task. Return exactly one terminal company_research_coverage row for the admitted thesis. "
        "Shared-driver research is read-only context; results MUST be an empty list. "
        "Use only deterministic_prefetch URLs and exact contiguous source_quote text from document_text. "
        "If exposure or current transmission cannot be proven, return UNKNOWN_AFTER_RESEARCH rather than an incomplete opportunity."
        if company_only
        else
        "This is shared-driver research only. Return one results row per admitted research_targets row in input order. "
        "Do not write company opportunities, company coverage, exposure resolutions, or execution failures. "
        "ACTIVE/INACTIVE requires current non-price evidence from deterministic_prefetch; otherwise return UNKNOWN."
        if shared_only
        else
        "Research only the supplied admitted work and obey the bounded evidence contract."
    )

    user_payload = {
        "authoritative_handoff": handoff,
        "deterministic_prefetch": prefetch,
        "shared_driver_research": shared,
        "task_instruction": task_instruction,
    }
    request = {
        "model": identity["model"],
        "reasoning": {"effort": identity["reasoning_effort"]},
        "store": False,
        "input": [
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": developer_instructions}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=False)}],
            },
        ],
    }

    try:
        response = requests.post(
            RESPONSES_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=request,
            timeout=180,
        )
    except requests.RequestException as exc:
        code = f"OPENAI_TRANSPORT_{type(exc).__name__}"
        _write_log(log_dir, call_id, {**identity, "failure": code, "detail": str(exc)[:1200]})
        return None, ("TRANSPORT_FAILED", code)

    if not response.ok:
        code = f"OPENAI_HTTP_{response.status_code}"
        _write_log(
            log_dir,
            call_id,
            {**identity, "failure": code, "response_body": response.text[-4000:]},
        )
        return None, ("TRANSPORT_FAILED", code)

    try:
        body = response.json()
        text = _extract_text(body)
        if not text:
            raise ValueError("OPENAI_EMPTY_OUTPUT")
        payload = _extract_json(text)
        if payload.get("contract") != CONTRACT:
            raise ValueError("MODEL_ENVELOPE_MISMATCH")
        if str(payload.get("research_run_id") or "") != str(handoff.get("run_id") or ""):
            raise ValueError("MODEL_RUN_ID_MISMATCH")
        if any(not isinstance(payload.get(field, []), list) for field in FIELDS):
            raise ValueError("MODEL_LIST_SCHEMA_INVALID")
        if payload.get("company_execution_failures"):
            raise ValueError("MODEL_CANNOT_ASSIGN_EXECUTION_FAILURE")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        code = str(exc) or type(exc).__name__
        _write_log(
            log_dir,
            call_id,
            {
                **identity,
                "failure": code,
                "response_id": (body.get("id") if isinstance(locals().get("body"), dict) else None),
                "output_text_tail": (locals().get("text") or "")[-8000:],
            },
        )
        return None, ("SCHEMA_FAILED", code)

    payload["provider"] = identity["provider"]
    payload["provider_version"] = identity["provider_version"]
    payload["model"] = identity["model"]
    payload["reasoning_effort"] = identity["reasoning_effort"]
    payload["provider_response_id"] = body.get("id")
    payload["provider_generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_log(
        log_dir,
        call_id,
        {
            **identity,
            "status": "PASS",
            "response_id": body.get("id"),
            "usage": body.get("usage"),
        },
    )
    return payload, None
