from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from portfolio_risk import load_portfolio_state, load_risk_policy, validate_risk_inputs
from position_alias_output import load_alias_map

OUT = Path("output")
THEME_PATH = OUT / "theme_breadth.csv"
REGIME_PATH = OUT / "risk_regime.json"
ALIAS_ACTION_PATH = OUT / "position_alias_actions.json"
OUTPUT_PATH = OUT / "position_cio_advisory.json"

RISK_GROUP_THEME_MAP = {
    "US_MEGATECH": ["Factor_Growth", "Market_US", "AI_Server", "Cloud_AI", "AI_Semiconductor", "Consumer_Tech"],
    "GROWTH_DURATION": ["Factor_Growth", "Factor_Momentum", "Market_US"],
    "BIOTECH_RISK": ["Biotech", "Genomics"],
    "CRITICAL_MATERIALS": ["Copper", "Uranium", "Energy"],
    "CYBERSECURITY": ["Cybersecurity"],
    "ENTERPRISE_IT": ["Software", "Cloud_AI"],
    "TAIWAN_BROAD": [],
}
RATE_SENSITIVE_RISK_GROUPS = {"GROWTH_DURATION", "BIOTECH_RISK"}
ADVERSE_REGIMES = {"CAUTION", "DEFENSIVE", "CRISIS"}

CONF_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.85, "LOW": 0.55}
RESIDUAL_WEIGHT_PCT = 0.10


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ticker_key(v: Any) -> str:
    return str(v or "").strip().upper().removesuffix(".TWO").removesuffix(".TW")


def _is_taiwan_etf(ticker: str) -> bool:
    key = _ticker_key(ticker)
    return len(key) in {5, 6} and key.isdigit() and key.startswith("00")


def _groups(pos: dict[str, Any]) -> list[str]:
    groups = pos.get("risk_groups") or []
    if isinstance(groups, str):
        groups = [groups]
    return [str(g).upper() for g in groups]


