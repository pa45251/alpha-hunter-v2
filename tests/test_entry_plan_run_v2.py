import pandas as pd
import pytest

from entry_plan_run_v2 import (
    _assert_plans_use_closed_sessions,
    _clip_histories_to_closed_date,
    build_canonical_plans,
)


def _hist():
    idx = pd.bdate_range("2026-01-02", periods=90)
    close = pd.Series(range(90), index=idx, dtype=float) * 0.1 + 90
    return pd.DataFrame({
        "Open": close - 0.1, "High": close + 0.5, "Low": close - 0.5,
        "Close": close, "Volume": 1_000_000.0,
    }, index=idx)


def _row(driver, priority):
    return {
        "ticker": "2317.TW", "name": "SYN", "driver_id": driver,
        "global_theme": "AI_Server", "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED", "polarity": "POSITIVE",
        "reaction_state": "CONFIRMING", "rs_20d_vs_bench": 0.05,
        "rs_60d_vs_bench": 0.10, "keynes_v2": 0.2,
        "research_priority_score": priority,
    }


def test_entry_plan_uses_alignment_driver_not_highest_other_driver(monkeypatch):
    # Higher research priority belongs to the wrong driver. Canonical entry must still follow alignment driver.
    board = pd.DataFrame([
        _row("WRONG_DRIVER", 0.99),
        _row("AI_SERVER_SHIPMENTS", 0.60),
    ])
    alignment = pd.DataFrame([{
        "ticker": "2317.TW", "name": "SYN", "driver_id": "AI_SERVER_SHIPMENTS",
        "alignment_eligible": True, "alignment_score": 0.8,
        "international_theme": "AI_Server", "breadth_n": 5, "breadth_eligible": True,
        "global_trend_score": 0.8, "international_breadth_score": 0.7,
    }])
    # Risk env intentionally absent: lineage is still visible even though the risk gate fails closed.
    out = build_canonical_plans(board, alignment, {"2317.TW": _hist()})
    assert out.iloc[0]["driver_id"] == "AI_SERVER_SHIPMENTS"
    assert bool(out.iloc[0]["entry_driver_matches_alignment_driver"])


def test_missing_alignment_driver_row_fails_closed():
    board = pd.DataFrame([_row("OTHER", 0.9)])
    alignment = pd.DataFrame([{
        "ticker": "2317.TW", "name": "SYN", "driver_id": "AI_SERVER_SHIPMENTS",
        "alignment_eligible": True, "alignment_score": 0.8,
    }])
    out = build_canonical_plans(board, alignment, {"2317.TW": _hist()})
    assert out.iloc[0]["entry_status"] == "DRIVER_LINEAGE_MISMATCH"
    assert not bool(out.iloc[0]["entry_structure_valid"])


def test_runtime_history_cutoff_excludes_still_forming_daily_bar():
    idx = pd.to_datetime(["2026-09-03", "2026-09-04", "2026-09-07"])
    h = pd.DataFrame({
        "Open": [100, 101, 110], "High": [102, 103, 130], "Low": [99, 100, 109],
        "Close": [101, 102, 125], "Volume": [1_000_000, 1_100_000, 500_000],
    }, index=idx)
    clipped = _clip_histories_to_closed_date({"2317.TW": h}, "2026-09-04")
    assert clipped["2317.TW"].index.max().date().isoformat() == "2026-09-04"
    assert 125 not in clipped["2317.TW"]["Close"].tolist()


def test_plan_newer_than_canonical_closed_session_is_blocked():
    plans = pd.DataFrame([{"ticker": "2317.TW", "price_as_of_utc": "2026-09-07T00:00:00"}])
    with pytest.raises(RuntimeError, match="OPEN_OR_FUTURE_DAILY_BAR_BLOCKED"):
        _assert_plans_use_closed_sessions(plans, "2026-09-04")
