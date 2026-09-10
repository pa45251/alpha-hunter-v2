import pandas as pd

from cio_advisory import build_cio_advisory


def row(**overrides):
    base = {
        "run_id": "r1",
        "global_theme": "AI_Server",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "driver_label": "AI server shipment / ODM cycle",
        "taiwan_code": "3231",
        "ticker": "3231.TW",
        "name": "Wistron",
        "etf_ticker": "BOTZ",
        "stock_vs_etf_state": "STOCK_ALPHA_RESEARCH",
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "NEEDS_SOURCE_BACKFILL",
        "reaction_state": "CONFIRMING",
        "semantic_breadth_state": "HEALTHY",
        "semantic_breadth_n": 6,
        "semantic_positive_rs20_pct": 0.67,
        "semantic_median_rs20": 0.04,
        "polarity": "POSITIVE",
        "linkage_tier": "DIRECT",
        "linkage_confidence": 0.95,
        "research_priority_score": 0.84,
        "candidate_action": "WATCH_RESEARCH",
        "portfolio_action": "WATCH_RESEARCH",
    }
    base.update(overrides)
    return base


def advisory(**overrides):
    out = build_cio_advisory(pd.DataFrame([row(**overrides)]))
    return out.iloc[0]


def test_active_direct_stock_can_have_provisional_bias_without_execution_permission():
    r = advisory()
    assert r["advisory_action"] == "PROVISIONAL_BUY_BIAS_STOCK"
    assert r["advisory_confidence"] == "LOW"
    assert r["preferred_exposure"] == "STOCK_RESEARCH_ONLY"
    assert bool(r["auto_trade_allowed"]) is False
    assert "COMPANY_EDGE_SOURCE_BACKING" in r["advisory_missing_evidence"]


def test_source_backed_confirming_stock_gets_buy_bias():
    r = advisory(provenance_status="SOURCE_BACKED")
    assert r["advisory_action"] == "BUY_BIAS_STOCK"
    assert r["advisory_confidence"] == "HIGH"
    assert r["preferred_exposure"] == "STOCK"


def test_broken_semantic_theme_blocks_otherwise_valid_stock():
    r = advisory(provenance_status="SOURCE_BACKED", semantic_breadth_state="BROKEN")
    assert r["advisory_action"] == "AVOID"
    assert r["preferred_exposure"] == "CASH"
    assert "breadth is broken" in r["advisory_rationale"]


def test_mixed_semantic_theme_does_not_surface_buy_bias():
    r = advisory(provenance_status="SOURCE_BACKED", semantic_breadth_state="MIXED")
    assert r["advisory_action"] == "RESEARCH_FIRST"
    assert "SEMANTIC_THEME_BREADTH_HEALTHY" in r["advisory_missing_evidence"]


def test_etf_core_route_is_not_blocked_by_missing_company_provenance_or_taiwan_breadth():
    r = advisory(
        stock_vs_etf_state="ETF_CORE_PREFERRED",
        provenance_status="NEEDS_SOURCE_BACKFILL",
        semantic_breadth_state="BROKEN",
    )
    assert r["advisory_action"] == "PREFER_ETF"
    assert r["preferred_exposure"] == "ETF"


def test_weak_stock_edge_falls_back_to_etf_instead_of_endless_research():
    r = advisory(stock_vs_etf_state="STOCK_BLOCKED_WEAK_EDGE", provenance_status="NEEDS_SOURCE_BACKFILL")
    assert r["advisory_action"] == "PREFER_ETF"


def test_extended_state_waits_instead_of_chasing():
    r = advisory(provenance_status="SOURCE_BACKED", reaction_state="EXTENDED")
    assert r["advisory_action"] == "WAIT_PULLBACK"
    assert r["preferred_exposure"] == "CASH_UNTIL_ENTRY"


def test_broken_transmission_is_avoid():
    r = advisory(provenance_status="SOURCE_BACKED", reaction_state="BROKEN")
    assert r["advisory_action"] == "AVOID"
    assert r["preferred_exposure"] == "CASH"


def test_unresolved_driver_cannot_be_rescued_by_price_strength():
    r = advisory(dynamic_driver_state="UNRESOLVED", reaction_state="CONFIRMING")
    assert r["advisory_action"] == "RESEARCH_FIRST"
    assert r["advisory_confidence"] == "INSUFFICIENT"
