import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from automation_guard_v4 import canonical_snapshot_is_fresh_for_today, manual_research_inputs_are_current, triggering_run_produced_snapshot


TAIPEI = ZoneInfo("Asia/Taipei")


def test_today_pass_snapshot_is_fresh():
    manifest = {
        "status": "PASS",
        "generated_at_taipei": "2026-09-09T06:35:00+08:00",
        "generated_at_utc": "2026-09-08T22:35:00+00:00",
        "pipeline_checks": {"a": True, "b": True},
    }
    now = datetime(2026, 9, 9, 6, 50, tzinfo=TAIPEI)
    assert canonical_snapshot_is_fresh_for_today(manifest, now) == (True, "FRESH_TODAY")


def test_previous_day_snapshot_is_not_fresh():
    manifest = {
        "status": "PASS",
        "generated_at_taipei": "2026-09-08T06:35:00+08:00",
        "pipeline_checks": {"a": True},
    }
    now = datetime(2026, 9, 9, 6, 20, tzinfo=TAIPEI)
    fresh, reason = canonical_snapshot_is_fresh_for_today(manifest, now)
    assert fresh is False
    assert reason == "MANIFEST_NOT_TODAY_TAIPEI"


def test_failed_pipeline_check_is_not_fresh():
    manifest = {
        "status": "PASS",
        "generated_at_taipei": "2026-09-09T06:35:00+08:00",
        "pipeline_checks": {"a": True, "b": False},
    }
    now = datetime(2026, 9, 9, 6, 40, tzinfo=TAIPEI)
    fresh, reason = canonical_snapshot_is_fresh_for_today(manifest, now)
    assert fresh is False
    assert reason == "PIPELINE_CHECKS_NOT_ALL_TRUE"


def test_trigger_window_accepts_snapshot_created_by_run():
    manifest = {
        "status": "PASS",
        "generated_at_utc": "2026-09-08T22:28:00+00:00",
    }
    assert triggering_run_produced_snapshot(manifest, "2026-09-08T22:20:00Z") == (
        True,
        "SNAPSHOT_FROM_TRIGGER_WINDOW",
    )


def test_trigger_window_rejects_old_snapshot_from_backup_noop():
    manifest = {
        "status": "PASS",
        "generated_at_utc": "2026-09-08T22:28:00+00:00",
    }
    assert triggering_run_produced_snapshot(manifest, "2026-09-08T22:50:00Z") == (
        False,
        "SNAPSHOT_PREDATES_TRIGGER",
    )


def test_manual_research_input_hashes_detect_config_change(tmp_path):
    config = tmp_path / "config"
    output = tmp_path / "output"
    config.mkdir()
    output.mkdir()
    structural = config / "structural_exposure_graph.csv"
    peers = config / "manual_global_peers.csv"
    structural.write_text("driver_id\nA\n", encoding="utf-8")
    peers.write_text("driver_id,ticker\nA,X\n", encoding="utf-8")

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    handoff = {
        "mapping_source_of_truth": "config/structural_exposure_graph.csv",
        "mapping_input_sha256": {
            "config/structural_exposure_graph.csv": sha(structural),
        },
        "peer_input_sha256": {
            "config/manual_global_peers.csv": sha(peers),
        },
    }
    path = output / "manual_research_handoff.json"
    path.write_text(json.dumps(handoff), encoding="utf-8")
    assert manual_research_inputs_are_current(path, tmp_path) == (True, "MANUAL_INPUTS_CURRENT")

    peers.write_text("driver_id,ticker\nA,Y\n", encoding="utf-8")
    fresh, reason = manual_research_inputs_are_current(path, tmp_path)
    assert fresh is False
    assert reason == "MANUAL_INPUT_CHANGED:config/manual_global_peers.csv"


def test_manual_research_input_hashes_require_canonical_mapping_source(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    path = output / "manual_research_handoff.json"
    path.write_text(json.dumps({
        "mapping_source_of_truth": "config/manual_industry_map.csv",
        "mapping_input_sha256": {"config/manual_industry_map.csv": "x"},
        "peer_input_sha256": {"config/manual_global_peers.csv": "y"},
    }), encoding="utf-8")
    assert manual_research_inputs_are_current(path, tmp_path) == (
        False, "MANUAL_MAPPING_SOURCE_NOT_CANONICAL"
    )
