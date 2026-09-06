import json

import pandas as pd
import pytest

from position_alias_output import build_alias_payload, load_alias_map, update_public_alias_meta


def _actions():
    return pd.DataFrame([
        {
            "position_index": 0,
            "action": "HOLD",
            "reason": "SYSTEM_THESIS_ACTIVE_SOURCE_BACKED",
            "thesis_mapping": "SYSTEM_TICKER_EXPOSURE",
            "thesis_strength": 3,
            "user_thesis_disagrees": False,
            "weight_pct": 99.0,
        },
        {
            "position_index": 1,
            "action": "REDUCE_RISK",
            "reason": "PORTFOLIO_GROSS_EXPOSURE_ABOVE_POLICY",
            "thesis_mapping": "SYSTEM_RISK_GROUP",
            "thesis_strength": 1,
            "user_thesis_disagrees": False,
            "weight_pct": 88.0,
        },
    ])


def _portfolio():
    return {
        "cash_twd": 999,
        "positions": [
            {"ticker": "1111.TW", "market_value_twd": 111, "weight_pct": 10, "unrealized_pnl_pct": 2},
            {"ticker": "2222", "market_value_twd": 222, "weight_pct": 20, "unrealized_pnl_pct": -3},
        ],
    }


def test_alias_payload_contains_actions_but_no_tickers_or_balances():
    payload = build_alias_payload(_actions(), _portfolio(), {"1111": "CORE_A", "2222": "SAT_B"}, "r1")
    assert [r["alias"] for r in payload["positions"]] == ["CORE_A", "SAT_B"]
    assert payload["positions"][1]["action"] == "REDUCE_RISK"
    text = json.dumps(payload)
    for forbidden in ["1111", "2222", "market_value_twd", "weight_pct", "unrealized_pnl_pct", "cash_twd"]:
        assert forbidden not in text


def test_alias_map_loaded_from_secret_without_suffix_leak(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_ALIAS_JSON", json.dumps({"aliases": {"1111.TW": "CORE_A", "2222": "SAT_B"}}))
    assert load_alias_map({}) == {"1111": "CORE_A", "2222": "SAT_B"}


def test_unicode_aliases_are_supported(monkeypatch):
    monkeypatch.setenv(
        "ALPHA_HUNTER_POSITION_ALIAS_JSON",
        json.dumps({"aliases": {"1111": "標的A", "2222": "零碎部位"}}, ensure_ascii=False),
    )
    assert load_alias_map({}) == {"1111": "標的A", "2222": "零碎部位"}


def test_alias_map_can_come_from_private_portfolio_fields(monkeypatch):
    monkeypatch.delenv("ALPHA_HUNTER_POSITION_ALIAS_JSON", raising=False)
    p = {"positions": [{"ticker": "1111.TW", "alias": "core_a"}]}
    assert load_alias_map(p) == {"1111": "CORE_A"}


def test_missing_alias_mapping_fails_closed(monkeypatch):
    monkeypatch.delenv("ALPHA_HUNTER_POSITION_ALIAS_JSON", raising=False)
    with pytest.raises(RuntimeError, match="POSITION_ALIAS_NOT_CONFIGURED"):
        load_alias_map(_portfolio())


def test_incomplete_alias_mapping_fails_closed():
    with pytest.raises(RuntimeError, match="POSITION_ALIAS_MAPPING_INCOMPLETE"):
        build_alias_payload(_actions(), _portfolio(), {"1111": "CORE_A"}, "r1")


def test_duplicate_alias_rejected(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_ALIAS_JSON", json.dumps({"1111": "SAME", "2222": "SAME"}))
    with pytest.raises(RuntimeError, match="POSITION_ALIAS_DUPLICATE"):
        load_alias_map({})


def test_alias_with_whitespace_or_punctuation_rejected(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_POSITION_ALIAS_JSON", json.dumps({"1111": "標的 A"}, ensure_ascii=False))
    with pytest.raises(RuntimeError, match="POSITION_ALIAS_INVALID_FORMAT"):
        load_alias_map({})


def test_public_meta_contains_no_mapping_or_ticker(tmp_path):
    p = tmp_path / "decision_packet.json"
    p.write_text(json.dumps({
        "existing_position_layer": {
            "private_handoff": {"delivery": "OLD"},
            "position_action_counts": {"HOLD": 1},
        }
    }), encoding="utf-8")
    update_public_alias_meta("READY", 2, p)
    out = json.loads(p.read_text(encoding="utf-8"))
    layer = out["existing_position_layer"]
    assert "private_handoff" not in layer
    meta = layer["alias_output"]
    assert meta["status"] == "READY"
    assert meta["record_count"] == 2
    text = json.dumps(meta).lower()
    assert "ticker" in text  # only the explicit privacy assertion key, never a ticker value
    assert "mapping" in text
    assert "1111" not in text
