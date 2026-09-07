from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json

import pandas as pd

from decision_engine import build_decision_board, build_decision_packet

CONTRACT = "ALPHA_HUNTER_DECISION_STATE_V2"


def _normalize_code(v) -> str:
    return str(v).strip().split(".")[0].zfill(4)


def _date_string(v) -> str:
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return ""
        if isinstance(ts, pd.DatetimeIndex):
            return ""
        return pd.Timestamp(ts).date().isoformat()
    except Exception:
        return ""


def _recorded_session(v) -> str:
    try:
        ts = pd.to_datetime(v, utc=True, errors="coerce")
        if pd.isna(ts):
            return ""
        return pd.Timestamp(ts).tz_convert("Asia/Taipei").date().isoformat()
    except Exception:
        return ""


def _current_session(row: pd.Series) -> str:
    # Taiwan market date is authoritative for Taiwan reaction/entry state. Using the workflow
    # execution date would incorrectly treat weekend/manual reruns as new market observations.
    for c in ("last_price_date", "taiwan_last_price_date", "price_date"):
        if c in row.index:
            d = _date_string(row.get(c))
            if d:
                return d
    return ""


def apply_previous_state_v2(board_input: pd.DataFrame, history_path: Path) -> pd.DataFrame:
    """Attach the most recent state from a STRICTLY EARLIER Taiwan market session.

    Re-running the same scanner/decision snapshot 1, 2 or 10 times therefore cannot consume an
    entry trigger or advance a state streak. Legacy history without a decision_session is mapped
    conservatively to its recorded Taipei date; rows recorded after the current market session are
    never allowed to masquerade as prior observations.
    """
    x = board_input.copy()
    if x.empty:
        x["previous_reaction_state"] = ""
        x["previous_candidate_action"] = ""
        x["decision_session"] = ""
        return x

    x["taiwan_code"] = x["taiwan_code"].map(_normalize_code)
    x["decision_session"] = x.apply(_current_session, axis=1)
    x["previous_reaction_state"] = ""
    x["previous_candidate_action"] = ""

    if not history_path.exists():
        return x
    try:
        h = pd.read_csv(history_path, dtype={"taiwan_code": str})
    except Exception:
        return x
    req = {"driver_id", "taiwan_code", "reaction_state", "candidate_action", "recorded_at"}
    if h.empty or not req.issubset(h.columns):
        return x

    h = h.copy()
    h["taiwan_code"] = h["taiwan_code"].map(_normalize_code)
    if "decision_session" in h.columns:
        hs = h["decision_session"].map(_date_string)
    elif "last_price_date" in h.columns:
        hs = h["last_price_date"].map(_date_string)
    else:
        hs = pd.Series("", index=h.index)
    fallback = h["recorded_at"].map(_recorded_session)
    h["_history_session"] = hs.where(hs.astype(str).str.len().gt(0), fallback)
    h["_recorded_at_ts"] = pd.to_datetime(h["recorded_at"], utc=True, errors="coerce")

    prev_states: list[str] = []
    prev_actions: list[str] = []
    for _, row in x.iterrows():
        session = str(row.get("decision_session", ""))
        if not session:
            prev_states.append("")
            prev_actions.append("")
            continue
        c = h[
            h["driver_id"].astype(str).eq(str(row.get("driver_id", "")))
            & h["taiwan_code"].astype(str).eq(str(row.get("taiwan_code", "")))
            & h["_history_session"].astype(str).lt(session)
        ].copy()
        if c.empty:
            prev_states.append("")
            prev_actions.append("")
            continue
        c = c.sort_values(["_history_session", "_recorded_at_ts"], na_position="first")
        last = c.iloc[-1]
        prev_states.append(str(last.get("reaction_state", "") or ""))
        prev_actions.append(str(last.get("candidate_action", "") or ""))

    x["previous_reaction_state"] = prev_states
    x["previous_candidate_action"] = prev_actions
    return x


def write_decision_outputs_v2(
    structural_matches: pd.DataFrame,
    run_id: str,
    output_dir: str = "output",
) -> tuple[pd.DataFrame, dict]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    history_path = out / "decision_history.csv"

    stateful = apply_previous_state_v2(structural_matches, history_path)
    session_map = stateful[["driver_id", "taiwan_code", "decision_session"]].drop_duplicates(
        ["driver_id", "taiwan_code"], keep="last"
    )
    board = build_decision_board(stateful)
    if not board.empty:
        board["taiwan_code"] = board["taiwan_code"].map(_normalize_code)
        board = board.merge(session_map, on=["driver_id", "taiwan_code"], how="left")
    else:
        board["decision_session"] = pd.Series(dtype=str)

    board.to_csv(out / "decision_board.csv", index=False)
    packet = build_decision_packet(board, run_id)
    packet["state_lifecycle"] = {
        "contract": CONTRACT,
        "session_key": "TAIWAN_LAST_PRICE_DATE",
        "previous_state_must_be_strictly_earlier_session": True,
        "same_session_rerun_can_consume_trigger": False,
    }
    (out / "decision_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    if not board.empty:
        hist_cols = [
            c for c in [
                "run_id", "decision_session", "driver_id", "taiwan_code", "ticker", "name",
                "reaction_state", "candidate_action", "decision_stage", "stock_vs_etf_state",
                "entry_trigger_state",
            ] if c in board.columns
        ]
        snap = board[hist_cols].copy()
        snap["recorded_at"] = datetime.now().astimezone().isoformat()
        if history_path.exists():
            old = pd.read_csv(history_path, dtype={"taiwan_code": str})
            hist = pd.concat([old, snap], ignore_index=True)
            hist = hist.drop_duplicates(["run_id", "driver_id", "taiwan_code"], keep="last")
        else:
            hist = snap
        hist.to_csv(history_path, index=False)
    return board, packet
