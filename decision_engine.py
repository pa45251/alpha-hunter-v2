from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json

import pandas as pd


@dataclass(frozen=True)
class DecisionConfig:
    contract_version: str = "2.7.1"
    source_backed_value: str = "SOURCE_BACKED"
    edge_research_max_age_days: int = 120


ENTRY_RESEARCH_STATES = {"PRE_CONFIRMATION", "EARLY_CONFIRMATION", "CONFIRMING", "PULLBACK"}


def _normalize_code(v) -> str:
    return str(v).strip().split(".")[0].zfill(4)


def apply_edge_provenance(structural_matches: pd.DataFrame, path: Path, cfg: DecisionConfig = DecisionConfig()) -> pd.DataFrame:
    if structural_matches is None or structural_matches.empty or not path.exists():
        return structural_matches
    try:
        e = pd.read_csv(path, dtype={"taiwan_code": str})
    except Exception:
        return structural_matches
    req = {"driver_id", "taiwan_code", "provenance_status", "as_of_utc", "source_count", "source_summary"}
    if e.empty or not req.issubset(e.columns):
        return structural_matches

    x = structural_matches.copy()
    x["taiwan_code"] = x["taiwan_code"].map(_normalize_code)
    e["taiwan_code"] = e["taiwan_code"].map(_normalize_code)
    e["driver_id"] = e["driver_id"].astype(str)
    e["provenance_status"] = e["provenance_status"].fillna("").astype(str).str.upper()
    e["source_count"] = pd.to_numeric(e["source_count"], errors="coerce")
    parsed = pd.to_datetime(e["as_of_utc"], utc=True, errors="coerce")
    age_days = (pd.Timestamp.now(tz="UTC") - parsed).dt.total_seconds() / 86400
    e["edge_research_valid"] = (
        e["provenance_status"].eq(cfg.source_backed_value)
        & e["source_count"].fillna(0).ge(1)
        & age_days.between(0, cfg.edge_research_max_age_days, inclusive="both")
        & e["source_summary"].fillna("").astype(str).str.len().gt(0)
    )
    valid_pairs = set(zip(x["driver_id"].astype(str), x["taiwan_code"]))
    e = e[[pair in valid_pairs for pair in zip(e["driver_id"], e["taiwan_code"])]].copy()
    e = e[e["edge_research_valid"]].drop_duplicates(["driver_id", "taiwan_code"], keep="last")
    if e.empty:
        return x

    x["seed_provenance_status"] = x.get("provenance_status", "")
    cols = ["driver_id", "taiwan_code", "provenance_status", "as_of_utc", "source_count", "source_summary", "counter_evidence", "source_urls", "edge_research_valid"]
    cols = [c for c in cols if c in e.columns]
    e = e[cols].rename(columns={
        "provenance_status": "researched_provenance_status",
        "as_of_utc": "edge_research_as_of_utc",
        "source_count": "edge_source_count",
        "source_summary": "edge_source_summary",
        "counter_evidence": "edge_counter_evidence",
        "source_urls": "edge_source_urls",
    })
    x = x.merge(e, on=["driver_id", "taiwan_code"], how="left")
    valid = x.get("edge_research_valid", False).fillna(False)
    x.loc[valid, "provenance_status"] = x.loc[valid, "researched_provenance_status"]
    return x


