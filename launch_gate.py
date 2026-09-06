"""Frozen shadow-only release boundary. A research BUY is never live authorization."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_launch(root: Path = ROOT) -> dict:
    blockers = ["SHADOW_ONLY_NOT_APPROVED_FOR_LIVE_EXECUTION"]
    policy = {}
    frozen = {}
    try:
        policy = json.loads((root / "config/launch_policy.json").read_text())
        frozen = json.loads((root / "config/frozen_strategy_v1.json").read_text())
        if not frozen.get("file_hashes"):
            blockers.append("FROZEN_RULES_MISSING")
        for name, expected in frozen.get("file_hashes", {}).items():
            path = root / name
            if not path.is_file() or file_hash(path) != expected:
                blockers.append("FROZEN_RULES_CHANGED_REVALIDATION_REQUIRED")
                break
        if policy.get("mode") != "SHADOW":
            blockers.append("MODE_CHANGE_REQUIRES_SEPARATE_RELEASE")
    except (OSError, ValueError, TypeError):
        blockers.append("LAUNCH_CONFIGURATION_INVALID")
        policy = {}
        frozen = {}
    return {
        "policy_version": policy.get("policy_version", "UNKNOWN"),
        "strategy_version": frozen.get("strategy_version", "UNKNOWN"),
        "mode": "SHADOW",
        "live_execution_authorized": False,
        "auto_order_execution": False,
        "freeze_integrity_pass": len(blockers) == 1,
        "blockers": list(dict.fromkeys(blockers)),
        "first_review_date": policy.get("first_review_date"),
        "review_is_automatic_promotion": False,
        "pilot_limits": policy.get("pilot_limits", {}),
        "pilot_limits_active_on_existing_holdings": False,
        "validation_evidence_required": (policy.get("validation") or {}).get("required_evidence", []),
        "validation_evidence_status": "PENDING_ACCEPTANCE_REVIEW",
        "current_shadow_statistics_are_strategy_validation": False,
    }


def apply_launch_gate(board: pd.DataFrame, root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    release = evaluate_launch(root)
    x = board.copy()
    # Preserve model signals for ex-ante validation; never label them as executable.
    x["deployment_mode"] = "SHADOW"
    x["strategy_version"] = release["strategy_version"]
    x["live_execution_authorized"] = False
    x["auto_trade_allowed"] = False
    x["execution_action"] = "NO_LIVE_ORDER"
    x["launch_blockers"] = ";".join(release["blockers"])
    return x, release


def proposed_pilot_size(net_equity: float, initial_net_equity: float, stop_distance_pct: float,
                        current_pilot_value: float, open_planned_loss: float,
                        cumulative_pilot_pnl: float, *, inputs_valid: bool,
                        leveraged: bool = False, root: Path = ROOT) -> dict:
    """Private sizing preview only. Values include both realized and unrealized pilot P/L.

    Caller supplies investable net equity after related financing and living reserve.
    Existing portfolio positions are not assigned to this pilot automatically.
    """
    denied = {"proposed_value": 0.0, "planned_loss": 0.0, "live_execution_authorized": False}
    nums = [net_equity, initial_net_equity, stop_distance_pct, current_pilot_value,
            open_planned_loss, cumulative_pilot_pnl]
    if not inputs_valid or leveraged or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in nums):
        return {**denied, "reason": "INVALID_INPUTS_OR_LEVERAGE"}
    if min(net_equity, initial_net_equity, stop_distance_pct) <= 0 or stop_distance_pct > 100 or min(current_pilot_value, open_planned_loss) < 0:
        return {**denied, "reason": "INVALID_BUDGET_INPUTS"}
    release = evaluate_launch(root)
    if not release["freeze_integrity_pass"]:
        return {**denied, "reason": "FROZEN_RULES_INVALID"}
    limits = release["pilot_limits"]
    if cumulative_pilot_pnl <= -initial_net_equity * limits["stop_new_entries_loss_pct_of_initial_net_equity"] / 100:
        return {**denied, "reason": "PILOT_LOSS_STOP"}
    loss_budget = min(net_equity * limits["max_planned_loss_per_trade_pct"] / 100,
                      max(0.0, net_equity * limits["max_aggregate_planned_loss_pct"] / 100 - open_planned_loss))
    gross_room = max(0.0, net_equity * limits["max_gross_pct_of_net_equity"] / 100 - current_pilot_value)
    value = min(gross_room, loss_budget / (stop_distance_pct / 100))
    return {"proposed_value": value, "planned_loss": value * stop_distance_pct / 100,
            "live_execution_authorized": False, "reason": "SHADOW_SIZING_PREVIEW_ONLY"}
