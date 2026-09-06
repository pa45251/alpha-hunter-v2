from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

OUT = Path("output")
POLICY_PATH = Path("config/portfolio_allocation_policy.json")
POSITION_PATH = OUT / "position_cio_advisory.json"
CANDIDATE_PATH = OUT / "cio_advisory.json"
REGIME_PATH = OUT / "risk_regime.json"
OUTPUT_PATH = OUT / "portfolio_allocation_advisory.json"

CONF_SCORE = {"HIGH": 1.0, "MEDIUM": 0.65, "LOW": 0.35, "INSUFFICIENT": 0.0}
REACTION_SCORE = {"PRE_CONFIRMATION": 0.10, "CONFIRMING": 0.08, "PULLBACK": 0.04, "PERSISTENT": -0.03, "EXTENDED": -0.10, "UNKNOWN": 0.0}
ACTION_BASE = {"BUY_BIAS_STOCK": 0.78, "PREFER_ETF": 0.68, "HOLD_BIAS": 0.55}


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _candidate_edge(row: dict[str, Any]) -> float:
    action = str(row.get("advisory_action", ""))
    base = ACTION_BASE.get(action, 0.0)
    if base <= 0:
        return 0.0
    conf = CONF_SCORE.get(str(row.get("advisory_confidence", "")).upper(), 0.0)
    reaction = REACTION_SCORE.get(str(row.get("reaction_state", "UNKNOWN")).upper(), 0.0)
    provenance = 0.03 if str(row.get("provenance_status", "")).upper() == "SOURCE_BACKED" else -0.05
    priority = max(0.0, min(1.0, _f(row.get("research_priority_score"))))
    missing = str(row.get("advisory_missing_evidence", "")).strip()
    missing_penalty = 0.05 if missing else 0.0
    return round(max(0.0, min(1.0, base + 0.08 * conf + reaction + provenance + 0.04 * priority - missing_penalty)), 4)


def _position_edge(row: dict[str, Any]) -> float:
    action = str(row.get("advisory_action", ""))
    score = row.get("signal_score")
    if score is None:
        if action == "IGNORE_RESIDUAL":
            return 0.0
        return 0.50
    val = max(0.0, min(1.0, _f(score, 0.5)))
    if action == "REDUCE_BIAS":
        val = min(val, 0.30)
    elif action == "REVIEW_HOLD":
        val = min(val, 0.50)
    return round(val, 4)


def _rotation_size(spread: float, regime: str, policy: dict[str, Any]) -> tuple[str, int]:
    rot = policy["rotation"]
    min_edge = float(rot["min_edge_spread"])
    strong = float(rot["strong_edge_spread"])
    trim_cap = int(rot["max_source_trim_pct"].get(regime, rot["max_source_trim_pct"].get("UNKNOWN", 0)))
    if trim_cap <= 0 or spread < min_edge:
        return "NO_ROTATION", 0
    if spread >= strong:
        return "STRONG", trim_cap
    return "NORMAL", max(10, int(round(trim_cap * 0.6)))


def _entry_gated_rotation(size_state: str, planned_trim: int, reaction_state: str) -> tuple[str, int, int, str]:
    """Do not let portfolio rotation bypass the existing entry-state discipline.

    PRE_CONFIRMATION can nominate and size a future rotation, but no source trim is recommended now.
    CONFIRMING is the only state that upgrades the rotation to a current action bias.
    Persistent/extended/unknown states do not create a fresh rotation entry.
    """
    if size_state == "NO_ROTATION" or planned_trim <= 0:
        return "NO_ROTATION", 0, 0, ""
    reaction = str(reaction_state or "UNKNOWN").upper()
    if reaction == "PRE_CONFIRMATION":
        action = "PREPARE_ROTATION_STRONG" if size_state == "STRONG" else "PREPARE_ROTATION"
        return action, 0, planned_trim, "DESTINATION_REACTION_CONFIRMING"
    if reaction == "CONFIRMING":
        action = "ROTATE_PARTIAL_STRONG" if size_state == "STRONG" else "ROTATE_PARTIAL"
        return action, planned_trim, planned_trim, ""
    return "WAIT_BETTER_ENTRY", 0, planned_trim, "DESTINATION_ENTRY_STATE_NOT_CONFIRMING"