def apply_exposure_map(structural_matches: pd.DataFrame, path: Path) -> pd.DataFrame:
    x = structural_matches.copy()
    if x.empty or not path.exists():
        x["etf_ticker"] = ""
        x["exposure_purity"] = ""
        x["comparison_policy"] = ""
        x["stock_vs_etf_state"] = "UNRESOLVED_NO_ETF_MAP"
        return x
    m = pd.read_csv(path)
    if m.empty or "driver_id" not in m.columns:
        return x
    m = m[m.get("enabled", 1).fillna(0).astype(int).eq(1)].copy() if "enabled" in m.columns else m.copy()
    keep = [c for c in ["driver_id", "etf_ticker", "etf_role", "exposure_purity", "comparison_policy", "notes"] if c in m.columns]
    m = m[keep].drop_duplicates("driver_id", keep="last")
    x = x.merge(m, on="driver_id", how="left")
    purity = x.get("exposure_purity", pd.Series("", index=x.index)).fillna("").astype(str).str.upper()
    policy = x.get("comparison_policy", pd.Series("", index=x.index)).fillna("").astype(str).str.upper()
    direct = x.get("linkage_tier", pd.Series("", index=x.index)).fillna("").astype(str).str.upper().isin({"DIRECT", "STRONG"})
    source_backed = x.get("provenance_status", pd.Series("", index=x.index)).fillna("").astype(str).str.upper().eq("SOURCE_BACKED")
    x["stock_vs_etf_state"] = "UNRESOLVED_NO_ETF_MAP"
    x.loc[policy.eq("ETF_CORE_PREFERRED"), "stock_vs_etf_state"] = "ETF_CORE_PREFERRED"
    x.loc[policy.eq("STOCK_ALPHA_ALLOWED") & direct & source_backed & purity.isin({"LOW", "MEDIUM"}), "stock_vs_etf_state"] = "STOCK_ALPHA_RESEARCH"
    x.loc[policy.eq("STOCK_ALPHA_ALLOWED") & ~source_backed, "stock_vs_etf_state"] = "STOCK_BLOCKED_WEAK_EDGE"
    return x


def apply_previous_state(board_input: pd.DataFrame, history_path: Path) -> pd.DataFrame:
    x = board_input.copy()
    x["previous_reaction_state"] = ""
    x["previous_candidate_action"] = ""
    if x.empty or not history_path.exists():
        return x
    try:
        h = pd.read_csv(history_path, dtype={"taiwan_code": str})
    except Exception:
        return x
    req = {"driver_id", "taiwan_code", "reaction_state", "candidate_action", "recorded_at"}
    if h.empty or not req.issubset(h.columns):
        return x
    h["taiwan_code"] = h["taiwan_code"].map(_normalize_code)
    h["recorded_at"] = pd.to_datetime(h["recorded_at"], utc=True, errors="coerce")
    h = h.sort_values("recorded_at").drop_duplicates(["driver_id", "taiwan_code"], keep="last")
    h = h[["driver_id", "taiwan_code", "reaction_state", "candidate_action"]].rename(columns={
        "reaction_state": "previous_reaction_state",
        "candidate_action": "previous_candidate_action",
    })
    x["taiwan_code"] = x["taiwan_code"].map(_normalize_code)
    x = x.drop(columns=["previous_reaction_state", "previous_candidate_action"], errors="ignore").merge(h, on=["driver_id", "taiwan_code"], how="left")
    x["previous_reaction_state"] = x["previous_reaction_state"].fillna("")
    x["previous_candidate_action"] = x["previous_candidate_action"].fillna("")
    return x


def _entry_transition(prev: str, current: str) -> str:
    prev, current = str(prev).upper(), str(current).upper()
    if prev in {"PRE_CONFIRMATION", "EARLY_CONFIRMATION"} and current == "CONFIRMING":
        return "BREAKOUT_CONFIRMATION_TRIGGER"
    if prev == "PULLBACK" and current == "CONFIRMING":
        return "PULLBACK_RECOVERY_TRIGGER"
    return "NOT_TRIGGERED"


