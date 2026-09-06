from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any

import pandas as pd

from existing_position import apply_existing_position_engine
from portfolio_risk import load_portfolio_state


OUT = Path("output")
PUBLIC_PACKET_PATH = OUT / "decision_packet.json"
DECISION_BOARD_PATH = OUT / "decision_board.csv"
ALIAS_OUTPUT_PATH = OUT / "position_alias_actions.json"
ALIAS_ENV = "ALPHA_HUNTER_POSITION_ALIAS_JSON"
ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _ticker_key(v: Any) -> str:
    return str(v or "").strip().upper().removesuffix(".TWO").removesuffix(".TW")


def load_alias_map(portfolio: dict[str, Any] | None = None) -> dict[str, str]:
    """Load ticker -> alias mapping from a private secret or private portfolio fields.

    Preferred secret formats:
      {"aliases": {"1234": "CORE_A", "5678.TW": "SAT_B"}}
      {"1234": "CORE_A", "5678.TW": "SAT_B"}

    For convenience, an `alias` field inside each private portfolio position is also accepted.
    No ticker/alias mapping is ever written to the public repository.
    """
    mapping: dict[str, str] = {}
    raw = os.getenv(ALIAS_ENV, "").strip()
    if raw:
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise RuntimeError("POSITION_ALIAS_JSON_INVALID") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("POSITION_ALIAS_JSON_INVALID_SCHEMA")
        aliases = payload.get("aliases", payload)
        if not isinstance(aliases, dict):
            raise RuntimeError("POSITION_ALIAS_JSON_INVALID_SCHEMA")
        for ticker, alias in aliases.items():
            key = _ticker_key(ticker)
            value = str(alias or "").strip().upper()
            if not key or not value:
                raise RuntimeError("POSITION_ALIAS_JSON_EMPTY_ENTRY")
            mapping[key] = value

    for pos in ((portfolio or {}).get("positions") or []):
        if not isinstance(pos, dict):
            continue
        key = _ticker_key(pos.get("ticker"))
        alias = str(pos.get("alias", "") or "").strip().upper()
        if key and alias and key not in mapping:
            mapping[key] = alias

    if not mapping:
        raise RuntimeError("POSITION_ALIAS_NOT_CONFIGURED")

    seen: set[str] = set()
    for alias in mapping.values():
        if not ALIAS_RE.fullmatch(alias):
            raise RuntimeError("POSITION_ALIAS_INVALID_FORMAT")
        if alias in seen:
            raise RuntimeError("POSITION_ALIAS_DUPLICATE")
        seen.add(alias)
    return mapping


