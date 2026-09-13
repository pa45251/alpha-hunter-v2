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
