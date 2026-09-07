from pathlib import Path

import pandas as pd

from shadow_audit_v2 import append_shadow_audit_v2


def _board(run_id: str):
    return pd.DataFrame([{
        "run_id": run_id,
        "decision_contract_version": "2.7.1",
        "ticker": "2317.TW",
        "taiwan_code": "2317",
        "name": "SYN",
        "global_theme": "AI_Server",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "dynamic_driver_state": "ACTIVE_RESEARCH_VALIDATED",
        "provenance_status": "SOURCE_BACKED",
        "reaction_state": "CONFIRMING",
        "previous_reaction_state": "PRE_CONFIRMATION",
        "entry_trigger_state": "BREAKOUT_CONFIRMATION_TRIGGER",
        "stock_vs_etf_state": "STOCK_ALPHA_RESEARCH",
        "candidate_action": "ENTRY_TRIGGERED_STOCK_RISK_PENDING",
        "portfolio_action": "WATCH_ENTRY",
        "risk_gate_pass": False,
        "decision_blockers": "",
        "risk_blockers": "",
        "strategy_version": "ALPHA_HUNTER_SHADOW_V1",
        "deployment_mode": "SHADOW",
        "live_execution_authorized": False,
        "execution_action": "NO_LIVE_ORDER",
        "decision_session": "2026-09-04",
        "public_lineage_id": "L1",
    }])


def test_identical_same_session_reruns_are_one_prospective_observation(tmp_path: Path):
    p = tmp_path / "shadow.csv"
    first = append_shadow_audit_v2(_board("RUN1"), str(p))
    second = append_shadow_audit_v2(_board("RUN2"), str(p))
    assert len(first) == 1
    assert len(second) == 1
    assert second.iloc[0]["decision_session"] == "2026-09-04"


def test_materially_changed_same_session_action_is_kept(tmp_path: Path):
    p = tmp_path / "shadow.csv"
    append_shadow_audit_v2(_board("RUN1"), str(p))
    b = _board("RUN2")
    b.loc[0, "portfolio_action"] = "BUY_STOCK"
    out = append_shadow_audit_v2(b, str(p))
    assert len(out) == 2
