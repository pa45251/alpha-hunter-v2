"""Alpha Hunter v3.0 deterministic validator for autonomous research artifacts.

This module intentionally performs no web research and makes no causal inference.
It validates the output of a future research provider before downstream use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

VALID_STATES = {"ACTIVE", "INACTIVE", "UNKNOWN"}
VALID_SCOPES = {"INDUSTRY_WIDE", "COMPANY_SPECIFIC", "MIXED", "UNKNOWN"}
VALID_CHALLENGER = {"PASS", "DOWNGRADE_TO_UNKNOWN", "REJECT_INACTIVE", "NEEDS_MORE_EVIDENCE"}


class ResearchContractError(ValueError):
    pass


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_http_url(value: Any) -> bool:
    if not _nonempty(value):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_iso(value: Any) -> datetime:
    if not _nonempty(value):
        raise ResearchContractError("missing timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception as exc:
        raise ResearchContractError(f"invalid timestamp: {value}") from exc


def validate_evidence_item(item: dict[str, Any]) -> None:
    required = {"claim", "source_title", "source_url", "published_at", "evidence_type"}
    missing = sorted(k for k in required if not _nonempty(item.get(k)))
    if missing:
        raise ResearchContractError(f"evidence missing fields: {missing}")
    if not _valid_http_url(item["source_url"]):
        raise ResearchContractError("evidence source_url must be http(s)")
    _parse_iso(item["published_at"])
    if item.get("event_date"):
        _parse_iso(item["event_date"])
    if str(item.get("evidence_type", "")).upper() == "PRICE":
        raise ResearchContractError("PRICE_CANNOT_CREATE_CAUSALITY")


def validate_research_result(result: dict[str, Any], allowed_driver_ids: Iterable[str]) -> None:
    allowed = set(allowed_driver_ids)
    driver_id = result.get("driver_id")
    if driver_id not in allowed:
        raise ResearchContractError(f"unknown or unnominated driver_id: {driver_id}")
    if result.get("state") not in VALID_STATES:
        raise ResearchContractError("invalid research state")
    if result.get("industry_scope") not in VALID_SCOPES:
        raise ResearchContractError("invalid industry_scope")
    confidence = result.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise ResearchContractError("confidence must be numeric 0..1")
    _parse_iso(result.get("researched_at_utc"))
    if not _nonempty(result.get("research_run_id")):
        raise ResearchContractError("missing research_run_id")

    supporting = result.get("supporting_evidence") or []
    counter = result.get("counter_evidence") or []
    if not isinstance(supporting, list) or not isinstance(counter, list):
        raise ResearchContractError("evidence fields must be lists")
    for item in supporting + counter:
        if not isinstance(item, dict):
            raise ResearchContractError("evidence item must be object")
        validate_evidence_item(item)

    if result["state"] == "ACTIVE":
        if len(supporting) < 1:
            raise ResearchContractError("ACTIVE requires source-backed supporting evidence")
        if int(result.get("source_count", -1)) < 1:
            raise ResearchContractError("ACTIVE requires source_count >= 1")
        if not _nonempty(result.get("primary_cause")):
            raise ResearchContractError("ACTIVE requires primary_cause")


def validate_challenger_result(challenge: dict[str, Any], research: dict[str, Any]) -> None:
    if challenge.get("driver_id") != research.get("driver_id"):
        raise ResearchContractError("challenger driver_id mismatch")
    if challenge.get("research_run_id") != research.get("research_run_id"):
        raise ResearchContractError("challenger research_run_id mismatch")
    if challenge.get("verdict") not in VALID_CHALLENGER:
        raise ResearchContractError("invalid challenger verdict")
    checks = challenge.get("checks")
    if not isinstance(checks, dict):
        raise ResearchContractError("challenger checks missing")
    required_checks = {
        "exact_driver_match",
        "causal_direction",
        "event_time_consistency",
        "industry_scope",
        "company_specific_contamination",
        "circular_sourcing",
        "stale_evidence",
        "counter_evidence_reviewed",
        "price_not_used_as_causality",
    }
    if set(checks) != required_checks or not all(isinstance(v, bool) for v in checks.values()):
        raise ResearchContractError("challenger checks incomplete or malformed")
    if challenge["verdict"] == "PASS" and not all(checks.values()):
        raise ResearchContractError("PASS requires every challenger check true")


def downstream_state(research: dict[str, Any], challenge: dict[str, Any]) -> str:
    """Return only a state safe for downstream transmission."""
    validate_challenger_result(challenge, research)
    if research.get("state") == "ACTIVE" and challenge.get("verdict") != "PASS":
        return "UNKNOWN"
    if challenge.get("verdict") == "REJECT_INACTIVE":
        return "INACTIVE"
    return str(research.get("state", "UNKNOWN"))
