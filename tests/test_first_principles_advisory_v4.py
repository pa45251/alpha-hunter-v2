from __future__ import annotations

import json
from datetime import datetime, timezone

from opportunity_advisory import MAX_PLANNED_POSITION_FRACTION, rank_opportunities
import research_handoff


def test_same_ticker_different_theses_are_not_collapsed():
    rows = [
        {"ticker": "9999.TW", "driver_id": "DRIVER_A", "thesis_id": "A", "action": "WAIT", "evidence": [], "price_ok": False},
        {"ticker": "9999.TW", "driver_id": "UNMAPPED_OPPORTUNITY", "thesis_id": "LOCAL_EVENT", "action": "WAIT", "evidence": [], "price_ok": False},
    ]
    result = rank_opportunities(rows)
    assert len(result) == 2
    assert {x["thesis_id"] for x in result} == {"A", "LOCAL_EVENT"}


def test_planned_position_constant_is_a_ceiling_not_risk_budget():
    assert MAX_PLANNED_POSITION_FRACTION == 0.35


def test_multi_exposure_cache_expands_one_unmapped_nomination(monkeypatch, tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    cache = {
        "contract": "ALPHA_HUNTER_V3_EXPOSURE_RESOLUTION_CACHE",
        "status": "PASS",
        "resolutions": [
            {
                "ticker": "9999.TW",
                "resolved_driver_id": "DRIVER_A",
                "mechanism": "Product A exposure",
                "source_urls": ["https://example.com/a"],
                "source_available_at": "2026-09-01T00:00:00+00:00",
                "valid_until_utc": "2027-09-01T00:00:00+00:00",
                "origin_research_run_id": "old-a",
            },
            {
                "ticker": "9999.TW",
                "resolved_driver_id": "DRIVER_B",
                "mechanism": "Product B exposure",
                "source_urls": ["https://example.com/b"],
                "source_available_at": "2026-09-02T00:00:00+00:00",
                "valid_until_utc": "2027-09-02T00:00:00+00:00",
                "origin_research_run_id": "old-b",
            },
        ],
    }
    (out / "exposure_resolution_v3.json").write_text(json.dumps(cache), encoding="utf-8")
    monkeypatch.setattr(research_handoff, "_driver_taxonomy", lambda: {
        "DRIVER_A": {"driver_id": "DRIVER_A", "driver_label": "A", "global_theme": "Theme A", "driver_scope": "GLOBAL"},
        "DRIVER_B": {"driver_id": "DRIVER_B", "driver_label": "B", "global_theme": "Theme B", "driver_scope": "GLOBAL"},
    })
    rows = research_handoff._apply_exposure_cache(
        [{"ticker": "9999.TW", "driver_id": "UNMAPPED_OPPORTUNITY"}],
        out,
        datetime(2026, 9, 13, tzinfo=timezone.utc),
    )
    assert {x["driver_id"] for x in rows} == {"DRIVER_A", "DRIVER_B"}
    assert {x["exposure_origin_research_run_id"] for x in rows} == {"old-a", "old-b"}


def test_expired_exposure_is_not_refreshed_by_cache_read(monkeypatch, tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    cache = {
        "contract": "ALPHA_HUNTER_V3_EXPOSURE_RESOLUTION_CACHE",
        "status": "PASS",
        "resolutions": [{
            "ticker": "9999.TW",
            "resolved_driver_id": "DRIVER_A",
            "mechanism": "Old exposure",
            "source_urls": ["https://example.com/a"],
            "source_available_at": "2025-01-01T00:00:00+00:00",
            "valid_until_utc": "2026-01-01T00:00:00+00:00",
            "origin_research_run_id": "old",
        }],
    }
    (out / "exposure_resolution_v3.json").write_text(json.dumps(cache), encoding="utf-8")
    monkeypatch.setattr(research_handoff, "_driver_taxonomy", lambda: {
        "DRIVER_A": {"driver_id": "DRIVER_A", "driver_label": "A", "global_theme": "Theme A", "driver_scope": "GLOBAL"},
    })
    rows = research_handoff._apply_exposure_cache(
        [{"ticker": "9999.TW", "driver_id": "UNMAPPED_OPPORTUNITY"}],
        out,
        datetime(2026, 9, 13, tzinfo=timezone.utc),
    )
    assert rows == [{"ticker": "9999.TW", "driver_id": "UNMAPPED_OPPORTUNITY"}]
