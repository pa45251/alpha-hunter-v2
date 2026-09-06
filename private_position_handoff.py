from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from existing_position import apply_existing_position_engine
from portfolio_risk import load_portfolio_state
from gdrive_upload import upload_or_replace


PRIVATE_HANDOFF_PATH = Path("/tmp/alpha_hunter_private_position_actions.json")
PUBLIC_PACKET_PATH = Path("output/decision_packet.json")
PRIVATE_FILENAME = "alpha_hunter_private_position_actions.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def build_private_payload(
    private_actions: pd.DataFrame,
    portfolio: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """Join private position actions back to private tickers without publishing balances.

    The returned payload is private-only. It intentionally excludes market value, weight,
    cost basis, P/L, cash, financing and all other portfolio balances.
    """
    positions = list((portfolio or {}).get("positions") or [])
    records: list[dict[str, Any]] = []
    if private_actions is None:
        private_actions = pd.DataFrame()

    for row in private_actions.to_dict(orient="records"):
        idx = _i(row.get("position_index"), -1)
        if idx < 0 or idx >= len(positions):
            raise RuntimeError("PRIVATE_HANDOFF_POSITION_INDEX_MISMATCH")
        pos = positions[idx]
        ticker = str(pos.get("ticker", "")).strip()
        if not ticker:
            raise RuntimeError("PRIVATE_HANDOFF_TICKER_MISSING")
        records.append({
            "ticker": ticker,
            "action": str(row.get("action", "")),
            "reason": str(row.get("reason", "")),
            "thesis_mapping": str(row.get("thesis_mapping", "")),
            "thesis_strength": _i(row.get("thesis_strength"), 0),
            "user_thesis_disagrees": bool(row.get("user_thesis_disagrees", False)),
        })

    return {
        "contract": "ALPHA_HUNTER_PRIVATE_POSITION_ACTIONS",
        "schema_version": "1.0",
        "run_id": str(run_id),
        "generated_at": datetime.now().astimezone().isoformat(),
        "privacy": {
            "private_only": True,
            "balances_included": False,
            "weights_included": False,
            "pnl_included": False,
            "public_repo_commit_allowed": False,
        },
        "positions": records,
    }


def _build_actions_from_current_runtime(board: pd.DataFrame, run_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Recompute private actions after the public decision run without changing frozen rules.

    If an ephemeral portfolio-maintenance result is present, apply the same private overlay used
    by decision_run_with_maintenance.py so the handoff matches that run.
    """
    private_board = board
    maintenance_path = os.getenv("ALPHA_HUNTER_MAINTENANCE_RESEARCH_PATH", "").strip()
    if maintenance_path:
        from portfolio_maintenance_research import private_board_overlay
        private_board, _ = private_board_overlay(board, run_id)
    return apply_existing_position_engine(private_board)


def write_private_handoff(path: Path = PRIVATE_HANDOFF_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    if not PUBLIC_PACKET_PATH.exists() or not Path("output/decision_board.csv").exists():
        raise RuntimeError("PRIVATE_HANDOFF_PUBLIC_DECISION_INPUTS_MISSING")

    packet = json.loads(PUBLIC_PACKET_PATH.read_text(encoding="utf-8"))
    run_id = str(packet.get("run_id", ""))
    if not run_id:
        raise RuntimeError("PRIVATE_HANDOFF_RUN_ID_MISSING")

    board = pd.read_csv("output/decision_board.csv", dtype={"taiwan_code": str})
    private_actions, position_meta = _build_actions_from_current_runtime(board, run_id)
    portfolio = load_portfolio_state()
    payload = build_private_payload(private_actions, portfolio, run_id)

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return payload, position_meta


def upload_private_handoff(path: Path = PRIVATE_HANDOFF_PATH) -> str:
    """Upload to the configured private Drive folder; never fall back to public storage."""
    raw = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    folder = os.getenv("GDRIVE_FOLDER_ID", "").strip()
    if not raw or not folder:
        return "NOT_CONFIGURED"
    if not path.exists():
        return "PRIVATE_FILE_MISSING"

    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    upload_or_replace(svc, folder, path)
    return "GOOGLE_DRIVE_UPLOADED"


def update_public_delivery_meta(
    delivery: str,
    record_count: int,
    packet_path: Path = PUBLIC_PACKET_PATH,
) -> None:
    """Write only privacy-safe delivery metadata to the public packet."""
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    layer = dict(packet.get("existing_position_layer") or {})
    layer["private_handoff"] = {
        "schema_version": "1.0",
        "record_count": int(record_count),
        "contains_ticker_level_actions": True,
        "contains_balances_weights_or_pnl": False,
        "delivery": str(delivery),
        "drive_filename": PRIVATE_FILENAME if delivery == "GOOGLE_DRIVE_UPLOADED" else None,
        "private_details_committed": False,
    }
    packet["existing_position_layer"] = layer
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    delivery = "GENERATION_FAILED"
    record_count = 0
    try:
        payload, _ = write_private_handoff(PRIVATE_HANDOFF_PATH)
        record_count = len(payload.get("positions") or [])
        delivery = upload_private_handoff(PRIVATE_HANDOFF_PATH)
    except Exception as exc:
        # Do not print private payloads or tickers. The exception class/message is constrained to
        # deterministic handoff failures unless an external upload client raises.
        delivery = f"FAILED:{type(exc).__name__}"
    finally:
        if PUBLIC_PACKET_PATH.exists():
            update_public_delivery_meta(delivery, record_count, PUBLIC_PACKET_PATH)
        try:
            PRIVATE_HANDOFF_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    print(f"Private position handoff: delivery={delivery} records={record_count}; no ticker-level data written to git/logs")


if __name__ == "__main__":
    main()
