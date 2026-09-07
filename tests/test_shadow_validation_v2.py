from datetime import datetime, timezone

import pandas as pd

from shadow_validation_v2 import evaluate_shadow_audit_v2


def _prices():
    idx = pd.to_datetime(["2026-09-04", "2026-09-07"])
    return pd.DataFrame({"Open": [100.0, 102.0], "Close": [101.0, 104.0]}, index=idx)


def _audit():
    return pd.DataFrame([{
        "audit_at_utc": "2026-09-03T14:00:00+00:00",
        "run_id": "R1",
        "ticker": "2317.TW",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "candidate_action": "WATCH_ENTRY",
        "portfolio_action": "BUY_STOCK",
    }])


def loader(ticker, start, end):
    return _prices()


def test_future_bar_present_in_loader_cannot_mature_two_session_outcome():
    # Sunday 9/6: provider may already expose a labelled 9/7 row in a synthetic/test feed.
    # The validator must not use it.
    now = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
    out = evaluate_shadow_audit_v2(_audit(), loader, horizons=(2,), now_utc=now)
    assert out.empty


def test_current_taiwan_daily_bar_before_close_is_not_mature():
    # Monday 9/7 12:00 Taipei = 04:00 UTC, before the 13:35 closed-bar cutoff.
    now = datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc)
    out = evaluate_shadow_audit_v2(_audit(), loader, horizons=(2,), now_utc=now)
    assert out.empty


def test_outcome_matures_only_after_taiwan_session_close():
    # Monday 9/7 14:00 Taipei = 06:00 UTC, after the safety cutoff.
    now = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)
    out = evaluate_shadow_audit_v2(_audit(), loader, horizons=(2,), now_utc=now)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["exit_date"] == "2026-09-07"
    assert bool(row["future_data_cutoff_enforced"])
