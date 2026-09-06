from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json

import pandas as pd


@dataclass(frozen=True)
class DecisionConfig:
    contract_version: str = "2.7.0"
    source_backed_value: str = "SOURCE_BACKED"
    edge_research_max_age_days: int = 120


ENTRY_RESEARCH_STATES = {"PRE_CONFIRMATION", "EARLY_CONFIRMATION", "CONFIRMING", "PULLBACK"}


def _normalize_code(v) -> str:
    return str(v).strip().split(".")[0].zfill(4)


def apply_edge_provenance(
    structural_matches: pd.DataFrame,
    path: Path,
    cfg: DecisionConfig = DecisionConfig(),
) -> pd.DataFrame:
    """Apply a research overlay without mutating the canonical seed exposure graph.

    Only existing (driver_id, taiwan_code) edges may be upgraded. The overlay cannot create a new
    structural relationship. This keeps the slow-moving graph and time-stamped research evidence separate.
    """
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
    overlay_cols = [
        "driver_id", "taiwan_code", "provenance_status", "as_of_utc", "source_count",
        "source_summary", "counter_evidence", "source_urls", "edge_research_valid"
    ]
    overlay_cols = [c for c in overlay_cols if c in e.columns]
    e = e[overlay_cols].rename(columns={
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


def build_decision_board(structural_matches: pd.DataFrame, cfg: DecisionConfig = DecisionConfig()) -> pd.DataFrame:
    """Build the deterministic Research -> Decision bridge.

    This module intentionally does NOT invent ETF mappings, entry thresholds, position sizes,
    stops, or portfolio-risk limits. Until those downstream modules are validated, the strongest
    permissible new-candidate output is WATCH_ENTRY.
    """
    if structural_matches is None or structural_matches.empty:
        return pd.DataFrame()

    x = structural_matches.copy()
    for c in ["driver_id", "dynamic_driver_state", "provenance_status", "reaction_state", "polarity"]:
        if c not in x.columns:
            x[c] = ""
        x[c] = x[c].fillna("").astype(str).str.upper()

    x["gate_driver_active"] = x["dynamic_driver_state"].eq("ACTIVE_RESEARCH_VALIDATED")
    x["gate_edge_source_backed"] = x["provenance_status"].eq(cfg.source_backed_value)
    x["gate_positive_long_edge"] = x["polarity"].eq("POSITIVE")
    x["gate_not_extended"] = ~x["reaction_state"].eq("EXTENDED")
    x["gate_not_broken"] = ~x["reaction_state"].eq("BROKEN")
    x["gate_entry_research_state"] = x["reaction_state"].isin(ENTRY_RESEARCH_STATES)

    actions = []
    stages = []
    blockers = []
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
        elif not r.gate_edge_source_backed:
            action, stage = "WATCH_RESEARCH", "GATE_2_TRANSMISSION"
        elif not r.gate_positive_long_edge:
            action, stage = "WATCH_RESEARCH", "GATE_2_TRANSMISSION"
        elif r.reaction_state == "EXTENDED":
            b.append("CHASE_RISK_EXTENDED")
            action, stage = "NO_BUY_EXTENDED", "GATE_4_REACTION"
        elif r.reaction_state == "BROKEN":
            b.append("EXPECTED_TRANSMISSION_BROKEN")
            action, stage = "AVOID_BROKEN", "GATE_4_REACTION"
        elif r.reaction_state in ENTRY_RESEARCH_STATES:
            b.extend(["ETF_VS_STOCK_NOT_YET_VALIDATED", "ENTRY_TRIGGER_NOT_YET_VALIDATED"])
            action, stage = "WATCH_ENTRY", "GATE_3_TO_5_PENDING"
        elif r.reaction_state == "PERSISTENT":
            b.extend(["INFORMATION_MAY_BE_PRICED", "ETF_VS_STOCK_NOT_YET_VALIDATED"])
            action, stage = "WATCH_ENTRY", "GATE_3_STOCK_VS_ETF"
        else:
            b.append("REACTION_STATE_NOT_ENTRY_READY")
            action, stage = "WATCH_RESEARCH", "GATE_4_REACTION"

        actions.append(action)
        stages.append(stage)
        blockers.append(";".join(dict.fromkeys(b)))

    x["decision_stage"] = stages
    x["candidate_action"] = actions
    x["decision_blockers"] = blockers
    x["decision_contract_version"] = cfg.contract_version
    x["auto_trade_allowed"] = False

    sort_cols = [c for c in ["candidate_action", "research_priority_score"] if c in x.columns]
    if sort_cols:
        x = x.sort_values(sort_cols, ascending=[True, False][: len(sort_cols)])

    preferred = [
        "run_id", "decision_contract_version", "global_theme", "driver_id", "driver_label",
        "taiwan_code", "ticker", "name", "industry", "economic_role", "linkage_tier",
        "linkage_confidence", "seed_provenance_status", "provenance_status", "edge_research_as_of_utc",
        "edge_source_count", "edge_source_summary", "edge_counter_evidence", "edge_source_urls",
        "dynamic_driver_state", "reaction_state", "rs_20d_vs_bench", "rs_60d_vs_bench", "acceleration", "keynes_v2",
        "gate_driver_active", "gate_edge_source_backed", "gate_positive_long_edge",
        "gate_not_extended", "gate_not_broken", "gate_entry_research_state",
        "decision_stage", "candidate_action", "decision_blockers", "auto_trade_allowed",
        "research_priority_score",
    ]
    preferred = [c for c in preferred if c in x.columns]
    return x[preferred]


def build_decision_packet(board: pd.DataFrame, run_id: str, cfg: DecisionConfig = DecisionConfig()) -> dict:
    counts = board["candidate_action"].value_counts(dropna=False).to_dict() if not board.empty else {}
    entry = board[board["candidate_action"].eq("WATCH_ENTRY")].copy() if not board.empty else pd.DataFrame()
    cols = [c for c in [
        "global_theme", "driver_id", "taiwan_code", "ticker", "name", "reaction_state",
        "provenance_status", "dynamic_driver_state", "decision_stage", "candidate_action", "decision_blockers"
    ] if c in entry.columns]
    return {
        "contract": "ALPHA_HUNTER_DECISION_PACKET",
        "decision_contract_version": cfg.contract_version,
        "run_id": run_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "gate_first_score_second": True,
        "price_can_create_causality": False,
        "auto_trade_allowed": False,
        "current_capability": "RESEARCH_TO_DECISION_BRIDGE",
        "missing_downstream_modules": [
            "ETF_EXPOSURE_PURITY_AND_STOCK_VS_ETF",
            "VALIDATED_ENTRY_TRIGGER",
            "PORTFOLIO_RISK_BUDGET",
            "EXISTING_POSITION_THESIS_LEDGER",
            "SHADOW_AUDIT_VALIDATION",
        ],
        "action_counts": {str(k): int(v) for k, v in counts.items()},
        "watch_entry_candidates": entry[cols].head(50).to_dict(orient="records") if cols else [],
        "rule": (
            "No score can override a failed causal/provenance/reaction gate. "
            "Until ETF-vs-stock, entry, and risk modules are validated, code cannot emit automatic BUY/SELL actions."
        ),
    }


def write_decision_outputs(structural_matches: pd.DataFrame, run_id: str, output_dir: str = "output") -> tuple[pd.DataFrame, dict]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    board = build_decision_board(structural_matches)
    board.to_csv(out / "decision_board.csv", index=False)
    packet = build_decision_packet(board, run_id)
    (out / "decision_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return board, packet
