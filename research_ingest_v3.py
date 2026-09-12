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


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str):
    """Extract one top-level JSON object without relaxing downstream validation.

    Copilot CLI can occasionally wrap an otherwise valid JSON object with brief
    prose/tool chatter. We tolerate only that transport noise. The extracted
    object must still pass the exact research contract, run_id, target and
    evidence validators below.
    """
    text = text.strip().lstrip("\ufeff")
    if not text:
        raise ResearchContractError("empty autonomous research output")

    # Fast path: strict JSON or a single fenced JSON block.
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

    # Bounded recovery for prefix/suffix chatter: scan for the first decodable
    # top-level object and reject any case where none is found.
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


def main() -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    run_id = str(packet["run_id"])
    queue = packet.get("research_queue_top30") or []
    from research_handoff import decision_research_handoff
    selection_path = os.getenv('ALPHA_HUNTER_RESEARCH_SELECTION_PATH')
    selection = json.loads(Path(selection_path).read_text()) if selection_path else decision_research_handoff(PACKET.parent)
    if selection.get('run_id') != run_id:
        raise RuntimeError('RESEARCH_SELECTION_RUN_MISMATCH')
    targets = selection['research_targets']
    if any(r.get('driver_id') not in {q['driver_id'] for q in queue} for r in targets):
        raise RuntimeError('RESEARCH_SELECTION_NOT_CANONICAL')
    target_ids = [str(x["driver_id"]) for x in targets]
    target_set = set(target_ids)

    status = "PASS"
    errors: list[str] = []
    supplied: dict[str, dict] = {}
    company_opportunities = []
    company_errors = []
    company_invalid_coverage = []

    try:
        raw_text = RAW.read_text(encoding="utf-8")
        payload = _extract_json(raw_text)
        if payload.get("contract") != "ALPHA_HUNTER_V3_AUTONOMOUS_RESEARCH":
            raise ResearchContractError("research contract marker mismatch")
        if str(payload.get("research_run_id")) != run_id:
            raise ResearchContractError("research run_id mismatch")
        results = payload.get("results")
        if not isinstance(results, list):
            raise ResearchContractError("results must be a list")
        for result in results:
            if not isinstance(result, dict):
                errors.append("non-object result rejected")
                continue
            driver_id = str(result.get("driver_id", ""))
            if driver_id not in target_set:
                errors.append(f"unnominated/non-target driver rejected: {driver_id}")
                continue
            if driver_id in supplied:
                errors.append(f"duplicate driver rejected: {driver_id}")
                continue
            try:
                if str(result.get("research_run_id")) != run_id:
                    raise ResearchContractError("per-driver run_id mismatch")
                validate_research_result(result, target_set)
                urls = {
                    e.get("source_url")
                    for e in (result.get("supporting_evidence") or []) + (result.get("counter_evidence") or [])
                    if isinstance(e, dict) and e.get("source_url")
                }
                if int(result.get("source_count", -1)) != len(urls):
                    raise ResearchContractError("source_count must equal unique evidence URLs")
                supplied[driver_id] = result
            except Exception as exc:
                errors.append(f"{driver_id}: {exc}")
    except Exception as exc:
        status = "RESEARCH_UNAVAILABLE"
        errors.append(str(exc))

    # Optional company intelligence is independently validated and never activates V2 edges.
    from research_handoff import company_research_targets
    from opportunity_advisory import validate_company_research
    company_targets = {(r['ticker'], r['driver_id']) for r in selection['company_research_targets']}
    if status == 'PASS':
        seen_company = set()
        for row in payload.get('company_opportunities') or []:
            try:
                validate_company_research(row, run_id, company_targets, _utcnow())
                key = (row['ticker'], row['driver_id'])
                if key in seen_company:
                    raise ValueError('DUPLICATE_COMPANY_RESEARCH')
                seen_company.add(key)
                company_opportunities.append(row)
            except (ValueError, TypeError) as exc:
                company_errors.append(str(exc))
                if isinstance(row, dict) and (row.get('ticker'), row.get('driver_id')) in company_targets:
                    company_invalid_coverage.append(dict(ticker=row['ticker'], driver_id=row['driver_id'], status='UNRESOLVED', reason='Research failed validation: ' + str(exc)))

    if status == 'PASS':
        covered = {(r.get('ticker'), r.get('driver_id')) for r in company_opportunities}
        covered.update((r.get('ticker'), r.get('driver_id')) for r in payload.get('company_research_coverage', []) if isinstance(r, dict) and r.get('reason'))
        for key in sorted(company_targets - covered):
            company_errors.append('COMPANY_RESEARCH_NOT_RETURNED:' + str(key))

    final_results = []
    for driver_id in target_ids:
        if driver_id in supplied:
            final_results.append(supplied[driver_id])
        else:
            status = "PARTIAL_FAIL_CLOSED" if status == "PASS" else status
            final_results.append(_unknown(driver_id, run_id, "Autonomous research output missing or failed deterministic validation."))

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
        "company_research_coverage": (payload.get("company_research_coverage", []) + company_invalid_coverage) if status == "PASS" else [],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"v3 research ingest: {status}; valid={len(supplied)}/{len(target_ids)} company_opportunities={len(company_opportunities)} company_errors={company_errors}")
    if errors:
        for err in errors[:8]:
            print(f"research ingest diagnostic: {err}")


if __name__ == "__main__":
    main()