def build_portfolio_allocation() -> dict[str, Any]:
    policy = _load(POLICY_PATH)
    pos = _load(POSITION_PATH)
    cand = _load(CANDIDATE_PATH)
    regime = _load(REGIME_PATH)
    if not policy or not pos or not cand or not regime:
        return {
            "contract": "ALPHA_HUNTER_PORTFOLIO_ALLOCATION_ADVISORY",
            "schema_version": "1.0",
            "generated_at": datetime.now().astimezone().isoformat(),
            "status": "DATA_UNAVAILABLE",
            "auto_trade_allowed": False,
        }

    regime_label = str(regime.get("regime", "UNKNOWN"))
    target_cash = regime.get("target_cash_pct")
    if regime.get("status") != "READY":
        regime_label = "UNKNOWN"
        target_cash = None

    candidates = []
    for r in cand.get("top_advisories") or []:
        edge = _candidate_edge(r)
        if edge <= 0:
            continue
        preferred = str(r.get("preferred_exposure", "")).upper()
        candidates.append({
            "ticker": r.get("ticker") if preferred == "STOCK" else r.get("etf_ticker"),
            "name": r.get("name") if preferred == "STOCK" else "Mapped ETF",
            "preferred_exposure": r.get("preferred_exposure"),
            "advisory_action": r.get("advisory_action"),
            "edge_score": edge,
            "driver_id": r.get("driver_id"),
            "reaction_state": r.get("reaction_state"),
            "confidence": r.get("advisory_confidence"),
        })
    candidates.sort(key=lambda x: x["edge_score"], reverse=True)

    sources = []
    for r in pos.get("positions") or []:
        if str(r.get("advisory_action")) == "IGNORE_RESIDUAL":
            continue
        sources.append({
            "alias": r.get("alias"),
            "current_action": r.get("advisory_action"),
            "current_edge_score": _position_edge(r),
            "confidence": r.get("confidence"),
            "signal_state": r.get("signal_state"),
        })
    sources.sort(key=lambda x: x["current_edge_score"])

    rotations = []
    if candidates:
        best = candidates[0]
        for source in sources:
            spread = round(best["edge_score"] - source["current_edge_score"], 4)
            size_state, planned_trim = _rotation_size(spread, regime_label, policy)
            if size_state == "NO_ROTATION":
                continue
            action, trim_now, trim_on_trigger, entry_trigger = _entry_gated_rotation(
                size_state, planned_trim, str(best.get("reaction_state", "UNKNOWN"))
            )
            redeploy_pct = int(policy["rotation"]["redeploy_pct_of_trim"].get(regime_label, policy["rotation"]["redeploy_pct_of_trim"].get("UNKNOWN", 0)))
            rotations.append({
                "source_alias": source["alias"],
                "source_action": source["current_action"],
                "destination_ticker": best["ticker"],
                "destination_name": best["name"],
                "destination_action": best["advisory_action"],
                "destination_driver": best["driver_id"],
                "destination_reaction_state": best["reaction_state"],
                "rotation_action": action,
                "edge_spread": spread,
                "suggested_source_trim_pct_now": trim_now,
                "suggested_source_trim_pct_on_trigger": trim_on_trigger,
                "suggested_redeploy_pct_of_trim_on_trigger": redeploy_pct,
                "suggested_risk_buffer_pct_of_trim_on_trigger": 100 - redeploy_pct,
                "entry_trigger_required": entry_trigger,
                "reason": "DESTINATION_EDGE_EXCEEDS_SOURCE_BY_POLICY_THRESHOLD",
            })
            # One primary rotation at a time avoids mechanically concentrating multiple holdings into one destination.
            break

    return {
        "contract": "ALPHA_HUNTER_PORTFOLIO_ALLOCATION_ADVISORY",
        "schema_version": "1.1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "READY",
        "risk_regime": regime_label,
        "risk_score": regime.get("risk_score"),
        "target_cash_pct": target_cash,
        "cash_rule": "Target cash is a risk-budget buffer. In leveraged accounts, implementation should generally reduce financing/gross exposure before holding idle cash; private balances are not published here.",
        "best_new_opportunity": candidates[0] if candidates else None,
        "rotations": rotations,
        "source_ranking": sources,
        "candidate_ranking": candidates[:10],
        "privacy": {
            "source_positions_alias_only": True,
            "portfolio_balances_included": False,
            "position_weights_included": False,
            "financing_included": False
        },
        "auto_trade_allowed": False,
        "method": "Compare normalized CIO edge for current holdings versus validated new opportunities, nominate at most one primary rotation, but preserve entry discipline: PRE_CONFIRMATION only prepares a rotation and CONFIRMING is required before a current rotation bias is emitted. Risk regime controls trim/redeploy sizing.",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = build_portfolio_allocation()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Portfolio allocation: status={payload.get('status')} regime={payload.get('risk_regime')} target_cash={payload.get('target_cash_pct')} rotations={len(payload.get('rotations') or [])}")


if __name__ == "__main__":
    main()
