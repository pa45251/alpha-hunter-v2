from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pandas as pd

import position_alias_output as legacy
from existing_position_v2 import apply_existing_position_engine, CONTRACT_VERSION
from portfolio_risk import load_portfolio_state

OUT = Path("output")
PUBLIC_PACKET_PATH = OUT / "decision_packet.json"
DECISION_BOARD_PATH = OUT / "decision_board.csv"
ALIAS_OUTPUT_PATH = OUT / "position_alias_actions.json"


def _publish_meta(packet: dict, payload: dict, status: str) -> None:
    layer = dict(packet.get("existing_position_layer") or {})
    legacy_counts = dict(layer.get("position_action_counts") or {})
    v2_counts = Counter(str(r.get("action", "")) for r in (payload.get("positions") or [])) if status == "READY" else Counter()
    layer["legacy_frozen_v1_position_action_counts"] = legacy_counts
    if status == "READY":
        layer["position_action_counts"] = {str(k): int(v) for k, v in v2_counts.items()}
    layer["existing_position_contract"] = CONTRACT_VERSION
    layer["broken_exit_guard"] = "ACTIVE_DRIVER_PLUS_BROKEN_REQUIRES_PERSISTENCE_CONFIRMATION"
    layer["alias_output"] = {
        "schema_version": "2.0",
        "status": status,
        "record_count": len(payload.get("positions") or []) if status == "READY" else 0,
        "contains_alias_level_actions": status == "READY",
        "contains_tickers_names_balances_weights_or_pnl": False,
        "alias_mapping_published": False,
        "path": str(ALIAS_OUTPUT_PATH) if status == "READY" else None,
    }
    packet["existing_position_layer"] = layer
    PUBLIC_PACKET_PATH.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")


def write_alias_output_v2() -> tuple[dict, dict]:
    if not PUBLIC_PACKET_PATH.exists() or not DECISION_BOARD_PATH.exists():
        raise RuntimeError("POSITION_ALIAS_DECISION_INPUTS_MISSING")
    packet = json.loads(PUBLIC_PACKET_PATH.read_text(encoding="utf-8"))
    run_id = str(packet.get("run_id", ""))
    if not run_id:
        raise RuntimeError("POSITION_ALIAS_RUN_ID_MISSING")
    board = pd.read_csv(DECISION_BOARD_PATH, dtype={"taiwan_code": str})
    private_actions, position_meta = apply_existing_position_engine(board)
    portfolio = load_portfolio_state()
    alias_map = legacy.load_alias_map(portfolio)
    payload = legacy.build_alias_payload(private_actions, portfolio, alias_map, run_id)
    OUT.mkdir(parents=True, exist_ok=True)
    ALIAS_OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _publish_meta(packet, payload, "READY")
    return payload, position_meta


def main() -> None:
    status = "FAILED"
    records = 0
    packet = json.loads(PUBLIC_PACKET_PATH.read_text(encoding="utf-8")) if PUBLIC_PACKET_PATH.exists() else {}
    try:
        payload, _ = write_alias_output_v2()
        records = len(payload.get("positions") or [])
        status = "READY"
    except RuntimeError as exc:
        ALIAS_OUTPUT_PATH.unlink(missing_ok=True)
        if str(exc) in {
            "POSITION_ALIAS_NOT_CONFIGURED",
            "POSITION_ALIAS_MAPPING_INCOMPLETE",
            "POSITION_ALIAS_JSON_INVALID",
            "POSITION_ALIAS_JSON_INVALID_SCHEMA",
            "POSITION_ALIAS_JSON_EMPTY_ENTRY",
            "POSITION_ALIAS_INVALID_FORMAT",
            "POSITION_ALIAS_DUPLICATE",
        }:
            status = "NOT_CONFIGURED"
        if packet:
            _publish_meta(packet, {}, status)
    except Exception:
        ALIAS_OUTPUT_PATH.unlink(missing_ok=True)
        if packet:
            _publish_meta(packet, {}, status)
    print(f"Position alias V2 output: status={status} records={records}; BROKEN alone cannot create thesis exit")


if __name__ == "__main__":
    main()
