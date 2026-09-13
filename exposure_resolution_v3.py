from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

OUT = Path("output")
RAW = OUT / "research_result_v3.raw.txt"
CACHE = OUT / "exposure_resolution_v3.json"
HANDOFF = Path("/tmp/research_handoff.json")
CONTRACT = "ALPHA_HUNTER_V3_EXPOSURE_RESOLUTION_CACHE"
MAX_AGE_DAYS = 120


def enabled_taxonomy() -> dict[str, dict]:
    frame = pd.read_csv("config/causal_driver_taxonomy.csv")
    enabled = pd.to_numeric(frame.get("enabled"), errors="coerce").fillna(0).eq(1)
    result = {}
    for row in frame[enabled].to_dict("records"):
        driver_id = str(row.get("driver_id") or "").strip()
        if driver_id:
            result[driver_id] = row
    return result


def valid_evidence(item: dict, ticker: str, cutoff: pd.Timestamp, allowed_urls: set[str]) -> bool:
    if not isinstance(item, dict) or str(item.get("ticker") or "") != ticker:
        return False
    url = str(item.get("source_url") or "").strip()
    if not url or url not in allowed_urls:
        return False
    if not str(item.get("claim") or "").strip() or not str(item.get("source_title") or "").strip():
        return False
    if str(item.get("evidence_type") or "") not in {"COMPANY_PRIMARY", "PRIMARY_OFFICIAL", "HIGH_QUALITY_REPORTING"}:
        return False
    published = pd.to_datetime(item.get("published_at"), utc=True, errors="coerce")
    available = pd.to_datetime(item.get("available_at"), utc=True, errors="coerce")
    if pd.isna(published) or pd.isna(available):
        return False
    return bool(published <= available <= cutoff and 0 <= (cutoff - published).days <= MAX_AGE_DAYS)


def existing_cache(cutoff: pd.Timestamp, taxonomy: dict[str, dict]) -> dict[str, dict]:
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
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "")
        resolved = str(row.get("resolved_driver_id") or "")
        stamped = pd.to_datetime(row.get("validated_at_utc"), utc=True, errors="coerce")
        urls = row.get("source_urls") or []
        if ticker and resolved in taxonomy and not pd.isna(stamped) and isinstance(urls, list) and urls:
            if 0 <= (cutoff - stamped).days <= MAX_AGE_DAYS:
                kept[ticker] = row
    return kept


def main() -> None:
    # Exposure resolution is an optional CAN-stage enrichment. If the ephemeral raw
    # research transport is absent (e.g. unit tests or a later deterministic refresh),
    # do not weaken or block the canonical activation path; simply leave exposure UNKNOWN.
    if not RAW.exists() or not HANDOFF.exists():
        print("Exposure resolution skipped: ephemeral research transport unavailable")
        return

    validated = json.loads((OUT / "research_result_v3.json").read_text(encoding="utf-8"))
    run_id = str(validated.get("research_run_id") or "")
    cutoff_text = str(validated.get("validated_at_utc") or "")
    cutoff = pd.to_datetime(cutoff_text, utc=True, errors="coerce")
    if validated.get("status") != "PASS" or not run_id or pd.isna(cutoff):
        raise RuntimeError("EXPOSURE_RESOLUTION_REQUIRES_VALIDATED_RESEARCH")

    from research_ingest_v3 import _extract_json, _prefetch_allowlists
    raw = _extract_json(RAW.read_text(encoding="utf-8"))
    handoff = json.loads(HANDOFF.read_text(encoding="utf-8"))
    if str(raw.get("research_run_id") or "") != run_id or str(handoff.get("run_id") or "") != run_id:
        raise RuntimeError("EXPOSURE_RESOLUTION_RUN_MISMATCH")
    _driver_allow, company_allow = _prefetch_allowlists(run_id)

    taxonomy = enabled_taxonomy()
    handoff_ids = {
        str(row.get("driver_id") or "")
        for row in (handoff.get("allowed_driver_taxonomy") or [])
        if isinstance(row, dict)
    }
    allowed_ids = set(taxonomy).intersection(handoff_ids)
    nominated = {
        (str(row.get("ticker") or ""), str(row.get("driver_id") or ""))
        for row in (handoff.get("company_research_targets") or [])
        if isinstance(row, dict)
    }
    proposals = [row for row in (raw.get("exposure_resolutions") or []) if isinstance(row, dict)]
    counts = {}
    for row in proposals:
        ticker = str(row.get("ticker") or "")
        counts[ticker] = counts.get(ticker, 0) + 1

    cache = existing_cache(cutoff, taxonomy)
    accepted = 0
    for row in proposals:
        ticker = str(row.get("ticker") or "")
        resolved = str(row.get("resolved_driver_id") or "")
        mechanism = str(row.get("mechanism") or "").strip()
        evidence = row.get("company_evidence") or []
        if counts.get(ticker) != 1:
            print(f"Exposure unresolved {ticker}: ambiguous proposals")
            continue
        if (ticker, "UNMAPPED_OPPORTUNITY") not in nominated:
            print(f"Exposure unresolved {ticker}: not nominated as UNMAPPED")
            continue
        if str(row.get("nominated_driver_id") or "") != "UNMAPPED_OPPORTUNITY":
            print(f"Exposure unresolved {ticker}: nominated driver mismatch")
            continue
        if str(row.get("research_run_id") or "") != run_id or resolved not in allowed_ids:
            print(f"Exposure unresolved {ticker}: invalid existing driver {resolved}")
            continue
        allowed_urls = company_allow.get((ticker, "UNMAPPED_OPPORTUNITY"), set())
        if not mechanism or not isinstance(evidence, list) or not evidence:
            print(f"Exposure unresolved {ticker}: missing mechanism/evidence")
            continue
        if not all(valid_evidence(item, ticker, cutoff, allowed_urls) for item in evidence):
            print(f"Exposure unresolved {ticker}: evidence validation failed")
            continue
        urls = sorted({str(item.get("source_url")) for item in evidence})
        meta = taxonomy[resolved]
        cache[ticker] = {
            "ticker": ticker,
            "resolved_driver_id": resolved,
            "driver_label": str(meta.get("driver_label") or ""),
            "global_theme": str(meta.get("global_theme") or ""),
            "mechanism": mechanism,
            "source_urls": urls,
            "source_count": len(urls),
            "validated_at_utc": cutoff_text,
            "research_run_id": run_id,
            "mapping_status": "PROVISIONAL_SOURCE_BACKED",
        }
        accepted += 1

    CACHE.write_text(json.dumps({
        "contract": CONTRACT,
        "status": "PASS",
        "updated_at_utc": cutoff_text,
        "resolutions": sorted(cache.values(), key=lambda row: str(row.get("ticker"))),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exposure resolution PASS: accepted={accepted} retained={len(cache)}")


if __name__ == "__main__":
    main()
