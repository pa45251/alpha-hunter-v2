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
SUPPORTIVE_REGIMES = {"RISK_ON", "NORMAL"}
ADVERSE_REGIMES = {"CAUTION", "DEFENSIVE", "CRISIS"}


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


def _trend_state(reaction_state: str) -> str:
    reaction = str(reaction_state or "UNKNOWN").upper()
    if reaction == "PULLBACK":
        return "UPTREND_PULLBACK"
    if reaction in {"PRE_CONFIRMATION", "EARLY_CONFIRMATION", "CONFIRMING", "PERSISTENT", "EXTENDED"}:
        return "UPTREND"
    if reaction == "BROKEN":
        return "DOWNTREND_OR_BROKEN"
    return "UNKNOWN"


def _regime_support(regime: str) -> str:
    label = str(regime or "UNKNOWN").upper()
    if label in SUPPORTIVE_REGIMES:
        return "SUPPORTIVE"
    if label in ADVERSE_REGIMES:
        return "ADVERSE"
    return "UNKNOWN"


def _trend_regime_stance(trend_state: str, regime_support: str) -> str:
    """High-level CIO philosophy: follow trend; buy weakness only when regime still supports it."""
    if trend_state == "UPTREND_PULLBACK" and regime_support == "SUPPORTIVE":
        return "BUY_PULLBACK_CANDIDATE"
    if trend_state == "UPTREND" and regime_support == "SUPPORTIVE":
        return "HOLD_OR_WAIT_PULLBACK"
    if trend_state in {"UPTREND", "UPTREND_PULLBACK"} and regime_support == "ADVERSE":
        return "WAIT_REGIME"
    if trend_state == "DOWNTREND_OR_BROKEN" and regime_support == "SUPPORTIVE":
        return "WAIT_RECOVERY"
    if trend_state == "DOWNTREND_OR_BROKEN" and regime_support == "ADVERSE":
        return "REDUCE_EXIT_CASH"
    return "WAIT"


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


def _entry_gated_rotation(size_state: str, planned_trim: int, reaction_state: str, regime_support: str = "SUPPORTIVE") -> tuple[str, int, int, str]:
    """Preserve entry discipline and add a regime veto for fresh risk.

    Trend alone is insufficient. A pullback or confirmation can only become a current
    rotation bias when the broader regime is supportive. Adverse/unknown regime keeps
    the idea in wait/prepare mode; it does not manufacture a trade.
    """
    if size_state == "NO_ROTATION" or planned_trim <= 0:
        return "NO_ROTATION", 0, 0, ""
    reaction = str(reaction_state or "UNKNOWN").upper()
    if regime_support != "SUPPORTIVE":
        return "WAIT_REGIME", 0, planned_trim, "REGIME_SUPPORT_REQUIRED"
    if reaction == "PRE_CONFIRMATION":
        action = "PREPARE_ROTATION_STRONG" if size_state == "STRONG" else "PREPARE_ROTATION"
        return action, 0, planned_trim, "DESTINATION_REACTION_CONFIRMING"
    if reaction == "CONFIRMING":
        action = "ROTATE_PARTIAL_STRONG" if size_state == "STRONG" else "ROTATE_PARTIAL"
        return action, planned_trim, planned_trim, ""
    if reaction == "PULLBACK":
        action = "BUY_PULLBACK_ROTATION_STRONG" if size_state == "STRONG" else "BUY_PULLBACK_ROTATION"
        return action, planned_trim, planned_trim, ""
    return "WAIT_BETTER_ENTRY", 0, planned_trim, "DESTINATION_ENTRY_STATE_NOT_CONFIRMING_OR_PULLBACK"


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
    regime_support = _regime_support(regime_label)

    candidates = []
    for r in cand.get("top_advisories") or []:
        edge = _candidate_edge(r)
        if edge <= 0:
            continue
        preferred = str(r.get("preferred_exposure", "")).upper()
        reaction_state = str(r.get("reaction_state", "UNKNOWN"))
        trend_state = _trend_state(reaction_state)
        candidates.append({
            "ticker": r.get("ticker") if preferred == "STOCK" else r.get("etf_ticker"),
            "name": r.get("name") if preferred == "STOCK" else "Mapped ETF",
            "preferred_exposure": r.get("preferred_exposure"),
            "advisory_action": r.get("advisory_action"),
            "edge_score": edge,
            "driver_id": r.get("driver_id"),
            "reaction_state": reaction_state,
            "trend_state": trend_state,
            "regime_support": regime_support,
            "trend_regime_stance": _trend_regime_stance(trend_state, regime_support),
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
            "regime_support": regime_support,
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
                size_state,
                planned_trim,
                str(best.get("reaction_state", "UNKNOWN")),
                regime_support,
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
                "destination_trend_state": best["trend_state"],
                "regime_support": regime_support,
                "trend_regime_stance": best["trend_regime_stance"],
                "rotation_action": action,
                "edge_spread": spread,
                "suggested_source_trim_pct_now": trim_now,
                "suggested_source_trim_pct_on_trigger": trim_on_trigger,
                "suggested_redeploy_pct_of_trim_on_trigger": redeploy_pct,
                "suggested_risk_buffer_pct_of_trim_on_trigger": 100 - redeploy_pct,
                "entry_trigger_required": entry_trigger,
                "reason": "DESTINATION_EDGE_EXCEEDS_SOURCE_BY_POLICY_THRESHOLD",
            })
            break

    return {
        "contract": "ALPHA_HUNTER_PORTFOLIO_ALLOCATION_ADVISORY",
        "schema_version": "1.2",
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "READY",
        "risk_regime": regime_label,
        "risk_score": regime.get("risk_score"),
        "regime_support": regime_support,
        "target_cash_pct": target_cash,
        "core_philosophy": "FOLLOW_TREND_BUY_WEAKNESS_ONLY_WHEN_REGIME_SUPPORTS_TREND",
        "decision_matrix": {
            "UPTREND+SUPPORTIVE": "HOLD_OR_BUY_PULLBACK",
            "UPTREND+ADVERSE": "HOLD_OR_WAIT; DO_NOT_AUTO_BUY_DIP",
            "DOWNTREND+SUPPORTIVE": "WAIT_RECOVERY",
            "DOWNTREND+ADVERSE": "REDUCE_EXIT_CASH",
        },
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
        "method": "Follow trend first, then apply the macro/risk regime as a veto on fresh risk. A pullback is attractive only when the underlying trend is intact and the regime remains supportive. Trend strength never creates causality, and adverse regime does not by itself prove a crash; it reduces willingness to buy weakness and increases the value of cash. Rotation remains advisory and preserves entry discipline.",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = build_portfolio_allocation()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Portfolio allocation: status={payload.get('status')} regime={payload.get('risk_regime')} target_cash={payload.get('target_cash_pct')} rotations={len(payload.get('rotations') or [])}")


if __name__ == "__main__":
    main()
