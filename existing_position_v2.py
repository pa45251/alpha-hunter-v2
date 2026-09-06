from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

import existing_position as legacy
from portfolio_risk import load_portfolio_state, load_risk_policy, validate_risk_inputs

CONTRACT_VERSION = "EXISTING_POSITION_V2"
BROKEN_EXIT_REASON = "SYSTEM_THESIS_SOURCE_BACKED_TRANSMISSION_BROKEN"
BROKEN_REVIEW_REASON = "SYSTEM_THESIS_TRANSMISSION_BROKEN_REQUIRES_PERSISTENCE_CONFIRMATION"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _apply_gross_reduction(out: pd.DataFrame, policy: dict[str, Any], portfolio: dict[str, Any]) -> pd.DataFrame:
    """Re-apply portfolio gross-risk reduction after the contract correction.

    V1 could count a one-snapshot BROKEN transmission as an EXIT and therefore as already
    covering excess gross exposure. V2 first converts that false thesis exit into REVIEW,
    then independently nominates risk reductions if gross exposure still exceeds policy.
    """
    if out is None or out.empty:
        return out
    x = out.copy()
    current_gross = _f(portfolio.get("gross_exposure_pct"), 0)
    max_gross = _f(policy.get("max_gross_exposure_pct"), 0)
    excess = max(0.0, current_gross - max_gross) if max_gross > 0 else 0.0
    if excess <= 0:
        return x

    exits = x["action"].isin({"EXIT_THESIS", "EXIT_RISK"})
    covered = float(x.loc[exits, "weight_pct"].clip(lower=0).sum())
    candidates = x[~exits].sort_values(["thesis_strength", "weight_pct"], ascending=[True, False])
    for idx, row in candidates.iterrows():
        if covered >= excess:
            break
        x.at[idx, "action"] = "REDUCE_RISK"
        x.at[idx, "reason"] = "PORTFOLIO_GROSS_EXPOSURE_ABOVE_POLICY"
        covered += max(0.0, _f(row.get("weight_pct")))
    return x


def evaluate_existing_positions(
    board: pd.DataFrame,
    policy: dict[str, Any],
    portfolio: dict[str, Any],
    maintenance_states: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Contract-safe V2 evaluation.

    A BROKEN reaction while the causal driver is still ACTIVE is a falsification warning,
    not sufficient proof of thesis death. It requires persistence/company-transmission
    confirmation before a thesis exit. Causal INACTIVE and explicit risk-loss exits remain exits.
    """
    # Suppress V1's gross-overlay temporarily so we can correct thesis actions first.
    p = dict(portfolio or {})
    original_gross = _f(p.get("gross_exposure_pct"), 0)
    max_gross = _f(policy.get("max_gross_exposure_pct"), 0)
    if max_gross > 0 and original_gross > max_gross:
        p["gross_exposure_pct"] = max_gross

    out = legacy.evaluate_existing_positions(board, policy, p, maintenance_states)
    if out is None or out.empty:
        return out

    x = out.copy()
    mask = x["reason"].astype(str).eq(BROKEN_EXIT_REASON)
    x.loc[mask, "action"] = "REVIEW_RESEARCH"
    x.loc[mask, "reason"] = BROKEN_REVIEW_REASON
    x.loc[mask, "thesis_strength"] = 1

    return _apply_gross_reduction(x, policy, portfolio)


def apply_existing_position_engine(board: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    policy = load_risk_policy()
    raw_portfolio = load_portfolio_state()
    valid, blockers, portfolio = validate_risk_inputs(policy, raw_portfolio)
    overlay, overlay_status = legacy.load_private_thesis_overlay()
    if overlay_status in {"INVALID_JSON", "INVALID_SCHEMA"}:
        valid = False
        blockers = list(blockers) + [f"POSITION_THESIS_OVERLAY_{overlay_status}"]
    applied = 0
    if valid and overlay:
        portfolio, applied = legacy.apply_private_thesis_overlay(portfolio, overlay)
    if not valid:
        return pd.DataFrame(), {
            "position_inputs_valid": False,
            "position_blockers": blockers,
            "position_action_counts": {},
            "system_mapping_counts": {},
            "user_thesis_overlay_status": overlay_status,
            "existing_position_contract": CONTRACT_VERSION,
            "privacy_rule": "Per-position actions and holdings stay in-memory and are never committed or logged.",
        }

    private_actions = evaluate_existing_positions(board, policy, portfolio)
    counts = Counter(private_actions["action"].astype(str)) if not private_actions.empty else Counter()
    mappings = Counter(private_actions["thesis_mapping"].astype(str)) if not private_actions.empty else Counter()
    disagreement_count = int(private_actions.get("user_thesis_disagrees", pd.Series(dtype=bool)).fillna(False).sum()) if not private_actions.empty else 0
    return private_actions, {
        "position_inputs_valid": True,
        "position_blockers": [],
        "position_action_counts": {str(k): int(v) for k, v in counts.items()},
        "system_mapping_counts": {str(k): int(v) for k, v in mappings.items()},
        "user_thesis_overlay_status": overlay_status,
        "user_thesis_overlay_applied_count": int(applied),
        "user_thesis_disagreement_count": disagreement_count,
        "system_thesis_primary": True,
        "existing_position_contract": CONTRACT_VERSION,
        "broken_requires_persistence_confirmation": True,
        "private_position_details_committed": False,
        "privacy_rule": "Per-position actions, tickers, balances, weights and P/L stay in-memory and are never committed or logged.",
    }
