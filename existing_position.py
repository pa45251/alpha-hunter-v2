from __future__ import annotations

from typing import Any
import json
import os
import pandas as pd

from portfolio_risk import load_portfolio_state, load_risk_policy, validate_risk_inputs

RISK_GROUP_DRIVERS = {
    "AI_CAPEX": ["AI_SERVER_SHIPMENTS", "AI_SERVER_RACK_BUILD", "AI_SERVER_THERMAL_DENSITY", "DATACENTER_POWER_INFRA", "DATACENTER_COOLING_INFRA", "AI_NETWORKING_UPGRADE"],
    "SEMI_MEMORY": ["DRAM_PRICING", "SPECIALTY_MEMORY_PRICING", "MEMORY_IC_CYCLE", "NAND_STORAGE_CYCLE"],
    "SEMI_AI": ["LEADING_EDGE_FOUNDRY_AI_DEMAND", "ADVANCED_PACKAGING_TEST_CAPEX"],
    "SEMI_CYCLE": ["MATURE_NODE_FOUNDRY_UTILIZATION", "WAFER_FAB_EQUIPMENT_CAPEX"],
    "POWER_GRID": ["GRID_CAPEX", "POWER_ELECTRONICS_CAPEX"],
    "POWER_NUCLEAR": ["NUCLEAR_GRID_SECOND_ORDER"],
    "SHIPPING": ["CONTAINER_FREIGHT", "DRY_BULK_FREIGHT"],
    "CRITICAL_MATERIALS": ["COPPER_COMMODITY_TRADE_INVENTORY"],
    "CYBERSECURITY": ["ENTERPRISE_CYBER_SPEND"],
    "BIOTECH_RISK": ["BIOPHARMA_RISK_APPETITE", "GENOMICS_RISK_APPETITE"],
    "FINANCIALS": ["FINANCIALS_RATE_CREDIT_CYCLE"],
    "CONSUMER_TECH": ["CONSUMER_ELECTRONICS_CYCLE"],
}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if str(x).strip()]
    return []


def _ticker_key(v: Any) -> str:
    return str(v or "").strip().upper().replace(".TW", "").replace(".TWO", "")


def load_private_thesis_overlay() -> tuple[dict[str, dict[str, Any]], str]:
    """Load optional thesis-only Secret. No values are logged or persisted."""
    raw = os.getenv("ALPHA_HUNTER_POSITION_THESIS_JSON", "").strip()
    if not raw:
        return {}, "NOT_CONFIGURED"
    try:
        payload = json.loads(raw)
    except Exception:
        return {}, "INVALID_JSON"
    items = payload.get("positions", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return {}, "INVALID_SCHEMA"
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            return {}, "INVALID_SCHEMA"
        key = _ticker_key(item.get("ticker"))
        if not key:
            return {}, "INVALID_SCHEMA"
        drivers = [x.upper() for x in _list(item.get("thesis_driver_ids"))]
        status = str(item.get("thesis_status", "")).upper().strip()
        if not drivers and not status:
            return {}, "INVALID_SCHEMA"
        out[key] = {"thesis_driver_ids": list(dict.fromkeys(drivers)), "thesis_status": status}
    return out, "VALID"


def apply_private_thesis_overlay(portfolio: dict[str, Any], overlay: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], int]:
    p = dict(portfolio or {})
    positions = [dict(x) for x in (p.get("positions") or [])]
    applied = 0
    for pos in positions:
        item = overlay.get(_ticker_key(pos.get("ticker")))
        if not item:
            continue
        if item.get("thesis_driver_ids"):
            pos["thesis_driver_ids"] = item["thesis_driver_ids"]
        if item.get("thesis_status"):
            pos["thesis_status"] = item["thesis_status"]
        applied += 1
    p["positions"] = positions
    return p, applied


def _position_drivers(pos: dict[str, Any]) -> tuple[list[str], str]:
    explicit = _list(pos.get("thesis_driver_ids") or pos.get("thesis_drivers"))
    if explicit:
        return list(dict.fromkeys(x.upper() for x in explicit)), "EXPLICIT"
    inferred: list[str] = []
    for group in _list(pos.get("risk_groups")):
        inferred.extend(RISK_GROUP_DRIVERS.get(group.upper(), []))
    return list(dict.fromkeys(inferred)), "RISK_GROUP_INFERRED" if inferred else "MISSING"


def _pnl_pct(pos: dict[str, Any]) -> float | None:
    if pos.get("unrealized_pnl_pct") is not None:
        return _f(pos.get("unrealized_pnl_pct"))
    cost = pos.get("cost_basis_twd")
    mv = pos.get("market_value_twd")
    if cost is not None and mv is not None and _f(cost) > 0:
        return (_f(mv) / _f(cost) - 1.0) * 100.0
    return None


