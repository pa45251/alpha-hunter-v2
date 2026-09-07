from portfolio_allocation_v2 import build_portfolio_allocation_v2


def _policy():
    return {
        "rotation": {
            "min_edge_spread": 0.18,
            "strong_edge_spread": 0.35,
            "max_source_trim_pct": {"RISK_ON": 50, "CRISIS": 0, "UNKNOWN": 0},
            "redeploy_pct_of_trim": {"RISK_ON": 100, "CRISIS": 0, "UNKNOWN": 0},
        }
    }


def _positions():
    return {"positions": [
        {"alias": "標的D", "advisory_action": "REVIEW_HOLD", "signal_score": 0.40, "confidence": "MEDIUM", "signal_state": "MIXED"}
    ]}


def _candidates():
    return {"top_advisories": [
        {
            "ticker": "2317.TW", "name": "鴻海", "driver_id": "AI_SERVER_SHIPMENTS",
            "preferred_exposure": "STOCK", "advisory_action": "BUY_BIAS_STOCK",
            "advisory_confidence": "HIGH", "reaction_state": "CONFIRMING",
            "provenance_status": "SOURCE_BACKED", "research_priority_score": 0.8,
            "advisory_missing_evidence": "",
        }
    ]}


def _regime(label="RISK_ON"):
    return {"status": "READY", "regime": label, "risk_score": 10, "target_cash_pct": 0}


def _entries(plan):
    return {"status": "READY", "all_plans": [plan]}


def _plan(**overrides):
    p = {
        "ticker": "2317.TW", "entry_style": "FRESH_BREAKOUT",
        "entry_structure_valid": True,
        "global_confirmation": {"status": "PASS"},
        "current_action": "PREPARE",
        "entry_status": "WAITING_FOR_TRIGGER",
        "trigger_price": 200, "buy_zone_low": 200, "buy_zone_high": 205,
        "invalidation_price": 190,
    }
    p.update(overrides)
    return p


def test_rotation_requires_canonical_entry_plan():
    p = build_portfolio_allocation_v2(_policy(), _positions(), _candidates(), _regime(), {"status": "READY", "all_plans": []})
    assert p["rotations"] == []
    assert p["best_research_opportunity"]["ticker"] == "2317.TW"
    assert p["best_entry_plan_destination"] is None


def test_waiting_entry_can_only_prepare_rotation_and_trim_now_zero():
    p = build_portfolio_allocation_v2(_policy(), _positions(), _candidates(), _regime(), _entries(_plan()))
    assert len(p["rotations"]) == 1
    r = p["rotations"][0]
    assert r["rotation_action"].startswith("PREPARE_ROTATION")
    assert r["suggested_source_trim_pct_now"] == 0
    assert r["trigger_price"] == 200


def test_confirmed_eod_plan_still_needs_live_quote_before_source_sale():
    p = build_portfolio_allocation_v2(
        _policy(), _positions(), _candidates(), _regime(),
        _entries(_plan(entry_status="CONFIRMED_NEXT_SESSION_CONDITIONAL")),
    )
    r = p["rotations"][0]
    assert r["rotation_action"] == "PREPARE_ROTATION_TRIGGERED"
    assert r["suggested_source_trim_pct_now"] == 0
    assert "LIVE_QUOTE" in r["entry_trigger_required"]


def test_alignment_failure_blocks_rotation():
    bad = _plan(global_confirmation={"status": "FAIL"})
    p = build_portfolio_allocation_v2(_policy(), _positions(), _candidates(), _regime(), _entries(bad))
    assert p["rotations"] == []


def test_crisis_regime_blocks_risk_on_rotation():
    p = build_portfolio_allocation_v2(_policy(), _positions(), _candidates(), _regime("CRISIS"), _entries(_plan()))
    assert p["rotations"] == []
