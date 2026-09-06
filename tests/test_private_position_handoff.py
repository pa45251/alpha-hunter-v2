import json
from pathlib import Path

import pandas as pd

from private_position_handoff import build_private_payload, update_public_delivery_meta


def test_private_payload_maps_position_index_to_ticker_without_balances():
    actions = pd.DataFrame([
        {
            "position_index": 1,
            "action": "REDUCE_RISK",
            "reason": "PORTFOLIO_GROSS_EXPOSURE_ABOVE_POLICY",
            "thesis_mapping": "SYSTEM_RISK_GROUP",
            "thesis_strength": 1,
            "user_thesis_disagrees": False,
            "weight_pct": 99.9,
        }
    ])
    portfolio = {
        "cash_twd": 123,
        "financing_debt_twd": 456,
        "positions": [
            {"ticker": "AAA", "market_value_twd": 111, "weight_pct": 10.0},
            {"ticker": "BBB", "market_value_twd": 222, "weight_pct": 20.0, "unrealized_pnl_pct": -7.0},
        ],
    }
    payload = build_private_payload(actions, portfolio, "r1")
    assert payload["positions"][0]["ticker"] == "BBB"
    assert payload["positions"][0]["action"] == "REDUCE_RISK"
    text = json.dumps(payload)
    for forbidden in ["market_value_twd", "weight_pct", "unrealized_pnl_pct", "cash_twd", "financing_debt_twd"]:
        assert forbidden not in text


def test_private_payload_fails_closed_on_bad_position_index():
    actions = pd.DataFrame([{"position_index": 3, "action": "HOLD"}])
    portfolio = {"positions": [{"ticker": "AAA"}]}
    try:
        build_private_payload(actions, portfolio, "r1")
    except RuntimeError as exc:
        assert "POSITION_INDEX_MISMATCH" in str(exc)
    else:
        raise AssertionError("Expected a fail-closed position index mismatch")


def test_public_delivery_meta_never_contains_position_identity(tmp_path: Path):
    p = tmp_path / "decision_packet.json"
    p.write_text(json.dumps({
        "run_id": "r1",
        "existing_position_layer": {"position_action_counts": {"REDUCE_RISK": 1}},
    }), encoding="utf-8")
    update_public_delivery_meta("GOOGLE_DRIVE_UPLOADED", 5, p)
    out = json.loads(p.read_text(encoding="utf-8"))
    meta = out["existing_position_layer"]["private_handoff"]
    assert meta["record_count"] == 5
    assert meta["delivery"] == "GOOGLE_DRIVE_UPLOADED"
    assert meta["private_details_committed"] is False
    text = json.dumps(meta)
    assert "AAA" not in text
    assert "BBB" not in text
    assert "position_index" not in text
