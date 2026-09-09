from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from automation_guard_v4 import canonical_snapshot_is_fresh_for_today, triggering_run_produced_snapshot


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