def _theme_keys(pos: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for group in _groups(pos):
        out.extend(RISK_GROUP_THEME_MAP.get(group, []))
    return list(dict.fromkeys(out))


def _theme_score(row: pd.Series) -> float:
    return (
        0.30 * _f(row.get("above_ma20_pct"))
        + 0.25 * _f(row.get("above_ma60_pct"))
        + 0.25 * _f(row.get("positive_rs20_pct"))
        + 0.10 * _f(row.get("positive_rs5_pct"))
        + 0.10 * _f(row.get("near_20d_high_pct"))
    )


def _classify(score: float) -> str:
    if score >= 0.68:
        return "STRONG"
    if score >= 0.52:
        return "POSITIVE"
    if score >= 0.38:
        return "MIXED"
    return "WEAK"


def _trend_state_from_breadth(state: str) -> str:
    if state in {"STRONG", "POSITIVE"}:
        return "UPTREND"
    if state == "WEAK":
        return "DOWNTREND_OR_BROKEN"
    return "MIXED"


def _macro_support(pos: dict[str, Any], regime: dict[str, Any]) -> str:
    if not regime or regime.get("status") != "READY":
        return "UNKNOWN"
    label = str(regime.get("regime", "UNKNOWN")).upper()
    if label in ADVERSE_REGIMES:
        return "ADVERSE"

    groups = set(_groups(pos))
    rate_sensitive = bool(groups & RATE_SENSITIVE_RISK_GROUPS)
    rate_pressure = str((regime.get("signals") or {}).get("rate_pressure", "UNKNOWN")).upper()
    if rate_sensitive:
        if rate_pressure == "ADVERSE":
            return "ADVERSE"
        if rate_pressure == "SUPPORTIVE":
            return "SUPPORTIVE"
        return "CONDITIONAL"

    if label in {"RISK_ON", "NORMAL"}:
        return "SUPPORTIVE"
    return "UNKNOWN"


def _position_stance(trend_state: str, macro_support: str) -> tuple[str, str]:
    if trend_state == "UPTREND" and macro_support == "SUPPORTIVE":
        return "HOLD_BIAS", "UPTREND_MACRO_SUPPORTIVE"
    if trend_state == "UPTREND" and macro_support in {"ADVERSE", "CONDITIONAL", "UNKNOWN"}:
        return "REVIEW_HOLD", "UPTREND_MACRO_NOT_FULLY_SUPPORTIVE"
    if trend_state == "DOWNTREND_OR_BROKEN" and macro_support == "ADVERSE":
        return "REDUCE_BIAS", "TREND_AND_MACRO_BOTH_ADVERSE"
    if trend_state == "DOWNTREND_OR_BROKEN":
        return "REVIEW_HOLD", "WAIT_FOR_TREND_RECOVERY"
    if trend_state == "MIXED" and macro_support == "ADVERSE":
        return "REDUCE_BIAS", "MIXED_TREND_WITH_ADVERSE_MACRO"
    return "REVIEW_HOLD", "MIXED_OR_UNCERTAIN_TREND"


def _confidence(lane: str, rows: pd.DataFrame) -> str:
    if rows.empty:
        return "LOW"
    high_med = int(rows["breadth_confidence"].astype(str).str.upper().isin({"HIGH", "MEDIUM"}).sum())
    if lane == "ETF_THEME" and len(rows) >= 2 and high_med >= 2:
        return "HIGH"
    if high_med >= 1:
        return "MEDIUM"
    return "LOW"


def _strict_actions_by_alias() -> dict[str, str]:
    if not ALIAS_ACTION_PATH.exists():
        return {}
    try:
        payload = json.loads(ALIAS_ACTION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(r.get("alias", "")): str(r.get("action", "")) for r in (payload.get("positions") or [])}


def build_position_cio_advisory() -> dict[str, Any]:
    if not THEME_PATH.exists():
        raise RuntimeError("POSITION_CIO_THEME_BREADTH_MISSING")

    policy = load_risk_policy()
    raw_portfolio = load_portfolio_state()
    valid, blockers, portfolio = validate_risk_inputs(policy, raw_portfolio)
    if not valid:
        raise RuntimeError("POSITION_CIO_PRIVATE_INPUTS_INVALID:" + ";".join(blockers))

    alias_map = load_alias_map(portfolio)
    strict = _strict_actions_by_alias()
    regime = _load_json(REGIME_PATH)
    themes = pd.read_csv(THEME_PATH)
    themes["theme"] = themes["theme"].astype(str)
    theme_index = themes.set_index("theme", drop=False)

    records: list[dict[str, Any]] = []
    for pos in portfolio.get("positions") or []:
        ticker = _ticker_key(pos.get("ticker"))
        alias = alias_map.get(ticker)
        if not alias:
            raise RuntimeError("POSITION_CIO_ALIAS_MAPPING_INCOMPLETE")
        weight_pct = _f(pos.get("weight_pct"))

        if weight_pct < RESIDUAL_WEIGHT_PCT:
            records.append({
                "alias": alias,
                "lane": "RESIDUAL",
                "advisory_action": "IGNORE_RESIDUAL",
                "confidence": "HIGH",
                "signal_state": "DE_MINIMIS",
                "signal_score": None,
                "trend_state": "DE_MINIMIS",
                "macro_support": "NOT_APPLICABLE",
                "reason": "POSITION_BELOW_DE_MINIMIS_WEIGHT",
                "execution_lane_action": strict.get(alias, ""),
                "theme_coverage_count": 0,
            })
            continue

        keys = _theme_keys(pos)
        matched = theme_index.loc[[k for k in keys if k in theme_index.index]].copy() if keys else pd.DataFrame()
        if isinstance(matched, pd.Series):
            matched = matched.to_frame().T
        lane = "ETF_THEME" if _is_taiwan_etf(ticker) else "STOCK_THEME_PROXY"

        if matched.empty:
            records.append({
                "alias": alias,
                "lane": lane,
                "advisory_action": "RESEARCH_FIRST",
                "confidence": "LOW",
                "signal_state": "UNMAPPED",
                "signal_score": None,
                "trend_state": "UNKNOWN",
                "macro_support": _macro_support(pos, regime),
                "reason": "NO_MARKET_THEME_MAPPING",
                "execution_lane_action": strict.get(alias, ""),
                "theme_coverage_count": 0,
            })
            continue

        scores = matched.apply(_theme_score, axis=1)
        conf_w = matched["breadth_confidence"].astype(str).str.upper().map(CONF_WEIGHT).fillna(0.5)
        score = float((scores * conf_w).sum() / conf_w.sum()) if float(conf_w.sum()) > 0 else float(scores.mean())
        state = _classify(score)
        trend_state = _trend_state_from_breadth(state)
        macro_support = _macro_support(pos, regime)
        action, stance_reason = _position_stance(trend_state, macro_support)
        confidence = _confidence(lane, matched)
        reason = f"{stance_reason}_{lane}_{state}_MARKET_BREADTH"
        if lane == "STOCK_THEME_PROXY":
            reason += "_COMPANY_TRANSMISSION_NOT_EXACT"
            if confidence == "HIGH":
                confidence = "MEDIUM"

        records.append({
            "alias": alias,
            "lane": lane,
            "advisory_action": action,
            "confidence": confidence,
            "signal_state": state,
            "signal_score": round(score, 4),
            "trend_state": trend_state,
            "macro_support": macro_support,
            "reason": reason,
            "execution_lane_action": strict.get(alias, ""),
            "theme_coverage_count": int(len(matched)),
        })

    return {
        "contract": "ALPHA_HUNTER_EXISTING_POSITION_CIO_ADVISORY",
        "schema_version": "1.1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "privacy": {
            "alias_only": True,
            "ticker_included": False,
            "name_included": False,
            "balances_included": False,
            "weights_included": False,
            "risk_groups_included": False,
            "theme_names_included": False,
            "alias_mapping_published": False,
        },
        "rule": "Advisory only. Existing positions are evaluated as Trend x Theme-Macro Compatibility. Trend is derived from market breadth/relative-strength evidence, not entry reaction state. Rate-sensitive groups consume Treasury rate pressure without publishing private mappings. Execution remains frozen and separate.",
        "positions": records,
    }


def main() -> None:
    payload = build_position_cio_advisory()
    OUT.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Existing-position CIO advisory: records={len(payload['positions'])}; alias-only, no holdings identity published")


if __name__ == "__main__":
    main()
