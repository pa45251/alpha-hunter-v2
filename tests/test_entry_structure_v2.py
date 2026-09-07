import numpy as np
import pandas as pd

from entry_structure_v2 import (
    EntryPolicyV2,
    ENTRY_STYLE_CONTINUATION,
    build_continuation_plan,
    build_fresh_plan,
    build_pullback_plan,
)


def _alignment():
    return {
        "alignment_eligible": True,
        "alignment_score": 0.8,
        "driver_id": "AI_SERVER_SHIPMENTS",
        "international_theme": "AI_Server",
        "breadth_n": 5,
        "breadth_eligible": True,
        "global_trend_score": 0.8,
        "international_breadth_score": 0.7,
    }


def _row(reaction):
    return {
        "ticker": "2317.TW", "name": "SYN", "global_theme": "AI_Server",
        "driver_id": "AI_SERVER_SHIPMENTS", "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED", "polarity": "POSITIVE",
        "reaction_state": reaction, "rs_20d_vs_bench": 0.05,
        "rs_60d_vs_bench": 0.10, "keynes_v2": 0.25,
    }


def _hist(closes, highs=None, lows=None, volumes=None):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    highs = np.asarray(highs if highs is not None else closes + 0.5, dtype=float)
    lows = np.asarray(lows if lows is not None else closes - 0.5, dtype=float)
    opens = closes - 0.1
    volumes = np.asarray(volumes if volumes is not None else np.full(n, 1_000_000.0), dtype=float)
    idx = pd.bdate_range("2026-01-02", periods=n)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes}, index=idx)


def test_fresh_breakout_pivot_excludes_trigger_bar_high():
    closes = np.concatenate([np.linspace(90, 98, 79), [100.0]])
    highs = closes + 0.5
    lows = closes - 0.5
    # Current bar makes a huge high. It must NOT be used to define the pivot it is testing.
    highs[-1] = 120.0
    volumes = np.full(80, 1_000_000.0)
    volumes[-1] = 2_000_000.0
    h = _hist(closes, highs, lows, volumes)
    plan = build_fresh_plan(_row("CONFIRMING"), _alignment(), h, EntryPolicyV2())
    expected_prior_high = float(h.iloc[:-1].tail(20)["High"].max())
    assert plan["reference_pivot"] == expected_prior_high
    assert plan["reference_pivot"] < float(h["High"].iloc[-1])
    assert plan["current_action"] in {"PREPARE", "DONT_CHASE", "WAIT_BREAKOUT"}
    assert plan["current_action"] != "BUY_NOW"


def test_end_of_day_confirmation_never_claims_buy_now_without_live_quote():
    closes = np.concatenate([np.linspace(90, 99, 79), [102.0]])
    h = _hist(closes, volumes=np.concatenate([np.full(79, 1_000_000.0), [2_000_000.0]]))
    plan = build_fresh_plan(_row("CONFIRMING"), _alignment(), h, EntryPolicyV2())
    assert plan["current_action"] != "BUY_NOW"
    if plan["entry_status"] == "CONFIRMED_NEXT_SESSION_CONDITIONAL":
        assert "LIVE_EXECUTABLE_QUOTE_REQUIRED" in plan["why_not_now"]


def test_pullback_support_touch_is_not_an_entry_before_recovery_trigger():
    closes = np.concatenate([
        np.linspace(80, 100, 65),
        [99, 98, 96, 94, 93, 94, 95, 96, 96.5, 96.0, 96.2, 96.4, 96.5, 96.6, 96.7],
    ])
    h = _hist(closes)
    plan = build_pullback_plan(_row("PULLBACK"), _alignment(), h, EntryPolicyV2())
    assert plan["entry_style"] == "PULLBACK_RECOVERY"
    assert plan["current_action"] in {"WAIT_PULLBACK", "PREPARE", "DONT_CHASE", "AVOID"}
    if plan["current_action"] == "WAIT_PULLBACK":
        assert plan["current_price"] < plan["trigger_price"] or "RECOVERY" in plan["why_not_now"]
    assert plan["current_action"] != "BUY_NOW"


def test_straight_persistent_rally_is_not_automatically_a_continuation_base():
    closes = np.linspace(50, 100, 100)
    h = _hist(closes)
    plan = build_continuation_plan(_row("PERSISTENT"), _alignment(), h, EntryPolicyV2())
    assert plan["entry_style"] == ENTRY_STYLE_CONTINUATION
    assert plan["entry_status"] in {"NO_VALID_CONTINUATION_BASE", "WATCHLIST"}
    assert not bool(plan["entry_structure_valid"])
    assert plan["current_action"] != "BUY_NOW"


def test_global_alignment_failure_blocks_price_plan_even_with_good_chart():
    closes = np.concatenate([np.linspace(90, 99, 79), [102.0]])
    h = _hist(closes)
    bad_alignment = _alignment()
    bad_alignment["alignment_eligible"] = False
    plan = build_fresh_plan(_row("CONFIRMING"), bad_alignment, h, EntryPolicyV2())
    assert not bool(plan["entry_structure_valid"])
    assert "GLOBAL_ALIGNMENT_NOT_ELIGIBLE" in plan["blockers"]
