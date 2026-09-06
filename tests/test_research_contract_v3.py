import pytest

from research_contract_v3 import ResearchContractError, downstream_state, validate_research_result


def evidence(kind="PRIMARY"):
    return {
        "claim": "Exact driver evidence",
        "source_title": "Source",
        "source_url": "https://example.com/source",
        "published_at": "2026-09-06T00:00:00Z",
        "event_date": "2026-09-05T00:00:00Z",
        "evidence_type": kind,
    }


def research(state="ACTIVE"):
    return {
        "driver_id": "AI_SERVER_SHIPMENTS",
        "state": state,
        "confidence": 0.9,
        "primary_cause": "Demand translated into shipments",
        "industry_scope": "INDUSTRY_WIDE",
        "supporting_evidence": [evidence()],
        "counter_evidence": [evidence()],
        "source_count": 2,
        "researched_at_utc": "2026-09-06T01:00:00Z",
        "research_run_id": "research-1",
    }


def challenge(verdict="PASS", all_true=True):
    names = [
        "exact_driver_match",
        "causal_direction",
        "event_time_consistency",
        "industry_scope",
        "company_specific_contamination",
        "circular_sourcing",
        "stale_evidence",
        "counter_evidence_reviewed",
        "price_not_used_as_causality",
    ]
    checks = {name: True for name in names}
    if not all_true:
        checks["exact_driver_match"] = False
    return {
        "driver_id": "AI_SERVER_SHIPMENTS",
        "research_run_id": "research-1",
        "verdict": verdict,
        "checks": checks,
    }


def test_active_source_backed_passes():
    validate_research_result(research(), {"AI_SERVER_SHIPMENTS"})


def test_unknown_driver_fails_closed():
    with pytest.raises(ResearchContractError):
        validate_research_result(research(), {"DRAM_PRICING"})


def test_price_evidence_cannot_create_causality():
    row = research()
    row["supporting_evidence"] = [evidence("PRICE")]
    with pytest.raises(ResearchContractError, match="PRICE_CANNOT_CREATE_CAUSALITY"):
        validate_research_result(row, {"AI_SERVER_SHIPMENTS"})


def test_active_without_sources_fails():
    row = research()
    row["supporting_evidence"] = []
    row["source_count"] = 0
    with pytest.raises(ResearchContractError):
        validate_research_result(row, {"AI_SERVER_SHIPMENTS"})


def test_challenger_nonpass_downgrades_active_to_unknown():
    assert downstream_state(research(), challenge("NEEDS_MORE_EVIDENCE")) == "UNKNOWN"


def test_challenger_pass_preserves_active():
    assert downstream_state(research(), challenge("PASS")) == "ACTIVE"


def test_false_check_cannot_pass():
    with pytest.raises(ResearchContractError):
        downstream_state(research(), challenge("PASS", all_true=False))
