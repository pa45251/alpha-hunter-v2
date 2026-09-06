from pathlib import Path

import pandas as pd

from decision_engine import apply_edge_provenance, build_decision_board


def base_row(**overrides):
    row = {
        "run_id": "r1",
        "global_theme": "AI_Server",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "driver_label": "AI server shipment / ODM cycle",
        "taiwan_code": "2317",
        "ticker": "2317.TW",
        "name": "Foxconn",
        "industry": "Computer",
        "economic_role": "server_odm",
        "linkage_tier": "STRONG",
        "linkage_confidence": 0.88,
        "provenance_status": "NEEDS_SOURCE_BACKFILL",
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "reaction_state": "PRE_CONFIRMATION",
        "previous_reaction_state": "",
        "polarity": "POSITIVE",
        "stock_vs_etf_state": "STOCK_ALPHA_RESEARCH",
        "research_priority_score": 0.8,
    }
    row.update(overrides)
    return row


def test_score_cannot_override_weak_edge():
    board = build_decision_board(pd.DataFrame([base_row(research_priority_score=0.999)]))
    assert board.iloc[0]["candidate_action"] == "WATCH_RESEARCH"
    assert "EDGE_PROVENANCE_NOT_SOURCE_BACKED" in board.iloc[0]["decision_blockers"]


def test_extended_blocks_new_buy_even_when_driver_and_edge_pass():
    board = build_decision_board(pd.DataFrame([base_row(
        provenance_status="SOURCE_BACKED",
        reaction_state="EXTENDED",
    )]))
    assert board.iloc[0]["candidate_action"] == "NO_BUY_EXTENDED"


def test_preconfirmation_waits_for_transition():
    board = build_decision_board(pd.DataFrame([base_row(provenance_status="SOURCE_BACKED")]))
    assert board.iloc[0]["candidate_action"] == "WATCH_ENTRY"
    assert board.iloc[0]["entry_trigger_state"] == "NOT_TRIGGERED"
    assert "WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER" in board.iloc[0]["decision_blockers"]
    assert board.iloc[0]["auto_trade_allowed"] == False


def test_preconfirmation_to_confirming_triggers_stock_entry_but_risk_blocks_trade():
    board = build_decision_board(pd.DataFrame([base_row(
        provenance_status="SOURCE_BACKED",
        previous_reaction_state="PRE_CONFIRMATION",
        reaction_state="CONFIRMING",
    )]))
    assert board.iloc[0]["entry_trigger_state"] == "BREAKOUT_CONFIRMATION_TRIGGER"
    assert board.iloc[0]["candidate_action"] == "ENTRY_TRIGGERED_STOCK_RISK_PENDING"
    assert "PORTFOLIO_RISK_NOT_YET_VALIDATED" in board.iloc[0]["decision_blockers"]
    assert board.iloc[0]["auto_trade_allowed"] == False


def test_high_purity_etf_route_is_preserved():
    board = build_decision_board(pd.DataFrame([base_row(
        provenance_status="SOURCE_BACKED",
        stock_vs_etf_state="ETF_CORE_PREFERRED",
        previous_reaction_state="PRE_CONFIRMATION",
        reaction_state="CONFIRMING",
    )]))
    assert board.iloc[0]["candidate_action"] == "ENTRY_TRIGGERED_ETF_RISK_PENDING"


def test_edge_overlay_cannot_create_noncanonical_pair(tmp_path: Path):
    structural = pd.DataFrame([base_row()])
    p = tmp_path / "edge.csv"
    pd.DataFrame([{
        "driver_id": "AI_SERVER_SHIPMENTS",
        "taiwan_code": "9999",
        "provenance_status": "SOURCE_BACKED",
        "as_of_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source_count": 1,
        "source_summary": "evidence",
    }]).to_csv(p, index=False)
    out = apply_edge_provenance(structural, p)
    assert out.iloc[0]["provenance_status"] == "NEEDS_SOURCE_BACKFILL"


def test_valid_edge_overlay_upgrades_existing_pair(tmp_path: Path):
    structural = pd.DataFrame([base_row()])
    p = tmp_path / "edge.csv"
    pd.DataFrame([{
        "driver_id": "AI_SERVER_SHIPMENTS",
        "taiwan_code": "2317",
        "provenance_status": "SOURCE_BACKED",
        "as_of_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source_count": 1,
        "source_summary": "company evidence",
    }]).to_csv(p, index=False)
    out = apply_edge_provenance(structural, p)
    assert out.iloc[0]["provenance_status"] == "SOURCE_BACKED"