def build_decision_board(structural_matches: pd.DataFrame, cfg: DecisionConfig = DecisionConfig()) -> pd.DataFrame:
    if structural_matches is None or structural_matches.empty:
        return pd.DataFrame()
    x = structural_matches.copy()
    for c in ["driver_id", "dynamic_driver_state", "provenance_status", "reaction_state", "polarity", "stock_vs_etf_state", "previous_reaction_state"]:
        if c not in x.columns:
            x[c] = ""
        x[c] = x[c].fillna("").astype(str).str.upper()

    x["gate_driver_active"] = x["dynamic_driver_state"].eq("ACTIVE_RESEARCH_VALIDATED")
    x["gate_edge_source_backed"] = x["provenance_status"].eq(cfg.source_backed_value)
    x["gate_positive_long_edge"] = x["polarity"].eq("POSITIVE")
    x["gate_not_extended"] = ~x["reaction_state"].eq("EXTENDED")
    x["gate_not_broken"] = ~x["reaction_state"].eq("BROKEN")
    x["gate_entry_research_state"] = x["reaction_state"].isin(ENTRY_RESEARCH_STATES)
    x["entry_trigger_state"] = [_entry_transition(p, c) for p, c in zip(x["previous_reaction_state"], x["reaction_state"])]

    actions, stages, blockers = [], [], []
    for r in x.itertuples(index=False):
        b = []
        if not r.gate_driver_active:
            b.append("DRIVER_NOT_ACTIVE_RESEARCH_VALIDATED")
        if not r.gate_edge_source_backed:
            b.append("EDGE_PROVENANCE_NOT_SOURCE_BACKED")
        if not r.gate_positive_long_edge:
            b.append("NOT_POSITIVE_LONG_EDGE")

        if not r.gate_driver_active:
            action, stage = "WATCH_RESEARCH", "GATE_1_CAUSAL"
        elif not r.gate_edge_source_backed or not r.gate_positive_long_edge:
            action, stage = "WATCH_RESEARCH", "GATE_2_TRANSMISSION"
        elif r.stock_vs_etf_state == "UNRESOLVED_NO_ETF_MAP":
            b.append("ETF_EXPOSURE_MAP_MISSING")
            action, stage = "WATCH_RESEARCH", "GATE_3_STOCK_VS_ETF"
        elif r.stock_vs_etf_state == "STOCK_BLOCKED_WEAK_EDGE":
            b.append("STOCK_ALPHA_BLOCKED_WEAK_EDGE")
            action, stage = "ETF_CORE_RESEARCH", "GATE_3_STOCK_VS_ETF"
        elif r.reaction_state == "EXTENDED":
            b.append("CHASE_RISK_EXTENDED")
            action, stage = "NO_BUY_EXTENDED", "GATE_4_REACTION"
        elif r.reaction_state == "BROKEN":
            b.append("EXPECTED_TRANSMISSION_BROKEN")
            action, stage = "AVOID_BROKEN", "GATE_4_REACTION"
        elif r.entry_trigger_state in {"BREAKOUT_CONFIRMATION_TRIGGER", "PULLBACK_RECOVERY_TRIGGER"}:
            b.append("PORTFOLIO_RISK_NOT_YET_VALIDATED")
            if r.stock_vs_etf_state == "ETF_CORE_PREFERRED":
                action, stage = "ENTRY_TRIGGERED_ETF_RISK_PENDING", "GATE_6_RISK_PENDING"
            else:
                action, stage = "ENTRY_TRIGGERED_STOCK_RISK_PENDING", "GATE_6_RISK_PENDING"
        elif r.reaction_state in ENTRY_RESEARCH_STATES:
            b.append("WAIT_FOR_STATE_TRANSITION_ENTRY_TRIGGER")
            action, stage = "WATCH_ENTRY", "GATE_5_ENTRY"
        elif r.reaction_state == "PERSISTENT":
            b.append("INFORMATION_MAY_BE_PRICED")
            action, stage = "WATCH_ENTRY", "GATE_4_REACTION"
        else:
            b.append("REACTION_STATE_NOT_ENTRY_READY")
            action, stage = "WATCH_RESEARCH", "GATE_4_REACTION"
        actions.append(action); stages.append(stage); blockers.append(";".join(dict.fromkeys(b)))

    x["decision_stage"] = stages
    x["candidate_action"] = actions
    x["decision_blockers"] = blockers
    x["decision_contract_version"] = cfg.contract_version
    x["auto_trade_allowed"] = False

    sort_cols = [c for c in ["candidate_action", "research_priority_score"] if c in x.columns]
    if sort_cols:
        x = x.sort_values(sort_cols, ascending=[True, False][:len(sort_cols)])
    preferred = [
        "run_id", "decision_contract_version", "global_theme", "driver_id", "driver_label", "taiwan_code", "ticker", "name", "industry",
        "economic_role", "linkage_tier", "linkage_confidence", "polarity", "seed_provenance_status", "provenance_status", "edge_research_as_of_utc",
        "edge_source_count", "edge_source_summary", "edge_counter_evidence", "edge_source_urls", "dynamic_driver_state", "reaction_state",
        "previous_reaction_state", "entry_trigger_state", "etf_ticker", "etf_role", "exposure_purity", "comparison_policy", "stock_vs_etf_state",
        "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration", "keynes_v2", "gate_driver_active", "gate_edge_source_backed",
        "gate_positive_long_edge", "gate_not_extended", "gate_not_broken", "gate_entry_research_state", "decision_stage", "candidate_action",
        "decision_blockers", "auto_trade_allowed", "research_priority_score",
    ]
    return x[[c for c in preferred if c in x.columns]]


