from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from portfolio_allocation_advisory import _candidate_edge, _position_edge, _rotation_size

OUT = Path("output")
POLICY_PATH = Path("config/portfolio_allocation_policy.json")
POSITION_PATH = OUT / "position_cio_advisory.json"
CANDIDATE_PATH = OUT / "cio_advisory.json"
REGIME_PATH = OUT / "risk_regime.json"
ENTRY_PATH = OUT / "entry_plans_v2.json"
OUTPUT_PATH = OUT / "portfolio_allocation_v2.json"

CONTRACT = "ALPHA_HUNTER_PORTFOLIO_ALLOCATION_V2"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _entry_state(plan: dict[str, Any]) -> tuple[str, str]:
    """Map the canonical Entry Plan to rotation permission.

    EOD outputs never authorize an immediate source sale because BUY_NOW requires a live quote.
    They may nominate a future conditional rotation with exact levels.
    """
    action = str(plan.get("current_action", ""))
    status = str(plan.get("entry_status", ""))
    if action in {"AVOID", "DONT_CHASE"}:
        return "BLOCKED", action
    if not bool(plan.get("entry_structure_valid", False)):
        return "NO_STRUCTURE", status or action
    if not bool(plan.get("global_confirmation", {}).get("status") == "PASS"):
        return "BLOCKED", "GLOBAL_CONFIRMATION_FAILED"
    if status == "CONFIRMED_NEXT_SESSION_CONDITIONAL":
        return "TRIGGERED_CONDITIONAL", status
    if status in {
        "WAITING_FOR_TRIGGER", "WAITING_FOR_RECOVERY_TRIGGER", "CONTINUATION_BASE_WAITING_FOR_TRIGGER",
        "PRICE_CONFIRMED_PARTICIPATION_UNCONFIRMED", "CONTINUATION_PRICE_CONFIRMED_PARTICIPATION_UNCONFIRMED",
    }:
        return "PREPARE", status
    return "NO_STRUCTURE", status or action


