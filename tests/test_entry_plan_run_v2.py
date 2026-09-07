import pandas as pd

from entry_plan_run_v2 import build_canonical_plans


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
