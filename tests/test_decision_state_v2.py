from pathlib import Path

import pandas as pd

from decision_state_v2 import apply_previous_state_v2


def _current(session: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "driver_id": "AI_SERVER_SHIPMENTS",
        "taiwan_code": "2317",
        "last_price_date": session,
        "reaction_state": "CONFIRMING",
    }])


def test_same_session_history_is_ignored_for_previous_state(tmp_path: Path):
    history = pd.DataFrame([
        {
            "run_id": "R0", "decision_session": "2026-09-03", "driver_id": "AI_SERVER_SHIPMENTS",
            "taiwan_code": "2317", "reaction_state": "PRE_CONFIRMATION", "candidate_action": "WATCH_ENTRY",
            "recorded_at": "2026-09-03T14:00:00+00:00",
        },
        {
            "run_id": "R1", "decision_session": "2026-09-04", "driver_id": "AI_SERVER_SHIPMENTS",
            "taiwan_code": "2317", "reaction_state": "CONFIRMING", "candidate_action": "ENTRY_TRIGGERED_STOCK_RISK_PENDING",
            "recorded_at": "2026-09-04T14:00:00+00:00",
        },
    ])
    p = tmp_path / "decision_history.csv"
    history.to_csv(p, index=False)

    first = apply_previous_state_v2(_current("2026-09-04"), p)
    tenth = apply_previous_state_v2(_current("2026-09-04"), p)
    assert first.iloc[0]["previous_reaction_state"] == "PRE_CONFIRMATION"
    assert tenth.iloc[0]["previous_reaction_state"] == "PRE_CONFIRMATION"
    assert first.iloc[0]["decision_session"] == "2026-09-04"


def test_next_market_session_can_use_prior_session_state(tmp_path: Path):
    history = pd.DataFrame([
        {
            "run_id": "R1", "decision_session": "2026-09-04", "driver_id": "AI_SERVER_SHIPMENTS",
            "taiwan_code": "2317", "reaction_state": "CONFIRMING", "candidate_action": "WATCH_ENTRY",
            "recorded_at": "2026-09-04T14:00:00+00:00",
        },
    ])
    p = tmp_path / "decision_history.csv"
    history.to_csv(p, index=False)
    x = apply_previous_state_v2(_current("2026-09-07"), p)
    assert x.iloc[0]["previous_reaction_state"] == "CONFIRMING"


def test_legacy_history_recorded_after_market_session_cannot_be_prior_state(tmp_path: Path):
    # Legacy rows lacked decision_session. A weekend/manual rerun recorded on 9/6 must not become
    # the previous observation for the still-current 9/4 market session.
    history = pd.DataFrame([{
        "run_id": "LEGACY", "driver_id": "AI_SERVER_SHIPMENTS", "taiwan_code": "2317",
        "reaction_state": "CONFIRMING", "candidate_action": "WATCH_ENTRY",
        "recorded_at": "2026-09-06T02:00:00+00:00",
    }])
    p = tmp_path / "decision_history.csv"
    history.to_csv(p, index=False)
    x = apply_previous_state_v2(_current("2026-09-04"), p)
    assert x.iloc[0]["previous_reaction_state"] == ""
