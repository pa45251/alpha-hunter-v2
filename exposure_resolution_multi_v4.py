from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

OUT = Path("output")
RAW = OUT / "research_result_v3.raw.txt"
CACHE = OUT / "exposure_resolution_v3.json"
HANDOFF = Path("/tmp/research_handoff.json")
CONTRACT = "ALPHA_HUNTER_V3_EXPOSURE_RESOLUTION_CACHE"
SLOW_EXPOSURE_MAX_AGE_DAYS = 365


def _taxonomy() -> dict[str, dict]:
    frame = pd.read_csv("config/causal_driver_taxonomy.csv")
    enabled = pd.to_numeric(frame.get("enabled"), errors="coerce").fillna(0).eq(1)
    return {
        str(row.get("driver_id")): row
        for row in frame[enabled].to_dict("records")
        if str(row.get("driver_id") or "").strip()
    }


def _existing(cutoff: pd.Timestamp, taxonomy: dict[str, dict]) -> dict[tuple[str, str], dict]:
    if not CACHE.exists():
        return {}
    try:
        payload = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if payload.get("contract") != CONTRACT or payload.get("status") != "PASS":
        return {}
    kept = {}
    for row in payload.get("resolutions") or []:
        if not isinstance(row, dict) or row.get("revoked") is True:
            continue
        ticker = str(row.get("ticker") or "")
        driver = str(row.get("resolved_driver_id") or "")
        expires = pd.to_datetime(row.get("valid_until_utc"), utc=True, errors="coerce")
        if pd.isna(expires):
            stamped = pd.to_datetime(row.get("validated_at_utc"), utc=True, errors="coerce")
            if pd.isna(stamped):
                continue
            expires = stamped + timedelta(days=120)
        if ticker and driver in taxonomy and cutoff <= expires and row.get("source_urls"):
            kept[(ticker, driver)] = row
    return kept


def _valid_company_evidence(item: dict, ticker: str, cutoff: pd.Timestamp, allowed: set[str]) -> bool:
    if not isinstance(item, dict) or str(item.get("ticker") or "") != ticker:
        return False
    if str(item.get("source_url") or "") not in allowed:
        return False
    if not str(item.get("claim") or "").strip() or not str(item.get("source_title") or "").strip():
        return False
    published = pd.to_datetime(item.get("published_at"), utc=True, errors="coerce")
    available = pd.to_datetime(item.get("available_at"), utc=True, errors="coerce")
    if pd.isna(published) or pd.isna(available):
        return False
    return bool(published <= available <= cutoff and 0 <= (cutoff - available).days <= SLOW_EXPOSURE_MAX_AGE_DAYS)


