from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    policy_version: str = "1.1"
    gross_tolerance_pct: float = 1.0


REQUIRED_POLICY_FIELDS = [
    "max_single_position_pct",
    "max_theme_exposure_pct",
    "max_gross_exposure_pct",
    "max_new_position_pct",
    "min_avg_turnover_twd",
    "max_position_loss_pct",
]

# Candidate drivers are grouped into portfolio-level correlated risk buckets.
# A position may belong to several risk_groups at once. This is deliberately
# conservative: overlapping economic exposures should not disappear merely
# because a position has one primary label.
DRIVER_RISK_GROUP = {
    "AI_SERVER_SHIPMENTS": "AI_CAPEX",
    "AI_SERVER_RACK_BUILD": "AI_CAPEX",
    "AI_SERVER_THERMAL_DENSITY": "AI_CAPEX",
    "DATACENTER_POWER_INFRA": "AI_CAPEX",
    "DATACENTER_COOLING_INFRA": "AI_CAPEX",
    "AI_NETWORKING_UPGRADE": "AI_CAPEX",
    "DRAM_PRICING": "SEMI_MEMORY",
    "SPECIALTY_MEMORY_PRICING": "SEMI_MEMORY",
    "MEMORY_IC_CYCLE": "SEMI_MEMORY",
    "NAND_STORAGE_CYCLE": "SEMI_MEMORY",
    "LEADING_EDGE_FOUNDRY_AI_DEMAND": "SEMI_AI",
    "MATURE_NODE_FOUNDRY_UTILIZATION": "SEMI_CYCLE",
    "WAFER_FAB_EQUIPMENT_CAPEX": "SEMI_CYCLE",
    "ADVANCED_PACKAGING_TEST_CAPEX": "SEMI_AI",
    "GRID_CAPEX": "POWER_GRID",
    "POWER_ELECTRONICS_CAPEX": "POWER_GRID",
    "NUCLEAR_GRID_SECOND_ORDER": "POWER_NUCLEAR",
    "CONTAINER_FREIGHT": "SHIPPING",
    "DRY_BULK_FREIGHT": "SHIPPING",
    "COPPER_COMMODITY_TRADE_INVENTORY": "CRITICAL_MATERIALS",
    "ENTERPRISE_CYBER_SPEND": "CYBERSECURITY",
    "BIOPHARMA_RISK_APPETITE": "BIOTECH_RISK",
    "GENOMICS_RISK_APPETITE": "BIOTECH_RISK",
    "FINANCIALS_RATE_CREDIT_CYCLE": "FINANCIALS",
    "CONSUMER_ELECTRONICS_CYCLE": "CONSUMER_TECH",
}


def _load_json_path_or_env(path: Path, env_name: str) -> dict[str, Any]:
    raw = os.getenv(env_name, "").strip()
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return {}
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_risk_policy() -> dict[str, Any]:
    return _load_json_path_or_env(Path("input/risk_policy.json"), "ALPHA_HUNTER_RISK_POLICY_JSON")


def load_portfolio_state() -> dict[str, Any]:
    return _load_json_path_or_env(Path("input/portfolio_state.json"), "ALPHA_HUNTER_PORTFOLIO_JSON")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _normalise_portfolio(portfolio: dict[str, Any], cfg: RiskConfig = RiskConfig()) -> tuple[dict[str, Any], list[str]]:
    """Derive net equity / gross exposure / position weights from private market values.

    The public decision output never receives these values. They are kept in-memory only.
    Legacy input containing only gross_exposure_pct + positions remains supported.
    """
    p = dict(portfolio or {})
    blockers: list[str] = []

    mv = p.get("market_value_twd")
    debt = p.get("financing_debt_twd")
    cash = p.get("cash_twd")
    positions = p.get("positions") or []

    if mv is not None and debt is not None and cash is not None:
        market_value = _f(mv)
        financing_debt = _f(debt)
        cash_value = _f(cash)
        net_equity = market_value + cash_value - financing_debt
        if market_value < 0 or financing_debt < 0 or cash_value < 0:
            blockers.append("PORTFOLIO_NEGATIVE_BALANCE")
        if net_equity <= 0:
            blockers.append("PORTFOLIO_NET_EQUITY_NONPOSITIVE")
        else:
            computed_gross = market_value / net_equity * 100.0
            supplied_gross = p.get("gross_exposure_pct")
            if supplied_gross is not None and abs(_f(supplied_gross) - computed_gross) > cfg.gross_tolerance_pct:
                blockers.append("PORTFOLIO_GROSS_EXPOSURE_MISMATCH")
            p["net_equity_twd"] = net_equity
            p["gross_exposure_pct"] = computed_gross

            total_position_mv = 0.0
            for pos in positions:
                if pos.get("market_value_twd") is not None:
                    pmv = _f(pos.get("market_value_twd"))
                    total_position_mv += pmv
                    pos["weight_pct"] = pmv / net_equity * 100.0
            if total_position_mv > 0 and abs(total_position_mv - market_value) > max(1000.0, market_value * 0.001):
                blockers.append("PORTFOLIO_POSITION_MARKET_VALUE_MISMATCH")

    p["positions"] = positions
    return p, blockers


