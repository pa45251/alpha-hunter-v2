from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

OUT = Path("output")
POLICY_PATH = Path("config/portfolio_allocation_policy.json")
POSITION_PATH = OUT / "position_cio_advisory.json"
CANDIDATE_PATH = OUT / "cio_advisory.json"
REGIME_PATH = OUT / "risk_regime.json"
THEME_PATH = OUT / "theme_breadth.csv"
OUTPUT_PATH = OUT / "portfolio_allocation_advisory.json"

CONF_SCORE = {"HIGH": 1.0, "MEDIUM": 0.65, "LOW": 0.35, "INSUFFICIENT": 0.0}
REACTION_SCORE = {"PRE_CONFIRMATION": 0.10, "CONFIRMING": 0.08, "PULLBACK": 0.04, "PERSISTENT": -0.03, "EXTENDED": -0.10, "UNKNOWN": 0.0}
ACTION_BASE = {"BUY_BIAS_STOCK": 0.78, "PREFER_ETF": 0.68, "HOLD_BIAS": 0.55}
ADVERSE_REGIMES = {"CAUTION", "DEFENSIVE", "CRISIS"}
RATE_SENSITIVE_THEME_TOKENS = {"BIOTECH", "GENOMICS", "GROWTH", "SOFTWARE", "CLOUD"}


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


def _theme_score(row: pd.Series) -> float:
    return (
        0.30 * _f(row.get("above_ma20_pct"))
        + 0.25 * _f(row.get("above_ma60_pct"))
        + 0.25 * _f(row.get("positive_rs20_pct"))
        + 0.10 * _f(row.get("positive_rs5_pct"))
        + 0.10 * _f(row.get("near_20d_high_pct"))
    )


def _theme_trend(global_theme: str, themes: pd.DataFrame) -> str:
    if themes.empty or "theme" not in themes.columns:
        return "UNKNOWN"
    rows = themes[themes["theme"].astype(str) == str(global_theme)]
    if rows.empty:
        return "UNKNOWN"
    score = _theme_score(rows.iloc[0])
    if score >= 0.52:
        return "UPTREND"
    if score < 0.38:
        return "DOWNTREND_OR_BROKEN"
    return "MIXED"


def _theme_is_rate_sensitive(global_theme: str) -> bool:
    text = str(global_theme or "").upper()
    return any(token in text for token in RATE_SENSITIVE_THEME_TOKENS)


def _theme_macro_support(global_theme: str, regime: dict[str, Any]) -> str:
    if not regime or regime.get("status") != "READY":
        return "UNKNOWN"
    label = str(regime.get("regime", "UNKNOWN")).upper()
    if label in ADVERSE_REGIMES:
        return "ADVERSE"

    rate_pressure = str((regime.get("signals") or {}).get("rate_pressure", "UNKNOWN")).upper()
    if _theme_is_rate_sensitive(global_theme):
        if rate_pressure == "ADVERSE":
            return "ADVERSE"
        if rate_pressure == "SUPPORTIVE":
            return "SUPPORTIVE"
        return "CONDITIONAL"

    if label in {"RISK_ON", "NORMAL"}:
        return "SUPPORTIVE"
    return "UNKNOWN"


def _trend_regime_stance(trend_state: str, macro_support: str, entry_location: str) -> str:
    trend = str(trend_state or "UNKNOWN").upper()
    macro = str(macro_support or "UNKNOWN").upper()
    entry = str(entry_location or "UNKNOWN").upper()

    if trend == "UPTREND" and macro == "SUPPORTIVE" and entry == "PULLBACK":
        return "BUY_PULLBACK_CANDIDATE"
    if trend == "UPTREND" and macro == "SUPPORTIVE":
        return "HOLD_OR_WAIT_PULLBACK"
    if trend == "UPTREND" and macro != "SUPPORTIVE":
        return "WAIT_REGIME"
    if trend == "DOWNTREND_OR_BROKEN" and macro == "ADVERSE":
        return "REDUCE_EXIT_CASH"
    if trend == "DOWNTREND_OR_BROKEN":
        return "WAIT_RECOVERY"
    if trend == "MIXED" and macro == "ADVERSE":
        return "REDUCE_OR_WAIT"
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