def build_decision_packet(board: pd.DataFrame, run_id: str, cfg: DecisionConfig = DecisionConfig()) -> dict:
    counts = board["candidate_action"].value_counts(dropna=False).to_dict() if not board.empty else {}
    focus_actions = {"WATCH_ENTRY", "ENTRY_TRIGGERED_STOCK_RISK_PENDING", "ENTRY_TRIGGERED_ETF_RISK_PENDING", "ETF_CORE_RESEARCH"}
    focus = board[board["candidate_action"].isin(focus_actions)].copy() if not board.empty else pd.DataFrame()
    cols = [c for c in ["global_theme", "driver_id", "taiwan_code", "ticker", "name", "reaction_state", "previous_reaction_state", "entry_trigger_state", "etf_ticker", "exposure_purity", "stock_vs_etf_state", "provenance_status", "dynamic_driver_state", "decision_stage", "candidate_action", "decision_blockers"] if c in focus.columns]
    return {
        "contract": "ALPHA_HUNTER_DECISION_PACKET",
        "decision_contract_version": cfg.contract_version,
        "run_id": run_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "gate_first_score_second": True,
        "price_can_create_causality": False,
        "auto_trade_allowed": False,
        "current_capability": "ETF_VS_STOCK_PLUS_STATE_TRANSITION_ENTRY",
        "missing_downstream_modules": ["PORTFOLIO_RISK_BUDGET", "EXISTING_POSITION_THESIS_LEDGER", "SHADOW_AUDIT_VALIDATION"],
        "action_counts": {str(k): int(v) for k, v in counts.items()},
        "decision_focus": focus[cols].head(100).to_dict(orient="records") if cols else [],
        "entry_rule": "Only a PRE_CONFIRMATION/EARLY_CONFIRMATION -> CONFIRMING transition, or PULLBACK -> CONFIRMING recovery, can create an entry trigger. No fixed momentum threshold is invented.",
        "rule": "No score can override causal/provenance/reaction gates. Entry triggers remain risk-pending until portfolio risk is implemented."
    }


def write_decision_outputs(structural_matches: pd.DataFrame, run_id: str, output_dir: str = "output") -> tuple[pd.DataFrame, dict]:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    history_path = out / "decision_history.csv"
    structural_matches = apply_previous_state(structural_matches, history_path)
    board = build_decision_board(structural_matches)
    board.to_csv(out / "decision_board.csv", index=False)
    packet = build_decision_packet(board, run_id)
    (out / "decision_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    if not board.empty:
        hist_cols = [c for c in ["run_id", "driver_id", "taiwan_code", "ticker", "name", "reaction_state", "candidate_action", "decision_stage", "stock_vs_etf_state", "entry_trigger_state"] if c in board.columns]
        snap = board[hist_cols].copy(); snap["recorded_at"] = datetime.now().astimezone().isoformat()
        if history_path.exists():
            old = pd.read_csv(history_path, dtype={"taiwan_code": str})
            hist = pd.concat([old, snap], ignore_index=True)
            hist = hist.drop_duplicates(["run_id", "driver_id", "taiwan_code"], keep="last")
        else:
            hist = snap
        hist.to_csv(history_path, index=False)
    return board, packet