def _build_actions_from_current_runtime(board: pd.DataFrame, run_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Recompute exact private actions using the same frozen existing-position engine."""
    private_board = board
    maintenance_path = os.getenv("ALPHA_HUNTER_MAINTENANCE_RESEARCH_PATH", "").strip()
    if maintenance_path:
        from portfolio_maintenance_research import private_board_overlay
        private_board, _ = private_board_overlay(board, run_id)
    return apply_existing_position_engine(private_board)


def build_alias_payload(
    private_actions: pd.DataFrame,
    portfolio: dict[str, Any],
    alias_map: dict[str, str],
    run_id: str,
) -> dict[str, Any]:
    """Join private position actions to aliases without publishing tickers or balances."""
    positions = list((portfolio or {}).get("positions") or [])
    if private_actions is None:
        private_actions = pd.DataFrame()

    records: list[dict[str, Any]] = []
    for row in private_actions.to_dict(orient="records"):
        idx = _i(row.get("position_index"), -1)
        if idx < 0 or idx >= len(positions):
            raise RuntimeError("POSITION_ALIAS_INDEX_MISMATCH")
        ticker_key = _ticker_key(positions[idx].get("ticker"))
        if not ticker_key:
            raise RuntimeError("POSITION_ALIAS_PRIVATE_TICKER_MISSING")
        alias = alias_map.get(ticker_key)
        if not alias:
            raise RuntimeError("POSITION_ALIAS_MAPPING_INCOMPLETE")
        records.append({
            "alias": alias,
            "action": str(row.get("action", "")),
            "reason": str(row.get("reason", "")),
            "thesis_mapping": str(row.get("thesis_mapping", "")),
            "thesis_strength": _i(row.get("thesis_strength"), 0),
            "user_thesis_disagrees": bool(row.get("user_thesis_disagrees", False)),
        })

    if len({r["alias"] for r in records}) != len(records):
        raise RuntimeError("POSITION_ALIAS_OUTPUT_DUPLICATE")

    return {
        "contract": "ALPHA_HUNTER_POSITION_ALIAS_ACTIONS",
        "schema_version": "1.0",
        "run_id": str(run_id),
        "generated_at": datetime.now().astimezone().isoformat(),
        "privacy": {
            "alias_only": True,
            "ticker_included": False,
            "name_included": False,
            "balances_included": False,
            "weights_included": False,
            "pnl_included": False,
            "alias_mapping_published": False,
        },
        "positions": records,
    }


def _assert_matches_public_counts(payload: dict[str, Any], packet: dict[str, Any]) -> None:
    observed = Counter(str(r.get("action", "")) for r in (payload.get("positions") or []))
    expected_raw = ((packet.get("existing_position_layer") or {}).get("position_action_counts") or {})
    expected = Counter({str(k): int(v) for k, v in expected_raw.items()})
    if observed != expected:
        raise RuntimeError("POSITION_ALIAS_ACTION_COUNT_MISMATCH")


def update_public_alias_meta(status: str, record_count: int, packet_path: Path = PUBLIC_PACKET_PATH) -> None:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    layer = dict(packet.get("existing_position_layer") or {})
    layer.pop("private_handoff", None)
    layer["alias_output"] = {
        "schema_version": "1.0",
        "status": str(status),
        "record_count": int(record_count),
        "contains_alias_level_actions": status == "READY",
        "contains_tickers_names_balances_weights_or_pnl": False,
        "alias_mapping_published": False,
        "path": str(ALIAS_OUTPUT_PATH) if status == "READY" else None,
    }
    packet["existing_position_layer"] = layer
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")


def write_alias_output() -> tuple[dict[str, Any], dict[str, Any]]:
    if not PUBLIC_PACKET_PATH.exists() or not DECISION_BOARD_PATH.exists():
        raise RuntimeError("POSITION_ALIAS_DECISION_INPUTS_MISSING")

    packet = json.loads(PUBLIC_PACKET_PATH.read_text(encoding="utf-8"))
    run_id = str(packet.get("run_id", ""))
    if not run_id:
        raise RuntimeError("POSITION_ALIAS_RUN_ID_MISSING")

    board = pd.read_csv(DECISION_BOARD_PATH, dtype={"taiwan_code": str})
    private_actions, position_meta = _build_actions_from_current_runtime(board, run_id)
    portfolio = load_portfolio_state()
    alias_map = load_alias_map(portfolio)
    payload = build_alias_payload(private_actions, portfolio, alias_map, run_id)
    _assert_matches_public_counts(payload, packet)

    OUT.mkdir(parents=True, exist_ok=True)
    ALIAS_OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload, position_meta


def main() -> None:
    status = "FAILED"
    record_count = 0
    try:
        payload, _ = write_alias_output()
        record_count = len(payload.get("positions") or [])
        status = "READY"
    except RuntimeError as exc:
        # Fail closed: never leave a stale alias file that could be mistaken for the current run.
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
        else:
            status = "FAILED"
    except Exception:
        ALIAS_OUTPUT_PATH.unlink(missing_ok=True)
        status = "FAILED"

    if PUBLIC_PACKET_PATH.exists():
        update_public_alias_meta(status, record_count)

    print(f"Position alias output: status={status} records={record_count}; no ticker/name/balance/weight/P&L published")


if __name__ == "__main__":
    main()
