from __future__ import annotations

import math
from typing import Any

import pandas as pd

from portfolio_risk import (
    DRIVER_RISK_GROUP,
    REQUIRED_POLICY_FIELDS,
    _current_group_exposure,
    _current_ticker_weight,
    _normalise_portfolio,
    load_portfolio_state,
    load_risk_policy,
)

CONTRACT = "ALPHA_HUNTER_PORTFOLIO_RISK_V2"


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _require_finite(blockers: list[str], obj: dict[str, Any], field: str, prefix: str, *, min_value: float | None = None, max_value: float | None = None) -> None:
    if obj.get(field) is None:
        blockers.append(f"{prefix}_FIELD_MISSING:{field}")
        return
    x = _num(obj.get(field))
    if x is None:
        blockers.append(f"{prefix}_FIELD_NONFINITE:{field}")
        return
    if min_value is not None and x < min_value:
        blockers.append(f"{prefix}_FIELD_BELOW_MIN:{field}")
    if max_value is not None and x > max_value:
        blockers.append(f"{prefix}_FIELD_ABOVE_MAX:{field}")


def validate_risk_inputs_v2(policy: dict[str, Any], portfolio: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    blockers: list[str] = []
    if not policy:
        blockers.append("RISK_POLICY_MISSING")
    else:
        for field in REQUIRED_POLICY_FIELDS:
            _require_finite(blockers, policy, field, "RISK_POLICY", min_value=0.0)
        if policy.get("policy_version") is None:
            blockers.append("RISK_POLICY_FIELD_MISSING:policy_version")

    if not portfolio:
        blockers.append("PORTFOLIO_STATE_MISSING")
        return False, blockers, {}

    # Reject non-finite private balances before v1 normalization can coerce them to defaults.
    for field in ["market_value_twd", "financing_debt_twd", "cash_twd"]:
        if portfolio.get(field) is not None:
            _require_finite(blockers, portfolio, field, "PORTFOLIO", min_value=0.0)

    supplied_gross = portfolio.get("gross_exposure_pct")
    if supplied_gross is not None and _num(supplied_gross) is None:
        blockers.append("PORTFOLIO_FIELD_NONFINITE:gross_exposure_pct")

    normalized, normalise_blockers = _normalise_portfolio(dict(portfolio))
    blockers.extend(normalise_blockers)
    _require_finite(blockers, normalized, "gross_exposure_pct", "PORTFOLIO", min_value=0.0)

    positions = normalized.get("positions")
    if positions is None:
        blockers.append("PORTFOLIO_FIELD_MISSING:positions")
    elif not isinstance(positions, list):
        blockers.append("PORTFOLIO_FIELD_INVALID:positions")
    else:
        for i, pos in enumerate(positions):
            if not isinstance(pos, dict):
                blockers.append(f"PORTFOLIO_POSITION_INVALID:{i}")
                continue
            if pos.get("market_value_twd") is not None and _num(pos.get("market_value_twd")) is None:
                blockers.append(f"PORTFOLIO_POSITION_NONFINITE_MARKET_VALUE:{i}")
            if pos.get("weight_pct") is not None and _num(pos.get("weight_pct")) is None:
                blockers.append(f"PORTFOLIO_POSITION_NONFINITE_WEIGHT:{i}")

    blockers = list(dict.fromkeys(blockers))
    return len(blockers) == 0, blockers, normalized


def apply_entry_risk_gate_v2(board: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fail-closed risk gate for V2 entry plans.

    Missing/zero/non-finite turnover is a blocker rather than permission. This module does not
    alter frozen V1; it is consumed only by V2 advisory/entry/rotation paths.
    """
    if board is None or board.empty:
        return board, {
            "contract": CONTRACT,
            "risk_inputs_valid": False,
            "risk_blockers": ["EMPTY_ENTRY_PLAN_BOARD"],
        }

    policy = load_risk_policy()
    raw_portfolio = load_portfolio_state()
    valid, global_blockers, portfolio = validate_risk_inputs_v2(policy, raw_portfolio)

    x = board.copy()
    x["risk_v2_pass"] = False
    x["risk_v2_blockers"] = ""
    x["risk_policy_version"] = str(policy.get("policy_version", "")) if policy else ""

    for idx, r in x.iterrows():
        blockers = list(global_blockers)
        if not bool(r.get("entry_structure_valid", False)):
            blockers.append("ENTRY_STRUCTURE_NOT_VALID")

        if valid:
            ticker = str(r.get("ticker", ""))
            driver_id = str(r.get("driver_id", ""))
            risk_group = DRIVER_RISK_GROUP.get(driver_id, "")
            current_gross = _num(portfolio.get("gross_exposure_pct"))
            proposed = _num(policy.get("max_new_position_pct"))
            gross_cap = _num(policy.get("max_gross_exposure_pct"))
            theme_cap = _num(policy.get("max_theme_exposure_pct"))
            single_cap = _num(policy.get("max_single_position_pct"))
            min_turnover = _num(policy.get("min_avg_turnover_twd"))
            avg_turnover = _num(r.get("avg_turnover20_twd"))

            if None in {current_gross, proposed, gross_cap, theme_cap, single_cap, min_turnover}:
                blockers.append("RISK_NUMERIC_INPUT_INVALID")
            else:
                current_group = _current_group_exposure(portfolio, risk_group)
                current_ticker = _current_ticker_weight(portfolio, ticker)
                if current_gross > gross_cap:
                    blockers.append("PORTFOLIO_ALREADY_OVER_MAX_GROSS")
                elif current_gross + proposed > gross_cap:
                    blockers.append("MAX_GROSS_EXPOSURE")
                if risk_group and current_group + proposed > theme_cap:
                    blockers.append("MAX_THEME_EXPOSURE")
                if current_ticker + proposed > single_cap:
                    blockers.append("MAX_SINGLE_POSITION")

            # B01: absence, NaN, inf and non-positive turnover all fail closed.
            if avg_turnover is None or avg_turnover <= 0:
                blockers.append("LIQUIDITY_DATA_MISSING_OR_INVALID")
            elif min_turnover is not None and avg_turnover < min_turnover:
                blockers.append("LIQUIDITY_BELOW_POLICY")

        blockers = list(dict.fromkeys(blockers))
        x.at[idx, "risk_v2_pass"] = len(blockers) == 0
        x.at[idx, "risk_v2_blockers"] = ";".join(blockers)

    meta = {
        "contract": CONTRACT,
        "schema_version": "2.0",
        "risk_inputs_valid": valid,
        "risk_blockers": global_blockers,
        "risk_policy_version": str(policy.get("policy_version", "")) if policy else "",
        "missing_liquidity_fails_closed": True,
        "nonfinite_numeric_inputs_fail_closed": True,
        "auto_order_execution": False,
    }
    return x, meta
