from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from portfolio_risk import load_portfolio_state, load_risk_policy, validate_risk_inputs
from position_alias_output import load_alias_map

OUT = Path("output")
THEME_PATH = OUT / "theme_breadth.csv"
MANIFEST_PATH = OUT / "manifest.json"
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
RATE_CONDITIONAL_RISK_GROUPS = {"CRITICAL_MATERIALS"}
ADVERSE_REGIMES = {"CAUTION", "DEFENSIVE", "CRISIS"}

CONF_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.85, "LOW": 0.55}
RESIDUAL_WEIGHT_PCT = 0.10
POSITION_TREND_MIN_HISTORY = 65


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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_lineage() -> str:
    manifest = _load_json(MANIFEST_PATH)
    if manifest.get("status") != "PASS":
        raise RuntimeError("POSITION_CIO_CANONICAL_MANIFEST_NOT_PASS")
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise RuntimeError("POSITION_CIO_CANONICAL_RUN_ID_MISSING")
    auth = {str(r.get("relative_path")): r for r in (manifest.get("authoritative_files") or [])}
    row = auth.get("output/theme_breadth.csv")
    expected = str((row or {}).get("sha256") or "").strip().lower()
    if not expected or not THEME_PATH.exists() or _sha256(THEME_PATH).lower() != expected:
        raise RuntimeError("POSITION_CIO_THEME_BREADTH_LINEAGE_MISMATCH")
    return run_id


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


def _market_symbol_candidates(raw_ticker: Any) -> list[str]:
    raw = str(raw_ticker or "").strip().upper()
    if not raw:
        return []
    if raw.endswith(".TW") or raw.endswith(".TWO"):
        return [raw]
    key = _ticker_key(raw)
    if key.isdigit():
        return [f"{key}.TW", f"{key}.TWO"]
    return [raw]


def _close_series(hist: pd.DataFrame) -> pd.Series:
    if hist is None or hist.empty:
        return pd.Series(dtype=float)
    if isinstance(hist.columns, pd.MultiIndex):
        for level in range(hist.columns.nlevels):
            values = hist.columns.get_level_values(level)
            for field in ["Adj Close", "Close"]:
                if field in values:
                    try:
                        x = hist.xs(field, axis=1, level=level)
                        if isinstance(x, pd.DataFrame):
                            if x.shape[1] == 0:
                                continue
                            x = x.iloc[:, 0]
                        return pd.to_numeric(x, errors="coerce").dropna()
                    except Exception:
                        continue
        return pd.Series(dtype=float)
    col = "Adj Close" if "Adj Close" in hist.columns and hist["Adj Close"].notna().any() else "Close"
    if col not in hist.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(hist[col], errors="coerce").dropna()


def _classify_position_trend_from_close(s: pd.Series) -> dict[str, Any]:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < POSITION_TREND_MIN_HISTORY:
        return {"state": "UNKNOWN", "score": None, "as_of": None}
    ma20s = s.rolling(20).mean().dropna()
    ma60s = s.rolling(60).mean().dropna()
    if len(ma20s) < 6 or ma60s.empty:
        return {"state": "UNKNOWN", "score": None, "as_of": None}
    close = float(s.iloc[-1])
    ma20 = float(ma20s.iloc[-1])
    ma60 = float(ma60s.iloc[-1])
    slope20 = float(ma20s.iloc[-1] / ma20s.iloc[-6] - 1.0)
    ret20 = float(s.iloc[-1] / s.iloc[-21] - 1.0)
    ret60 = float(s.iloc[-1] / s.iloc[-61] - 1.0)
    votes = [close > ma20, ma20 > ma60, slope20 > 0, ret20 > 0, ret60 > 0]
    score = sum(bool(x) for x in votes) / len(votes)
    if score >= 0.8:
        state = "UPTREND"
    elif score <= 0.2:
        state = "DOWNTREND_OR_BROKEN"
    else:
        state = "MIXED"
    idx = pd.Timestamp(s.index[-1])
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return {"state": state, "score": round(score, 4), "as_of": idx.date().isoformat()}


def _position_trend(raw_ticker: Any) -> dict[str, Any]:
    for symbol in _market_symbol_candidates(raw_ticker):
        try:
            hist = yf.Ticker(symbol).history(period="1y", auto_adjust=False)
            s = _close_series(hist)
            result = _classify_position_trend_from_close(s)
            if result.get("state") != "UNKNOWN":
                return result
        except Exception:
            continue
    return {"state": "UNKNOWN", "score": None, "as_of": None}


def _macro_support(pos: dict[str, Any], regime: dict[str, Any]) -> str:
    if not regime or regime.get("status") != "READY":
        return "UNKNOWN"
    label = str(regime.get("regime", "UNKNOWN")).upper()
    if label in ADVERSE_REGIMES:
        return "ADVERSE"

    groups = set(_groups(pos))
    rate_pressure = str((regime.get("signals") or {}).get("rate_pressure", "UNKNOWN")).upper()
    if groups & RATE_SENSITIVE_RISK_GROUPS:
        if rate_pressure == "ADVERSE":
            return "ADVERSE"
        if rate_pressure == "SUPPORTIVE":
            return "SUPPORTIVE"
        return "CONDITIONAL"
    if groups & RATE_CONDITIONAL_RISK_GROUPS and rate_pressure == "ADVERSE":
        return "CONDITIONAL"
    if label in {"RISK_ON", "NORMAL"}:
        return "SUPPORTIVE"
    return "UNKNOWN"