def _entry_gated_rotation(size_state: str, planned_trim: int, reaction_state: str, trend_state: str, macro_support: str) -> tuple[str, int, int, str]:
    if size_state == "NO_ROTATION" or planned_trim <= 0:
        return "NO_ROTATION", 0, 0, ""
    if trend_state != "UPTREND":
        return "WAIT_TREND", 0, planned_trim, "UPTREND_REQUIRED"
    if macro_support != "SUPPORTIVE":
        return "WAIT_REGIME", 0, planned_trim, "THEME_MACRO_SUPPORT_REQUIRED"

    reaction = str(reaction_state or "UNKNOWN").upper()
    if reaction == "PRE_CONFIRMATION":
        action = "PREPARE_ROTATION_STRONG" if size_state == "STRONG" else "PREPARE_ROTATION"
        return action, 0, planned_trim, "DESTINATION_REACTION_CONFIRMING_OR_PULLBACK"
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
    themes = pd.read_csv(THEME_PATH) if THEME_PATH.exists() else pd.DataFrame()
    if not policy or not pos or not cand or not regime:
        return {
            "contract": "ALPHA_HUNTER_PORTFOLIO_ALLOCATION_ADVISORY",
            "schema_version": "1.3",
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
        reaction_state = str(r.get("reaction_state", "UNKNOWN"))
        global_theme = str(r.get("global_theme", ""))
        trend_state = _theme_trend(global_theme, themes)
        macro_support = _theme_macro_support(global_theme, regime)
        candidates.append({
            "ticker": r.get("ticker") if preferred == "STOCK" else r.get("etf_ticker"),
            "name": r.get("name") if preferred == "STOCK" else "Mapped ETF",
            "global_theme": global_theme,
            "preferred_exposure": r.get("preferred_exposure"),
            "advisory_action": r.get("advisory_action"),
            "edge_score": edge,
            "driver_id": r.get("driver_id"),
            "reaction_state": reaction_state,
            "trend_state": trend_state,
            "macro_support": macro_support,
            "trend_regime_stance": _trend_regime_stance(trend_state, macro_support, reaction_state),
            "confidence": r.get("advisory_confidence"),
        })
    candidates.sort(key=lambda x: x["edge_score"], reverse=True)

    sources = []
    for r in pos.get("positions") or []:
        if str(r.get("advisory_action")) == "IGNORE_RESIDUAL":
            continue
        trend_state = str(r.get("trend_state", "UNKNOWN"))
        macro_support = str(r.get("macro_support", "UNKNOWN"))
        sources.append({
            "alias": r.get("alias"),
            "current_action": r.get("advisory_action"),
            "current_edge_score": _position_edge(r),
            "confidence": r.get("confidence"),
            "signal_state": r.get("signal_state"),
            "trend_state": trend_state,
            "macro_support": macro_support,
            "trend_regime_stance": _trend_regime_stance(trend_state, macro_support, "HOLDING"),
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
                str(best.get("trend_state", "UNKNOWN")),
                str(best.get("macro_support", "UNKNOWN")),
            )
            redeploy_pct = int(policy["rotation"]["redeploy_pct_of_trim"].get(regime_label, policy["rotation"]["redeploy_pct_of_trim"].get("UNKNOWN", 0)))
            rotations.append({
                "source_alias": source["alias"],
                "source_action": source["current_action"],
                "source_trend_state": source["trend_state"],
                "source_macro_support": source["macro_support"],
                "destination_ticker": best["ticker"],
                "destination_name": best["name"],
                "destination_action": best["advisory_action"],
                "destination_driver": best["driver_id"],
                "destination_reaction_state": best["reaction_state"],
                "destination_trend_state": best["trend_state"],
                "destination_macro_support": best["macro_support"],
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
        "schema_version": "1.3",
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "READY",
        "risk_regime": regime_label,
        "risk_score": regime.get("risk_score"),
        "rate_pressure": str((regime.get("signals") or {}).get("rate_pressure", "UNKNOWN")),
        "target_cash_pct": target_cash,
        "core_philosophy": "FOLLOW_TREND_BUY_WEAKNESS_ONLY_WHEN_THEME_MACRO_SUPPORTS_TREND",
        "decision_matrix": {
            "UPTREND+SUPPORTIVE+PULLBACK": "BUY_OR_ADD_CANDIDATE",
            "UPTREND+ADVERSE": "HOLD_OR_WAIT; DO_NOT_AUTO_BUY_DIP",
            "DOWNTREND+SUPPORTIVE": "WAIT_RECOVERY",
            "DOWNTREND+ADVERSE": "REDUCE_EXIT_CASH",
        },
        "cash_rule": "Target cash is a risk-budget buffer. Adverse regime or theme-macro incompatibility reduces willingness to add fresh risk; neither is a crash prediction.",
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
        "method": "Trend, macro compatibility and entry location are separate. Trend is derived from theme breadth/relative-strength evidence rather than reaction state. Rate-sensitive themes consume Treasury rate pressure. Pullbacks may become buy candidates only when trend is up and theme macro is supportive. Price strength never creates causality.",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = build_portfolio_allocation()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Portfolio allocation: status={payload.get('status')} regime={payload.get('risk_regime')} target_cash={payload.get('target_cash_pct')} rotations={len(payload.get('rotations') or [])}")


if __name__ == "__main__":
    main()
