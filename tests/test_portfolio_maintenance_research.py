from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from portfolio_maintenance_research import ingest, private_board_overlay


def _evidence(url: str = "https://example.com/source") -> dict:
    return {
        "claim": "Current source-backed evidence.",
        "source_title": "Source",
        "source_url": url,
        "published_at": "2026-09-06T00:00:00+00:00",
        "evidence_type": "FUNDAMENTAL",
    }


def _result(driver: str, state: str, sources: list[dict]) -> dict:
    return {
        "driver_id": driver,
        "state": state,
        "confidence": 0.8,
        "primary_cause": "Current economic evidence.",
        "industry_scope": "INDUSTRY_WIDE",
        "supporting_evidence": sources if state == "ACTIVE" else [],
        "counter_evidence": sources if state == "INACTIVE" else [],
        "source_count": len({x["source_url"] for x in sources}),
        "event_date": None,
        "source_dates": [],
        "researched_at_utc": "2026-09-06T01:00:00+00:00",
        "research_run_id": "RUN1",
    }


def test_maintenance_ingest_requires_sources_for_inactive(tmp_path: Path):
    handoff = tmp_path / "handoff.json"
    raw = tmp_path / "raw.txt"
    out = tmp_path / "validated.json"
    handoff.write_text(json.dumps({
        "research_run_id": "RUN1",
        "research_targets": [{"driver_id": "D1"}],
        "target_truncated_count": 0,
    }), encoding="utf-8")
    raw.write_text(json.dumps({"research_run_id": "RUN1", "results": [_result("D1", "INACTIVE", [])]}), encoding="utf-8")
    payload = ingest(handoff, raw, out)
    assert payload["status"] == "PARTIAL_FAIL_CLOSED"
    assert payload["results"][0]["state"] == "UNKNOWN"


def test_private_overlay_never_changes_public_board_and_adapts_states(tmp_path: Path):
    p = tmp_path / "maintenance.json"
    p.write_text(json.dumps({
        "contract": "ALPHA_HUNTER_V3_VALIDATED_PORTFOLIO_MAINTENANCE",
        "status": "PASS",
        "research_run_id": "RUN1",
        "target_count": 2,
        "validated_count": 2,
        "target_truncated_count": 0,
        "results": [_result("D_ACTIVE", "ACTIVE", [_evidence()]), _result("D_INACTIVE", "INACTIVE", [_evidence("https://example.com/other")])],
    }), encoding="utf-8")
    public = pd.DataFrame([{"ticker": "2330.TW", "driver_id": "OTHER", "dynamic_driver_state": "UNRESOLVED"}])
    private, meta = private_board_overlay(public, "RUN1", p)
    assert len(public) == 1
    assert "_private_maintenance_row" not in public.columns
    assert len(private) == 3
    active = private[private["driver_id"].eq("D_ACTIVE")].iloc[0]
    inactive = private[private["driver_id"].eq("D_INACTIVE")].iloc[0]
    assert active["dynamic_driver_state"] == "ACTIVE_RESEARCH_VALIDATED"
    assert active["reaction_state"] == "MAINTENANCE_ACTIVE"
    assert inactive["reaction_state"] == "BROKEN"
    assert meta["maintenance_private_artifact_committed"] is False


def test_mixed_snapshot_fails_closed(tmp_path: Path):
    p = tmp_path / "maintenance.json"
    p.write_text(json.dumps({
        "contract": "ALPHA_HUNTER_V3_VALIDATED_PORTFOLIO_MAINTENANCE",
        "status": "PASS",
        "research_run_id": "OLD",
        "target_count": 1,
        "validated_count": 1,
        "results": [_result("D1", "ACTIVE", [_evidence()])],
    }), encoding="utf-8")
    board = pd.DataFrame([{"ticker": "X", "driver_id": "D0"}])
    private, meta = private_board_overlay(board, "NEW", p)
    assert len(private) == len(board)
    assert meta["maintenance_lane_status"] == "MIXED_OR_INVALID_SNAPSHOT"
