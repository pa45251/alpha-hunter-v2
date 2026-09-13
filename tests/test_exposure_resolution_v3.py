import json
from pathlib import Path

import pandas as pd

import exposure_resolution_v3 as er
import research_ingest_v3


def _setup(monkeypatch, tmp_path, source_url="https://issuer.example/facts"):
    out = tmp_path / "output"
    out.mkdir()
    raw = out / "research_result_v3.raw.txt"
    cache = out / "exposure_resolution_v3.json"
    handoff = tmp_path / "handoff.json"
    validated_at = "2026-09-13T03:00:00+00:00"
    (out / "research_result_v3.json").write_text(json.dumps({
        "contract": "ALPHA_HUNTER_V3_VALIDATED_RESEARCH",
        "status": "PASS",
        "research_run_id": "run-1",
        "validated_at_utc": validated_at,
    }), encoding="utf-8")
    raw.write_text(json.dumps({
        "contract": "ALPHA_HUNTER_V3_AUTONOMOUS_RESEARCH",
        "research_run_id": "run-1",
        "exposure_resolutions": [{
            "ticker": "1234.TW",
            "nominated_driver_id": "UNMAPPED_OPPORTUNITY",
            "resolved_driver_id": "AI_SERVER_SHIPMENTS",
            "research_run_id": "run-1",
            "mechanism": "Server products create direct shipment exposure.",
            "company_evidence": [{
                "ticker": "1234.TW",
                "claim": "Issuer disclosed server shipment exposure.",
                "source_title": "Issuer facts",
                "source_url": source_url,
                "published_at": "2026-09-12T00:00:00+00:00",
                "available_at": "2026-09-12T00:00:00+00:00",
                "evidence_type": "COMPANY_PRIMARY",
            }],
        }],
    }), encoding="utf-8")
    handoff.write_text(json.dumps({
        "run_id": "run-1",
        "allowed_driver_taxonomy": [{"driver_id": "AI_SERVER_SHIPMENTS"}],
        "company_research_targets": [{
            "ticker": "1234.TW",
            "driver_id": "UNMAPPED_OPPORTUNITY",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(er, "OUT", out)
    monkeypatch.setattr(er, "RAW", raw)
    monkeypatch.setattr(er, "CACHE", cache)
    monkeypatch.setattr(er, "HANDOFF", handoff)
    monkeypatch.setattr(er, "enabled_taxonomy", lambda: {
        "AI_SERVER_SHIPMENTS": {
            "driver_id": "AI_SERVER_SHIPMENTS",
            "driver_label": "AI server shipment / ODM cycle",
            "global_theme": "AI_Server",
        }
    })
    return cache


def test_existing_taxonomy_mapping_is_cached(monkeypatch, tmp_path):
    url = "https://issuer.example/facts"
    cache = _setup(monkeypatch, tmp_path, url)
    monkeypatch.setattr(research_ingest_v3, "_prefetch_allowlists", lambda run_id: ({}, {
        ("1234.TW", "UNMAPPED_OPPORTUNITY"): {url}
    }))
    er.main()
    payload = json.loads(cache.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["resolutions"][0]["resolved_driver_id"] == "AI_SERVER_SHIPMENTS"
    assert payload["resolutions"][0]["mapping_status"] == "PROVISIONAL_SOURCE_BACKED"


def test_unprefetched_evidence_stays_unresolved(monkeypatch, tmp_path):
    cache = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(research_ingest_v3, "_prefetch_allowlists", lambda run_id: ({}, {
        ("1234.TW", "UNMAPPED_OPPORTUNITY"): set()
    }))
    er.main()
    payload = json.loads(cache.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["resolutions"] == []


def test_stale_cache_is_not_reused(monkeypatch, tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({
        "contract": er.CONTRACT,
        "status": "PASS",
        "resolutions": [{
            "ticker": "1234.TW",
            "resolved_driver_id": "AI_SERVER_SHIPMENTS",
            "source_urls": ["https://issuer.example/facts"],
            "validated_at_utc": "2025-01-01T00:00:00+00:00",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(er, "CACHE", cache)
    kept = er.existing_cache(pd.Timestamp("2026-09-13T03:00:00Z"), {"AI_SERVER_SHIPMENTS": {}})
    assert kept == {}