def _position_stance(trend_state: str, macro_support: str) -> tuple[str, str]:
    if trend_state == "UPTREND" and macro_support == "SUPPORTIVE":
        return "HOLD_BIAS", "UPTREND_MACRO_SUPPORTIVE"
    if trend_state == "UPTREND":
        return "REVIEW_HOLD", "UPTREND_MACRO_NOT_FULLY_SUPPORTIVE"
    if trend_state == "DOWNTREND_OR_BROKEN" and macro_support != "SUPPORTIVE":
        return "REDUCE_BIAS", "DOWNTREND_WITHOUT_SUPPORTIVE_MACRO"
    if trend_state == "DOWNTREND_OR_BROKEN":
        return "REVIEW_HOLD", "WAIT_FOR_TREND_RECOVERY"
    if trend_state == "MIXED" and macro_support == "ADVERSE":
        return "REDUCE_BIAS", "MIXED_TREND_WITH_ADVERSE_MACRO"
    return "REVIEW_HOLD", "MIXED_OR_UNCERTAIN_TREND"


def _confidence(lane: str, rows: pd.DataFrame, trend_state: str) -> str:
    if trend_state == "UNKNOWN":
        return "LOW"
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
    source_run_id = _canonical_lineage()

    policy = load_risk_policy()
    raw_portfolio = load_portfolio_state()
    valid, blockers, portfolio = validate_risk_inputs(policy, raw_portfolio)
    if not valid:
        raise RuntimeError("POSITION_CIO_PRIVATE_INPUTS_INVALID:" + ";".join(blockers))

    alias_map = load_alias_map(portfolio)
    strict = _strict_actions_by_alias()
    regime = _load_json(REGIME_PATH)
    regime_source = str(regime.get("source_run_id") or "")
    if regime_source and regime_source != source_run_id:
        raise RuntimeError("POSITION_CIO_RISK_REGIME_LINEAGE_MISMATCH")
    themes = pd.read_csv(THEME_PATH)
    themes["theme"] = themes["theme"].astype(str)
    theme_index = themes.set_index("theme", drop=False)

    records: list[dict[str, Any]] = []
    for pos in portfolio.get("positions") or []:
        raw_ticker = pos.get("ticker")
        ticker = _ticker_key(raw_ticker)
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
                "trend_score": None,
                "trend_as_of": None,
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
        trend = _position_trend(raw_ticker)
        trend_state = str(trend.get("state", "UNKNOWN"))
        macro_support = _macro_support(pos, regime)

        if matched.empty:
            records.append({
                "alias": alias,
                "lane": lane,
                "advisory_action": "RESEARCH_FIRST",
                "confidence": "LOW",
                "signal_state": "UNMAPPED",
                "signal_score": None,
                "trend_state": trend_state,
                "trend_score": trend.get("score"),
                "trend_as_of": trend.get("as_of"),
                "macro_support": macro_support,
                "reason": "NO_MARKET_THEME_MAPPING",
                "execution_lane_action": strict.get(alias, ""),
                "theme_coverage_count": 0,
            })
            continue

        scores = matched.apply(_theme_score, axis=1)
        conf_w = matched["breadth_confidence"].astype(str).str.upper().map(CONF_WEIGHT).fillna(0.5)
        score = float((scores * conf_w).sum() / conf_w.sum()) if float(conf_w.sum()) > 0 else float(scores.mean())
        theme_state = _classify(score)
        action, stance_reason = _position_stance(trend_state, macro_support)
        confidence = _confidence(lane, matched, trend_state)
        reason = f"{stance_reason}_{lane}_{theme_state}_THEME_SUPPORT"
        if lane == "STOCK_THEME_PROXY":
            reason += "_COMPANY_TRANSMISSION_NOT_EXACT"
            if confidence == "HIGH":
                confidence = "MEDIUM"

        records.append({
            "alias": alias,
            "lane": lane,
            "advisory_action": action,
            "confidence": confidence,
            "signal_state": theme_state,
            "signal_score": round(score, 4),
            "trend_state": trend_state,
            "trend_score": trend.get("score"),
            "trend_as_of": trend.get("as_of"),
            "macro_support": macro_support,
            "reason": reason,
            "execution_lane_action": strict.get(alias, ""),
            "theme_coverage_count": int(len(matched)),
        })

    return {
        "contract": "ALPHA_HUNTER_EXISTING_POSITION_CIO_ADVISORY",
        "schema_version": "1.2",
        "source_run_id": source_run_id,
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
        "rule": "Advisory only. Existing-position trend comes from the actual held instrument price history. Theme breadth is confirmation/support only and can never substitute for position trend. Macro compatibility is evaluated separately. Canonical scanner lineage is enforced before publication.",
        "positions": records,
    }


def main() -> None:
    payload = build_position_cio_advisory()
    OUT.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Existing-position CIO advisory: run_id={payload.get('source_run_id')} records={len(payload['positions'])}; alias-only")


if __name__ == "__main__":
    main()