def build_portfolio_allocation_v2(
    policy: dict[str, Any],
    positions: dict[str, Any],
    candidates: dict[str, Any],
    regime: dict[str, Any],
    entries: dict[str, Any],
) -> dict[str, Any]:
    required = [policy, positions, candidates, regime, entries]
    if not all(required) or str(entries.get("status")) != "READY" or str(regime.get("status")) != "READY":
        return {
            "contract": CONTRACT,
            "schema_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "DATA_UNAVAILABLE",
            "auto_trade_allowed": False,
        }

    regime_label = str(regime.get("regime", "UNKNOWN"))
    plans = {str(p.get("ticker")): p for p in (entries.get("all_plans") or []) if p.get("ticker")}

    research_candidates = []
    executable_candidates = []
    for row in candidates.get("top_advisories") or []:
        preferred = str(row.get("preferred_exposure", "")).upper()
        ticker = str(row.get("ticker", ""))
        # Exact Entry V2 currently covers Taiwan common stocks. ETF destinations stay research-only.
        if preferred != "STOCK" or not ticker:
            continue
        edge = _candidate_edge(row)
        if edge <= 0:
            continue
        plan = plans.get(ticker)
        item = {
            "ticker": ticker,
            "name": row.get("name"),
            "driver_id": row.get("driver_id"),
            "advisory_action": row.get("advisory_action"),
            "edge_score": edge,
            "score_is_probability": False,
            "entry_plan_present": plan is not None,
            "entry_style": plan.get("entry_style") if plan else None,
            "entry_status": plan.get("entry_status") if plan else None,
            "trigger_price": plan.get("trigger_price") if plan else None,
            "buy_zone_low": plan.get("buy_zone_low") if plan else None,
            "buy_zone_high": plan.get("buy_zone_high") if plan else None,
            "invalidation_price": plan.get("invalidation_price") if plan else None,
        }
        research_candidates.append(item)
        if plan:
            permission, reason = _entry_state(plan)
            item = dict(item)
            item["entry_permission"] = permission
            item["entry_permission_reason"] = reason
            # Risk is advisory-only here; EOD still requires a live quote before execution.
            if permission in {"TRIGGERED_CONDITIONAL", "PREPARE"}:
                executable_candidates.append(item)

    research_candidates.sort(key=lambda x: x["edge_score"], reverse=True)
    executable_candidates.sort(key=lambda x: x["edge_score"], reverse=True)

    sources = []
    for row in positions.get("positions") or []:
        if str(row.get("advisory_action")) == "IGNORE_RESIDUAL":
            continue
        sources.append({
            "alias": row.get("alias"),
            "current_action": row.get("advisory_action"),
            "current_edge_score": _position_edge(row),
            "confidence": row.get("confidence"),
            "signal_state": row.get("signal_state"),
        })
    sources.sort(key=lambda x: x["current_edge_score"])

    rotations = []
    if executable_candidates and sources:
        best = executable_candidates[0]
        for source in sources:
            spread = round(float(best["edge_score"]) - float(source["current_edge_score"]), 4)
            size_state, planned_trim = _rotation_size(spread, regime_label, policy)
            if size_state == "NO_ROTATION":
                continue
            permission = str(best.get("entry_permission"))
            if permission == "TRIGGERED_CONDITIONAL":
                rotation_action = "PREPARE_ROTATION_TRIGGERED"
                trigger_required = "LIVE_QUOTE_IN_BUY_ZONE_AND_ROTATION_RISK_RECHECK"
            else:
                rotation_action = "PREPARE_ROTATION_STRONG" if size_state == "STRONG" else "PREPARE_ROTATION"
                trigger_required = "ENTRY_PLAN_TRIGGER_AND_LIVE_QUOTE"
            redeploy_pct = int(policy["rotation"]["redeploy_pct_of_trim"].get(regime_label, policy["rotation"]["redeploy_pct_of_trim"].get("UNKNOWN", 0)))
            rotations.append({
                "source_alias": source["alias"],
                "destination_ticker": best["ticker"],
                "destination_name": best["name"],
                "destination_driver": best["driver_id"],
                "destination_entry_style": best["entry_style"],
                "rotation_action": rotation_action,
                "relative_evidence_spread": spread,
                "score_is_probability": False,
                "suggested_source_trim_pct_now": 0,
                "suggested_source_trim_pct_if_live_trigger_valid": planned_trim,
                "suggested_redeploy_pct_of_trim": redeploy_pct,
                "trigger_price": best["trigger_price"],
                "buy_zone_low": best["buy_zone_low"],
                "buy_zone_high": best["buy_zone_high"],
                "invalidation_price": best["invalidation_price"],
                "entry_trigger_required": trigger_required,
                "reason": "DESTINATION_EDGE_EXCEEDS_SOURCE_AND_CANONICAL_ENTRY_PLAN_EXISTS",
            })
            break

    return {
        "contract": CONTRACT,
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "READY",
        "risk_regime": regime_label,
        "risk_score": regime.get("risk_score"),
        "target_cash_pct": regime.get("target_cash_pct"),
        "best_research_opportunity": research_candidates[0] if research_candidates else None,
        "best_entry_plan_destination": executable_candidates[0] if executable_candidates else None,
        "rotations": rotations,
        "source_ranking": sources,
        "candidate_ranking": executable_candidates[:10],
        "rules": [
            "ROTATION_MUST_USE_CANONICAL_ENTRY_PLAN_V2",
            "GLOBAL_ALIGNMENT_AND_EXACT_ENTRY_CANNOT_BE_BYPASSED",
            "END_OF_DAY_PIPELINE_NEVER_SELLS_SOURCE_NOW_WITHOUT_LIVE_EXECUTABLE_DESTINATION_QUOTE",
            "CRISIS_REGIME_CANNOT_CREATE_RISK_ON_ROTATION",
            "SCORES_ARE_RELATIVE_EVIDENCE_NOT_WIN_PROBABILITIES",
        ],
        "auto_trade_allowed": False,
    }


def write_outputs() -> dict[str, Any]:
    payload = build_portfolio_allocation_v2(
        _load(POLICY_PATH), _load(POSITION_PATH), _load(CANDIDATE_PATH), _load(REGIME_PATH), _load(ENTRY_PATH)
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    p = write_outputs()
    print(f"Portfolio Allocation V2 status={p.get('status')} rotations={len(p.get('rotations') or [])}")


if __name__ == "__main__":
    main()
