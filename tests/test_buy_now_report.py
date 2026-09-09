import pandas as pd

from buy_now_report import build_buy_now_report


def _advisory(**overrides):
    row = {
        "run_id": "r1",
        "ticker": "3231.TW",
        "name": "緯創",
        "global_theme": "AI_Server",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "preferred_exposure": "STOCK",
        "advisory_action": "BUY_BIAS_STOCK",
        "advisory_confidence": "HIGH",
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED",
        "semantic_breadth_state": "HEALTHY",
        "reaction_state": "CONFIRMING",
        "research_priority_score": 0.9,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _entries(**overrides):
    p = {
        "ticker": "3231.TW",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "entry_style": "FRESH_BREAKOUT",
        "entry_structure_valid": True,
        "global_confirmation": {"status": "PASS"},
        "entry_status": "CONFIRMED_NEXT_SESSION_CONDITIONAL",
        "risk_v2_pass": True,
        "trigger_price": 120,
        "buy_zone_low": 120,
        "buy_zone_high": 123,
        "invalidation_price": 114,
    }
    p.update(overrides)
    return {"status": "READY", "source_run_id": "r1", "all_plans": [p]}


def _regime(label="NORMAL"):
    return {"status": "READY", "regime": label}


def test_only_fully_confirmed_candidate_surfaces_buy_now():
    out = build_buy_now_report(_advisory(), _regime(), _entries())
    assert out["status"] == "BUY_NOW"
    assert len(out["recommendations"]) == 1
    assert out["recommendations"][0]["ticker"] == "3231.TW"
    assert "LIVE EXECUTABLE QUOTE" in out["recommendations"][0]["execution_condition"]


def test_broken_theme_never_surfaces_as_buy_now():
    out = build_buy_now_report(_advisory(semantic_breadth_state="BROKEN"), _regime(), _entries())
    assert out["status"] == "NO_BUY_NOW"
    assert out["recommendations"] == []


def test_watch_or_preconfirmation_is_suppressed_not_reported_as_noise():
    out = build_buy_now_report(_advisory(reaction_state="PRE_CONFIRMATION", advisory_confidence="MEDIUM"), _regime(), _entries())
    assert out["status"] == "NO_BUY_NOW"
    assert out["recommendations"] == []
    assert "near-misses are intentionally suppressed" in out["reason"]


def test_invalid_exact_entry_blocks_buy_now():
    out = build_buy_now_report(_advisory(), _regime(), _entries(entry_structure_valid=False))
    assert out["status"] == "NO_BUY_NOW"


def test_defensive_regime_blocks_new_buy():
    out = build_buy_now_report(_advisory(), _regime("DEFENSIVE"), _entries())
    assert out["status"] == "NO_BUY_NOW"


def test_mixed_snapshot_fails_closed():
    entries = _entries()
    entries["source_run_id"] = "stale"
    out = build_buy_now_report(_advisory(), _regime(), entries)
    assert out["status"] == "DATA_UNAVAILABLE"
