from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    policy_version: str = "1.0"


REQUIRED_POLICY_FIELDS = [
    "max_single_position_pct",
    "max_theme_exposure_pct",
    "max_gross_exposure_pct",
    "max_new_position_pct",
    "min_avg_turnover_twd",
    "max_position_loss_pct",
]


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


def validate_risk_inputs(policy: dict[str, Any], portfolio: dict[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not policy:
        blockers.append("RISK_POLICY_MISSING")
    else:
        for f in REQUIRED_POLICY_FIELDS:
            if policy.get(f) is None:
                blockers.append(f"RISK_POLICY_FIELD_MISSING:{f}")
    if not portfolio:
        blockers.append("PORTFOLIO_STATE_MISSING")
    else:
        if portfolio.get("gross_exposure_pct") is None:
            blockers.append("PORTFOLIO_FIELD_MISSING:gross_exposure_pct")
        if portfolio.get("positions") is None:
            blockers.append("PORTFOLIO_FIELD_MISSING:positions")
    return (len(blockers) == 0), blockers


def _current_theme_exposure(portfolio: dict[str, Any], theme: str) -> float:
    total = 0.0
    for p in portfolio.get("positions", []) or []:
        if str(p.get("theme", "")) == str(theme):
            try:
                total += float(p.get("weight_pct", 0) or 0)
            except Exception:
                pass
    return total


def _current_ticker_weight(portfolio: dict[str, Any], ticker: str) -> float:
    for p in portfolio.get("positions", []) or []:
        if str(p.get("ticker", "")) == str(ticker):
            try:
                return float(p.get("weight_pct", 0) or 0)
            except Exception:
                return 0.0
    return 0.0


def apply_portfolio_risk_gate(board: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply private user-defined portfolio risk constraints.

    This function never submits orders. It can only upgrade an already-triggered research candidate
    to a portfolio-decision state when explicit private risk inputs are available and complete.
    """
    if board is None or board.empty:
        return board, {"risk_inputs_valid": False, "risk_blockers": ["EMPTY_DECISION_BOARD"]}

    policy = load_risk_policy()
    portfolio = load_portfolio_state()
    valid, global_blockers = validate_risk_inputs(policy, portfolio)

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
            theme = str(r.get("global_theme", ""))
            try:
                current_gross = float(portfolio.get("gross_exposure_pct", 0) or 0)
                current_theme = _current_theme_exposure(portfolio, theme)
                current_ticker = _current_ticker_weight(portfolio, ticker)
                proposed = float(policy["max_new_position_pct"])
                avg_turnover = float(r.get("avg_turnover20_twd", 0) or 0)

                if current_gross + proposed > float(policy["max_gross_exposure_pct"]):
                    blockers.append("MAX_GROSS_EXPOSURE")
                if current_theme + proposed > float(policy["max_theme_exposure_pct"]):
                    blockers.append("MAX_THEME_EXPOSURE")
                if current_ticker + proposed > float(policy["max_single_position_pct"]):
                    blockers.append("MAX_SINGLE_POSITION")
                if avg_turnover and avg_turnover < float(policy["min_avg_turnover_twd"]):
                    blockers.append("LIQUIDITY_BELOW_POLICY")
            except Exception:
                blockers.append("RISK_EVALUATION_ERROR")

        if not blockers:
            x.at[idx, "risk_gate_pass"] = True
            x.at[idx, "portfolio_action"] = "BUY_STOCK"
        else:
            x.at[idx, "portfolio_action"] = "WATCH_ENTRY"
        x.at[idx, "risk_blockers"] = ";".join(dict.fromkeys(blockers))

    meta = {
        "risk_inputs_valid": valid,
        "risk_blockers": global_blockers,
        "risk_policy_version": str(policy.get("policy_version", "")) if policy else "",
        "auto_order_execution": False,
        "privacy_rule": "Portfolio holdings and personal risk settings must not be committed to the public repository.",
    }
    return x, meta
