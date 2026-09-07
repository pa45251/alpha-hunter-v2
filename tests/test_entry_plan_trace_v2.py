import json
from pathlib import Path

import pandas as pd

import entry_plan_trace_v2 as tr


def _manifest(path: Path, run_id: str = "RUN1", closed: str = "2026-09-04") -> None:
    path.write_text(
        json.dumps({"run_id": run_id, "taiwan": {"latest_price_date": closed}}),
        encoding="utf-8",
    )


def _plan_row(**overrides):
    row = {
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
        "risk_v2_pass": False,
        "global_alignment_score": 0.8,
        "price_as_of_utc": "2026-09-04T00:00:00",
        "trigger_price": 200.0,
        "buy_zone_low": 200.0,
        "buy_zone_high": 203.0,
        "invalidation_price": 188.0,
    }
    row.update(overrides)
    return row


def _patch_paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(tr, "OUT", tmp_path)
    monkeypatch.setattr(tr, "PLANS", tmp_path / "entry_plans_v2.csv")
    monkeypatch.setattr(tr, "MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(tr, "TRACE", tmp_path / "entry_plan_trace_v2.csv")


def test_same_source_run_does_not_duplicate_trace(monkeypatch, tmp_path: Path):
    _patch_paths(monkeypatch, tmp_path)
    pd.DataFrame([_plan_row()]).to_csv(tr.PLANS, index=False)
    _manifest(tr.MANIFEST)

    first = tr.append_entry_plan_trace()
    second = tr.append_entry_plan_trace()
    assert len(first) == 1
    assert len(second) == 1
    assert second.iloc[0]["decision_session"] == "2026-09-04"
    assert second.iloc[0]["canonical_closed_price_date"] == "2026-09-04"
    assert bool(second.iloc[0]["closed_session_verified"])
    assert bool(second.iloc[0]["score_is_probability"]) is False
    assert bool(second.iloc[0]["risk_gate_pass"]) is False


def test_pre_freeze_open_session_trace_is_purged(monkeypatch, tmp_path: Path):
    _patch_paths(monkeypatch, tmp_path)
    _manifest(tr.MANIFEST, closed="2026-09-04")
    old = pd.DataFrame([{
        "decision_session": "2026-09-07", "ticker": "2317.TW",
        "driver_id": "AI_SERVER_SHIPMENTS", "entry_style": "FRESH_BREAKOUT",
        "current_action": "WAIT_BREAKOUT", "entry_status": "WAITING_FOR_TRIGGER",
    }])
    old.to_csv(tr.TRACE, index=False)
    pd.DataFrame([_plan_row()]).to_csv(tr.PLANS, index=False)

    out = tr.append_entry_plan_trace()
    assert "2026-09-07" not in set(out["decision_session"].astype(str))
    assert set(out["decision_session"].astype(str)) == {"2026-09-04"}


def test_new_open_session_plan_fails_closed(monkeypatch, tmp_path: Path):
    _patch_paths(monkeypatch, tmp_path)
    _manifest(tr.MANIFEST, closed="2026-09-04")
    pd.DataFrame([_plan_row(price_as_of_utc="2026-09-07T00:00:00")]).to_csv(tr.PLANS, index=False)

    try:
        tr.append_entry_plan_trace()
    except RuntimeError as exc:
        assert "OPEN_OR_FUTURE_SESSION_BLOCKED" in str(exc)
    else:
        raise AssertionError("open-session trace should fail closed")