def validate_risk_inputs(policy: dict[str, Any], portfolio: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    blockers: list[str] = []
    if not policy:
        blockers.append("RISK_POLICY_MISSING")
    else:
        for f in REQUIRED_POLICY_FIELDS:
            if policy.get(f) is None:
                blockers.append(f"RISK_POLICY_FIELD_MISSING:{f}")

    if not portfolio:
        blockers.append("PORTFOLIO_STATE_MISSING")
        return False, blockers, {}

    portfolio, normalise_blockers = _normalise_portfolio(portfolio)
    blockers.extend(normalise_blockers)
    if portfolio.get("gross_exposure_pct") is None:
        blockers.append("PORTFOLIO_FIELD_MISSING:gross_exposure_pct")
    if portfolio.get("positions") is None:
        blockers.append("PORTFOLIO_FIELD_MISSING:positions")

    return (len(blockers) == 0), blockers, portfolio


def _position_risk_groups(pos: dict[str, Any]) -> set[str]:
    groups = pos.get("risk_groups", [])
    if isinstance(groups, str):
        groups = [groups]
    return {str(g).upper() for g in groups if str(g).strip()}


def _current_group_exposure(portfolio: dict[str, Any], risk_group: str) -> float:
    total = 0.0
    target = str(risk_group or "").upper()
    if not target:
        return total
    for pos in portfolio.get("positions", []) or []:
        if target in _position_risk_groups(pos):
            total += _f(pos.get("weight_pct", 0))
    return total


def _ticker_key(v: Any) -> str:
    return str(v or "").upper().replace(".TW", "").replace(".TWO", "")


def _current_ticker_weight(portfolio: dict[str, Any], ticker: str) -> float:
    target = _ticker_key(ticker)
    total = 0.0
    for pos in portfolio.get("positions", []) or []:
        if _ticker_key(pos.get("ticker")) == target:
            total += _f(pos.get("weight_pct", 0))
    return total


def apply_portfolio_risk_gate(board: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply private portfolio constraints without exposing holdings to public outputs.

    This function never submits orders. It can only upgrade an already-triggered research candidate
    when explicit private inputs are complete. Private holdings, balances, weights, risk groups and
    derived portfolio metrics are never copied into public decision outputs or logs.
    """
    if board is None or board.empty:
        return board, {"risk_inputs_valid": False, "risk_blockers": ["EMPTY_DECISION_BOARD"]}

    policy = load_risk_policy()
    raw_portfolio = load_portfolio_state()
    valid, global_blockers, portfolio = validate_risk_inputs(policy, raw_portfolio)

    x = board.copy()
    x["risk_policy_version"] = str(policy.get("policy_version", "")) if policy else ""
    x["risk_gate_pass"] = False
    x["risk_blockers"] = ""
    x["portfolio_action"] = x.get("candidate_action", "WATCH_RESEARCH")

    for idx, r in x.iterrows():
        blockers = list(global_blockers)
        action = str(r.get("candidate_action", ""))
        if action != "ENTRY_TRIGGERED_STOCK_RISK_PENDING":
            blockers.append("NO_ENTRY_TRIGGER")
            x.at[idx, "risk_blockers"] = ";".join(dict.fromkeys(blockers))
            continue

        if valid:
            ticker = str(r.get("ticker", ""))
            driver_id = str(r.get("driver_id", ""))
            risk_group = DRIVER_RISK_GROUP.get(driver_id, "")
            current_gross = _f(portfolio.get("gross_exposure_pct"))
            current_group = _current_group_exposure(portfolio, risk_group)
            current_ticker = _current_ticker_weight(portfolio, ticker)
            proposed = _f(policy.get("max_new_position_pct"))
            avg_turnover = _f(r.get("avg_turnover20_twd", 0))

            if current_gross > _f(policy["max_gross_exposure_pct"]):
                blockers.append("PORTFOLIO_ALREADY_OVER_MAX_GROSS")
            elif current_gross + proposed > _f(policy["max_gross_exposure_pct"]):
                blockers.append("MAX_GROSS_EXPOSURE")
            if risk_group and current_group + proposed > _f(policy["max_theme_exposure_pct"]):
                blockers.append("MAX_THEME_EXPOSURE")
            if current_ticker + proposed > _f(policy["max_single_position_pct"]):
                blockers.append("MAX_SINGLE_POSITION")
            if avg_turnover and avg_turnover < _f(policy["min_avg_turnover_twd"]):
                blockers.append("LIQUIDITY_BELOW_POLICY")

        if not blockers:
            x.at[idx, "risk_gate_pass"] = True
            x.at[idx, "portfolio_action"] = "BUY_STOCK"
        else:
            x.at[idx, "portfolio_action"] = "WATCH_ENTRY"
        x.at[idx, "risk_blockers"] = ";".join(dict.fromkeys(blockers))

    meta: dict[str, Any] = {
        "risk_inputs_valid": valid,
        "risk_blockers": global_blockers,
        "risk_policy_version": str(policy.get("policy_version", "")) if policy else "",
        "auto_order_execution": False,
        "privacy_rule": "Private holdings/balances/weights/risk groups and derived metrics are consumed in-memory only and never committed or printed.",
    }
    return x, meta