def evaluate_existing_positions(board: pd.DataFrame, policy: dict[str, Any], portfolio: dict[str, Any]) -> pd.DataFrame:
    """Evaluate private holdings in-memory. Returned rows are private and must never be committed/logged."""
    positions = portfolio.get("positions") or []
    if not positions:
        return pd.DataFrame(columns=["position_index", "action", "reason", "thesis_mapping"])

    b = board.copy() if board is not None else pd.DataFrame()
    if not b.empty:
        for c in ["driver_id", "dynamic_driver_state", "provenance_status", "polarity", "reaction_state"]:
            if c not in b.columns:
                b[c] = ""
            b[c] = b[c].fillna("").astype(str).str.upper()

    rows: list[dict[str, Any]] = []
    max_loss = _f(policy.get("max_position_loss_pct"), 0)
    for i, pos in enumerate(positions):
        drivers, mapping = _position_drivers(pos)
        matched = b[b["driver_id"].isin(drivers)] if drivers and not b.empty else pd.DataFrame()
        healthy = matched[
            matched["dynamic_driver_state"].eq("ACTIVE_RESEARCH_VALIDATED")
            & matched["provenance_status"].eq("SOURCE_BACKED")
            & matched["polarity"].eq("POSITIVE")
            & ~matched["reaction_state"].eq("BROKEN")
        ] if not matched.empty else pd.DataFrame()
        broken = matched[
            matched["dynamic_driver_state"].eq("ACTIVE_RESEARCH_VALIDATED")
            & matched["provenance_status"].eq("SOURCE_BACKED")
            & matched["reaction_state"].eq("BROKEN")
        ] if not matched.empty else pd.DataFrame()

        explicit_status = str(pos.get("thesis_status", "")).upper()
        pnl = _pnl_pct(pos)
        if explicit_status in {"INVALIDATED", "BROKEN"}:
            action, reason = "EXIT_THESIS", "PRIVATE_THESIS_EXPLICITLY_INVALIDATED"
            strength = 0
        elif pnl is not None and max_loss > 0 and pnl <= -max_loss:
            action, reason = "EXIT_RISK", "MAX_POSITION_LOSS_BREACHED"
            strength = 0
        elif not broken.empty and healthy.empty:
            action, reason = "EXIT_THESIS", "SOURCE_BACKED_TRANSMISSION_BROKEN"
            strength = 0
        elif not broken.empty and not healthy.empty:
            action, reason = "REDUCE_REVIEW", "MIXED_THESIS_SIGNALS"
            strength = 1
        elif not healthy.empty:
            action, reason = "HOLD", "THESIS_ACTIVE_SOURCE_BACKED"
            strength = 3
        elif mapping == "MISSING":
            action, reason = "REVIEW_THESIS", "THESIS_MAPPING_MISSING"
            strength = 1
        elif matched.empty:
            action, reason = "REVIEW_THESIS", "THESIS_DRIVER_NOT_ON_DECISION_BOARD"
            strength = 1
        else:
            action, reason = "REVIEW_THESIS", "THESIS_NOT_RESEARCH_VALIDATED"
            strength = 2

        rows.append({
            "position_index": i,
            "action": action,
            "reason": reason,
            "thesis_mapping": mapping,
            "thesis_strength": strength,
            "weight_pct": _f(pos.get("weight_pct"), 0),
        })

    out = pd.DataFrame(rows)
    current_gross = _f(portfolio.get("gross_exposure_pct"), 0)
    max_gross = _f(policy.get("max_gross_exposure_pct"), 0)
    excess = max(0.0, current_gross - max_gross) if max_gross > 0 else 0.0
    if excess > 0 and not out.empty:
        candidates = out[~out["action"].isin({"EXIT_THESIS", "EXIT_RISK"})].sort_values(
            ["thesis_strength", "weight_pct"], ascending=[True, False]
        )
        covered = 0.0
        for idx, r in candidates.iterrows():
            if covered >= excess:
                break
            out.at[idx, "action"] = "REDUCE_RISK"
            out.at[idx, "reason"] = "PORTFOLIO_GROSS_EXPOSURE_ABOVE_POLICY"
            covered += max(0.0, _f(r.get("weight_pct")))
    return out


def apply_existing_position_engine(board: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run private exit/hold logic and expose only aggregate, non-identifying metadata."""
    policy = load_risk_policy()
    raw_portfolio = load_portfolio_state()
    valid, blockers, portfolio = validate_risk_inputs(policy, raw_portfolio)
    overlay, overlay_status = load_private_thesis_overlay()
    if overlay_status in {"INVALID_JSON", "INVALID_SCHEMA"}:
        valid = False
        blockers = list(blockers) + [f"POSITION_THESIS_OVERLAY_{overlay_status}"]
    applied = 0
    if valid and overlay:
        portfolio, applied = apply_private_thesis_overlay(portfolio, overlay)
    if not valid:
        return pd.DataFrame(), {
            "position_inputs_valid": False,
            "position_blockers": blockers,
            "position_action_counts": {},
            "thesis_overlay_status": overlay_status,
            "privacy_rule": "Per-position actions and holdings stay in-memory and are never committed or logged.",
        }
    private_actions = evaluate_existing_positions(board, policy, portfolio)
    counts = private_actions["action"].value_counts(dropna=False).to_dict() if not private_actions.empty else {}
    mapping_counts = private_actions["thesis_mapping"].value_counts(dropna=False).to_dict() if not private_actions.empty else {}
    return private_actions, {
        "position_inputs_valid": True,
        "position_blockers": [],
        "position_action_counts": {str(k): int(v) for k, v in counts.items()},
        "thesis_mapping_counts": {str(k): int(v) for k, v in mapping_counts.items()},
        "thesis_overlay_status": overlay_status,
        "thesis_overlay_applied_count": int(applied),
        "private_position_details_committed": False,
        "privacy_rule": "Per-position actions, tickers, balances, weights and P/L stay in-memory and are never committed or logged.",
    }