def resolve() -> dict:
    if not RAW.exists() or not HANDOFF.exists():
        return {"accepted": 0, "retained": 0, "status": "SKIPPED_NO_EPHEMERAL_TRANSPORT"}

    validated = json.loads((OUT / "research_result_v3.json").read_text(encoding="utf-8"))
    run_id = str(validated.get("research_run_id") or "")
    cutoff_text = str(validated.get("validated_at_utc") or "")
    cutoff = pd.to_datetime(cutoff_text, utc=True, errors="coerce")
    if validated.get("status") not in {"PASS", "PARTIAL_FAIL_CLOSED"} or not run_id or pd.isna(cutoff):
        raise RuntimeError("EXPOSURE_RESOLUTION_REQUIRES_VALIDATED_RESEARCH")

    from research_ingest_v3 import _extract_json, _prefetch_allowlists
    raw = _extract_json(RAW.read_text(encoding="utf-8"))
    handoff = json.loads(HANDOFF.read_text(encoding="utf-8"))
    if str(raw.get("research_run_id") or "") != run_id or str(handoff.get("run_id") or "") != run_id:
        raise RuntimeError("EXPOSURE_RESOLUTION_RUN_MISMATCH")
    _driver_allow, company_allow = _prefetch_allowlists(run_id)

    taxonomy = _taxonomy()
    allowed_ids = {
        str(row.get("driver_id") or "")
        for row in handoff.get("allowed_driver_taxonomy") or []
        if isinstance(row, dict)
    }.intersection(taxonomy)
    nominated = {
        (str(row.get("ticker") or ""), str(row.get("driver_id") or ""))
        for row in handoff.get("company_research_targets") or []
        if isinstance(row, dict)
    }
    proposals = [row for row in raw.get("exposure_resolutions") or [] if isinstance(row, dict)]
    pair_counts: dict[tuple[str, str], int] = {}
    for row in proposals:
        key = (str(row.get("ticker") or ""), str(row.get("resolved_driver_id") or ""))
        pair_counts[key] = pair_counts.get(key, 0) + 1

    cache = _existing(cutoff, taxonomy)
    accepted = 0
    for row in proposals:
        ticker = str(row.get("ticker") or "")
        driver = str(row.get("resolved_driver_id") or "")
        pair = (ticker, driver)
        if pair_counts.get(pair) != 1:
            continue
        if (ticker, "UNMAPPED_OPPORTUNITY") not in nominated:
            continue
        if str(row.get("nominated_driver_id") or "") != "UNMAPPED_OPPORTUNITY":
            continue
        if str(row.get("research_run_id") or "") != run_id or driver not in allowed_ids:
            continue
        mechanism = str(row.get("mechanism") or "").strip()
        evidence = row.get("company_evidence") or []
        allowed_urls = company_allow.get((ticker, "UNMAPPED_OPPORTUNITY"), set())
        if not mechanism or not isinstance(evidence, list) or not evidence:
            continue
        if not all(_valid_company_evidence(item, ticker, cutoff, allowed_urls) for item in evidence):
            continue
        import os
        transport = json.loads(Path(os.getenv('ALPHA_HUNTER_RESEARCH_TRANSPORT_PATH', '/tmp/research_prefetch_v3.json')).read_text())
        if transport.get('document_contract') == 'EXACT_COMPANY_DOCUMENT_V1':
            from company_source_documents import verify_document_claim
            documents = {s['source_url']: s for t in transport.get('company_targets', [])
                         if t.get('ticker') == ticker and t.get('driver_id') == 'UNMAPPED_OPPORTUNITY'
                         for s in t.get('candidate_sources', [])}
            try:
                for item in evidence:
                    verify_document_claim(item, documents, specific=True)
            except ValueError:
                continue
        available = [pd.to_datetime(item.get("available_at"), utc=True, errors="coerce") for item in evidence]
        available = [x for x in available if not pd.isna(x)]
        published = [pd.to_datetime(item.get("published_at"), utc=True, errors="coerce") for item in evidence]
        published = [x for x in published if not pd.isna(x)]
        if not available:
            continue
        source_available = max(available)
        meta = taxonomy[driver]
        cache[pair] = {
            "ticker": ticker,
            "resolved_driver_id": driver,
            "driver_label": str(meta.get("driver_label") or ""),
            "global_theme": str(meta.get("global_theme") or ""),
            "mechanism": mechanism,
            "source_urls": sorted({str(item.get("source_url")) for item in evidence}),
            "source_published_at": max(published).isoformat() if published else None,
            "source_available_at": source_available.isoformat(),
            "validated_at_utc": cutoff_text,
            "valid_until_utc": (source_available + timedelta(days=SLOW_EXPOSURE_MAX_AGE_DAYS)).isoformat(),
            "origin_research_run_id": run_id,
            "mapping_status": "PROVISIONAL_SOURCE_BACKED",
            "revoked": False,
        }
        accepted += 1

    CACHE.write_text(json.dumps({
        "contract": CONTRACT,
        "status": "PASS",
        "updated_at_utc": cutoff_text,
        "resolutions": sorted(cache.values(), key=lambda x: (str(x.get("ticker")), str(x.get("resolved_driver_id")))),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"accepted": accepted, "retained": len(cache), "status": "PASS"}


def main() -> None:
    result = resolve()
    print(f"Exposure resolution {result['status']}: accepted={result['accepted']} retained={result['retained']}")


if __name__ == "__main__":
    main()
