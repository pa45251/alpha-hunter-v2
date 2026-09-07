import json
from pathlib import Path

import pandas as pd

import entry_plan_trace_v2 as tr


def test_same_source_run_does_not_duplicate_trace(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(tr, "OUT", tmp_path)
    monkeypatch.setattr(tr, "PLANS", tmp_path / "entry_plans_v2.csv")
    monkeypatch.setattr(tr, "MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(tr, "TRACE", tmp_path / "entry_plan_trace_v2.csv")

    pd.DataFrame([{
        "strategy_version": "ALPHA_HUNTER_ADVISORY_V2",
        "ticker": "2317.TW",
        "name": "SYN",
        "global_theme": "AI_Server",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "entry_style": "FRESH_BREAKOUT",
        "reaction_state": "CONFIRMING",
        "current_action": "WAIT_BREAKOUT",
        "entry_status": "WAITING_FOR_TRIGGER",
        "entry_structure_valid": True,
        "global_alignment_score": 0.8,
        "price_as_of_utc": "2026-09-04T00:00:00",
        "trigger_price": 200.0,
        "buy_zone_low": 200.0,
        "buy_zone_high": 203.0,
        "invalidation_price": 188.0,
    }]).to_csv(tr.PLANS, index=False)
    tr.MANIFEST.write_text(json.dumps({"run_id": "RUN1"}), encoding="utf-8")

    first = tr.append_entry_plan_trace()
    second = tr.append_entry_plan_trace()
    assert len(first) == 1
    assert len(second) == 1
    assert second.iloc[0]["decision_session"] == "2026-09-04"
    assert bool(second.iloc[0]["score_is_probability"]) is False
