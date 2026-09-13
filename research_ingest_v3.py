"""Fail-closed ingestion for Alpha Hunter v3 autonomous research output."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from research_contract_v3 import ResearchContractError, validate_research_result

PACKET = Path("output/research_packet.json")
RAW = Path("output/research_result_v3.raw.txt")
OUT = Path("output/research_result_v3.json")
DEFAULT_PREFETCH = Path("/tmp/research_prefetch_v3.json")
PREFETCH_CONTRACT = "ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str):
    text = text.strip().lstrip("\ufeff")
    if not text:
        raise ResearchContractError("empty autonomous research output")
    candidates = [text]
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidates.append("\n".join(lines).strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if not isinstance(payload, dict):
                raise ResearchContractError("top-level research payload must be an object")
            return payload
        except json.JSONDecodeError:
            pass
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    preview = text[:180].replace("\n", " ")
    raise ResearchContractError(f"no valid top-level JSON object found; raw_prefix={preview!r}")


def _unknown(driver_id: str, run_id: str, reason: str) -> dict:
    return {
        "driver_id": driver_id,
        "state": "UNKNOWN",
        "confidence": 0.0,
        "primary_cause": reason,
        "industry_scope": "UNKNOWN",
        "supporting_evidence": [],
        "counter_evidence": [],
        "source_count": 0,
        "event_date": None,
        "source_dates": [],
        "researched_at_utc": _utcnow(),
        "research_run_id": run_id,
    }


def _source_urls(items) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {str(item.get("source_url")) for item in items if isinstance(item, dict) and item.get("source_url")}


def _bind_driver_metadata(result: dict, run_id: str) -> tuple[dict, set[str]]:
    """Derive metadata already knowable from the validated envelope/evidence rows."""
    row = dict(result)
    supplied = row.get('research_run_id')
    if supplied not in {None, ''} and str(supplied) != str(run_id):
        raise ResearchContractError('per-driver run_id mismatch')
    row['research_run_id'] = run_id
    urls = _source_urls(row.get('supporting_evidence')) | _source_urls(row.get('counter_evidence'))
    row['source_count'] = len(urls)
    return row, urls


def _company_fact_urls(row: dict) -> set[str]:
    urls = _source_urls(row.get("fundamental_evidence")) | _source_urls(row.get("exposure_evidence")) | _source_urls(row.get("counter_evidence"))
    proof = row.get("local_scope_evidence")
    if isinstance(proof, dict):
        for field in ("event_evidence", "global_alternative_evidence"):
            item = proof.get(field)
            if isinstance(item, dict) and item.get("source_url"):
                urls.add(str(item["source_url"]))
    return urls


def _driver_fact_urls(row: dict) -> set[str]:
    return _source_urls(row.get("international_evidence"))


def _prefetch_allowlists(run_id: str) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    path = Path(os.getenv("ALPHA_HUNTER_RESEARCH_TRANSPORT_PATH", str(DEFAULT_PREFETCH)))
    if not path.exists():
        raise ResearchContractError("DETERMINISTIC_SOURCE_TRANSPORT_MISSING")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("contract") != PREFETCH_CONTRACT or data.get("status") not in {"PASS", "FAIL_CLOSED"}:
        raise ResearchContractError("DETERMINISTIC_SOURCE_TRANSPORT_INVALID")
    if str(data.get("research_run_id", "")) != str(run_id):
        raise ResearchContractError("DETERMINISTIC_SOURCE_TRANSPORT_RUN_MISMATCH")

    drivers: dict[str, set[str]] = {}
    for target in data.get("targets") or []:
        if isinstance(target, dict):
            drivers[str(target.get("driver_id", ""))] = _source_urls(target.get("candidate_sources"))
    companies: dict[tuple[str, str], set[str]] = {}
    for target in data.get("company_targets") or []:
        if isinstance(target, dict):
            key = (str(target.get("ticker", "")), str(target.get("driver_id", "")))
            companies[key] = _source_urls(target.get("candidate_sources"))
    return drivers, companies


def _assert_urls_prefetched(urls: set[str], allowed: set[str], label: str) -> None:
    escaped = sorted(urls - allowed)
    if escaped:
        raise ResearchContractError(f"UNPREFETCHED_EVIDENCE_URL:{label}:{escaped[:3]}")


def _failure_code(exc: Exception | str) -> str:
    return "TRANSPORT_FAILED" if "DETERMINISTIC_SOURCE_TRANSPORT" in str(exc) else "SCHEMA_FAILED"


def main() -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    run_id = str(packet["run_id"])
    queue = packet.get("research_queue_top30") or []
    if (PACKET.parent / "causal_research_queue.csv").exists():
        from driver_gates import sealed_csv
        queue = sealed_csv("causal_research_queue.csv", PACKET.parent).to_dict("records")
    from research_handoff import decision_research_handoff
    selection_path = os.getenv("ALPHA_HUNTER_RESEARCH_SELECTION_PATH")
    selection = json.loads(Path(selection_path).read_text()) if selection_path else decision_research_handoff(PACKET.parent)
    if selection.get("run_id") != run_id:
        raise RuntimeError("RESEARCH_SELECTION_RUN_MISMATCH")
    targets = selection["research_targets"]
    if any(r.get("driver_id") not in {q["driver_id"] for q in queue} for r in targets):
        raise RuntimeError("RESEARCH_SELECTION_NOT_CANONICAL")
    target_ids = [str(x["driver_id"]) for x in targets]
    target_set = set(target_ids)

    status = "PASS"
    errors: list[str] = []
    supplied: dict[str, dict] = {}
    company_opportunities: list[dict] = []
    company_errors: list[str] = []
    company_failures: list[dict] = []

    default_failure = None
    try:
        driver_allow, company_allow = _prefetch_allowlists(run_id)
        payload = _extract_json(RAW.read_text(encoding="utf-8"))
        if payload.get("contract") != "ALPHA_HUNTER_V3_AUTONOMOUS_RESEARCH":
            raise ResearchContractError("research contract marker mismatch")
        if str(payload.get("research_run_id")) != run_id:
            raise ResearchContractError("research run_id mismatch")
        results = payload.get("results")
        if not isinstance(results, list):
            raise ResearchContractError("results must be a list")
        for original in results:
            if not isinstance(original, dict):
                errors.append("non-object result rejected")
                continue
            driver_id = str(original.get("driver_id", ""))
            if driver_id not in target_set:
                errors.append(f"unnominated/non-target driver rejected: {driver_id}")
                continue
            if driver_id in supplied:
                errors.append(f"duplicate driver rejected: {driver_id}")
                continue
            try:
                result, urls = _bind_driver_metadata(original, run_id)
                validate_research_result(result, target_set)
                _assert_urls_prefetched(urls, driver_allow.get(driver_id, set()), driver_id)
                supplied[driver_id] = result
            except Exception as exc:
                errors.append(f"{driver_id}: {exc}")
    except Exception as exc:
        status = "RESEARCH_UNAVAILABLE"
        errors.append(str(exc))
        driver_allow, company_allow = {}, {}
        payload = {}
        default_failure = (_failure_code(exc), str(exc))
        if isinstance(exc, OSError) or "empty autonomous" in str(exc):
            default_failure = ("TRANSPORT_FAILED", str(exc))

    from opportunity_advisory import validate_company_research
    from company_research_terminal import finalize, resolve_identity
    nominated_companies = selection["company_research_targets"]
    company_targets = {(r["ticker"], r["driver_id"]) for r in nominated_companies}
    if status == "PASS":
        seen_company = set()
        for original in payload.get("company_opportunities") or []:
            row = original
            try:
                row = resolve_identity(row, nominated_companies)
                validate_company_research(row, run_id, company_targets, _utcnow())
                key = (row["ticker"], row["driver_id"])
                if row["thesis_id"] in seen_company:
                    raise ValueError("DUPLICATE_COMPANY_RESEARCH")
                _assert_urls_prefetched(_company_fact_urls(row), company_allow.get(key, set()), f"COMPANY:{key[0]}:{key[1]}")
                if row.get("driver_id") != "UNMAPPED_OPPORTUNITY":
                    _assert_urls_prefetched(_driver_fact_urls(row), driver_allow.get(str(row.get("driver_id")), set()),
                                            f"DRIVER:{key[0]}:{key[1]}")
                elif _driver_fact_urls(row):
                    raise ResearchContractError("UNMAPPED_COMPANY_CANNOT_CLAIM_SHARED_DRIVER_EVIDENCE")
                transport = json.loads(Path(os.getenv("ALPHA_HUNTER_RESEARCH_TRANSPORT_PATH", str(DEFAULT_PREFETCH))).read_text())
                if transport.get("document_contract") == "EXACT_COMPANY_DOCUMENT_V1":
                    from company_source_documents import verify_document_claim
                    docs = {s["source_url"]: s for t in transport.get("company_targets", [])
                            if (t.get("ticker"), t.get("driver_id")) == key
                            for s in t.get("candidate_sources", [])}
                    exposures = row.get("exposure_evidence") or []
                    if row.get("driver_state") != "REJECTED" and not exposures:
                        raise ValueError("SOURCE_BACKED_COMPANY_EXPOSURE_REQUIRED")
                    for item in exposures:
                        verify_document_claim(item, docs, specific=True)
                    for item in row.get("fundamental_evidence") or []:
                        verify_document_claim(item, docs)
                    for item in (row.get("local_scope_evidence") or {}).values():
                        if isinstance(item, dict) and item.get("source_url"):
                            verify_document_claim(item, docs, specific=True)
                    specific = [e for e in row.get("fundamental_evidence", [])
                                if (docs.get(e.get("source_url")) or {}).get("evidence_role") != "GENERIC_REVENUE_ONLY"]
                    if row.get("driver_state") != "REJECTED" and not specific:
                        raise ValueError("SPECIFIC_COMPANY_TRANSMISSION_REQUIRED")
                    if row.get("driver_state") == "REJECTED":
                        counter = row.get("counter_evidence") or []
                        if not counter:
                            raise ValueError("SOURCE_BACKED_REJECTION_REQUIRED")
                        for item in counter:
                            verify_document_claim(item, docs, specific=True)
                seen_company.add(row["thesis_id"])
                company_opportunities.append(row)
            except (ValueError, TypeError, ResearchContractError) as exc:
                company_errors.append(str(exc))
                if isinstance(row, dict) and (row.get("ticker"), row.get("driver_id")) in company_targets:
                    company_failures.append(dict(ticker=row["ticker"], driver_id=row["driver_id"], thesis_id=row.get("thesis_id"),
                                                 failure_code=_failure_code(exc), reason=str(exc)))

    final_results = []
    for driver_id in target_ids:
        if driver_id in supplied:
            final_results.append(supplied[driver_id])
        else:
            status = "PARTIAL_FAIL_CLOSED" if status == "PASS" else status
            final_results.append(_unknown(driver_id, run_id, "Autonomous research output missing or failed deterministic validation."))

    company_failures.extend(payload.get("company_execution_failures") or [])
    company_opportunities, coverage_rows, terminal_summary, terminal_errors = finalize(
        nominated_companies, company_opportunities, payload.get("company_research_coverage", []), company_failures, default_failure)
    company_errors.extend(terminal_errors)
    company_failures = [dict(r, failure_code=r["status"]) for r in coverage_rows
                        if r["status"] in {"TRANSPORT_FAILED", "SCHEMA_FAILED"}]

    out = {
        "contract": "ALPHA_HUNTER_V3_VALIDATED_RESEARCH",
        "status": status,
        "research_run_id": run_id,
        "validated_at_utc": _utcnow(),
        "target_driver_ids": target_ids,
        "errors": errors,
        "results": final_results,
        "company_opportunities": company_opportunities,
        "company_research_errors": company_errors,
        "company_research_failures": company_failures,
        "company_research_coverage": coverage_rows,
        "company_terminal_summary": terminal_summary,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"v3 research ingest: {status}; valid={len(supplied)}/{len(target_ids)} company_opportunities={len(company_opportunities)} company_failures={len(company_failures)}")
    if errors:
        for err in errors[:8]:
            print(f"research ingest diagnostic: {err}")


if __name__ == "__main__":
    main()
