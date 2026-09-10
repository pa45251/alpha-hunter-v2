from __future__ import annotations

import json
import pandas as pd

import portfolio_allocation_advisory as paa


def _policy():
    return {
        "rotation": {
            "min_edge_spread": 0.18,
            "strong_edge_spread": 0.35,
            "max_source_trim_pct": {"RISK_ON": 50, "NORMAL": 40, "CAUTION": 25, "DEFENSIVE": 15, "CRISIS": 0, "UNKNOWN": 0},
            "redeploy_pct_of_trim": {"RISK_ON": 100, "NORMAL": 75, "CAUTION": 50, "DEFENSIVE": 25, "CRISIS": 0, "UNKNOWN": 0},
        }
    }


def _run_case(tmp_path, monkeypatch, reaction_state: str, rate_pressure: str = "SUPPORTIVE", trend: str = "UP", global_theme: str = "AI_Server"):
    policy = _policy()
    pos = {
        "positions": [
            {"alias": "標的D", "advisory_action": "REVIEW_HOLD", "signal_score": 0.41, "confidence": "MEDIUM", "signal_state": "MIXED", "trend_state": "MIXED", "macro_support": "SUPPORTIVE"},
            {"alias": "標的B", "advisory_action": "HOLD_BIAS", "signal_score": 0.94, "confidence": "MEDIUM", "signal_state": "STRONG", "trend_state": "UPTREND", "macro_support": "SUPPORTIVE"},
        ]
    }
    cand = {
        "top_advisories": [
            {
                "ticker": "2317.TW", "name": "鴻海", "preferred_exposure": "STOCK",
                "advisory_action": "BUY_BIAS_STOCK", "advisory_confidence": "MEDIUM",
                "reaction_state": reaction_state, "provenance_status": "SOURCE_BACKED",
                "research_priority_score": 0.67, "driver_id": "AI_SERVER_SHIPMENTS",
                "global_theme": global_theme, "advisory_missing_evidence": "",
            }
        ]
    }
    regime = {"status": "READY", "regime": "NORMAL", "risk_score": 28, "target_cash_pct": 5, "signals": {"rate_pressure": rate_pressure}}
    if trend == "UP":
        theme = {"theme":global_theme,"above_ma20_pct":1.0,"above_ma60_pct":1.0,"positive_rs20_pct":1.0,"positive_rs5_pct":1.0,"near_20d_high_pct":0.8}
    else:
        theme = {"theme":global_theme,"above_ma20_pct":0.0,"above_ma60_pct":0.0,"positive_rs20_pct":0.0,"positive_rs5_pct":0.0,"near_20d_high_pct":0.0}

    files = {}
    for name, payload in [("policy.json", policy), ("pos.json", pos), ("cand.json", cand), ("regime.json", regime)]:
        p = tmp_path / name
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        files[name] = p
    theme_path = tmp_path / "theme.csv"
    pd.DataFrame([theme]).to_csv(theme_path, index=False)

    monkeypatch.setattr(paa, "POLICY_PATH", files["policy.json"])
    monkeypatch.setattr(paa, "POSITION_PATH", files["pos.json"])
    monkeypatch.setattr(paa, "CANDIDATE_PATH", files["cand.json"])
    monkeypatch.setattr(paa, "REGIME_PATH", files["regime.json"])
    monkeypatch.setattr(paa, "THEME_PATH", theme_path)
    return paa.build_portfolio_allocation()


def test_preconfirmation_prepares_but_does_not_trim_now(tmp_path, monkeypatch):
    out = _run_case(tmp_path, monkeypatch, "PRE_CONFIRMATION")
    assert out["status"] == "READY"
    assert out["best_new_opportunity"]["trend_state"] == "UPTREND"
    r = out["rotations"][0]
    assert r["source_alias"] == "標的D"
    assert r["rotation_action"] == "PREPARE_ROTATION_STRONG"
    assert r["suggested_source_trim_pct_now"] == 0
    assert r["suggested_source_trim_pct_on_trigger"] == 40


def test_confirming_allows_partial_rotation_bias(tmp_path, monkeypatch):
    out = _run_case(tmp_path, monkeypatch, "CONFIRMING")
    r = out["rotations"][0]
    assert r["rotation_action"] == "ROTATE_PARTIAL_STRONG"
    assert r["suggested_source_trim_pct_now"] == 40


def test_pullback_can_be_bought_only_when_trend_and_macro_support(tmp_path, monkeypatch):
    out = _run_case(tmp_path, monkeypatch, "PULLBACK", rate_pressure="SUPPORTIVE", trend="UP")
    best = out["best_new_opportunity"]
    assert best["trend_state"] == "UPTREND"
    assert best["trend_regime_stance"] == "BUY_PULLBACK_CANDIDATE"
    assert out["rotations"][0]["rotation_action"] == "BUY_PULLBACK_ROTATION_STRONG"


def test_rate_pressure_vetoes_rate_sensitive_pullback(tmp_path, monkeypatch):
    out = _run_case(tmp_path, monkeypatch, "PULLBACK", rate_pressure="ADVERSE", trend="UP", global_theme="Biotech")
    best = out["best_new_opportunity"]
    assert best["trend_state"] == "UPTREND"
    assert best["macro_support"] == "ADVERSE"
    assert best["trend_regime_stance"] == "WAIT_REGIME"
    assert out["rotations"][0]["rotation_action"] == "WAIT_REGIME"


def test_downtrend_is_not_relabelled_uptrend_by_pullback_reaction(tmp_path, monkeypatch):
    out = _run_case(tmp_path, monkeypatch, "PULLBACK", trend="DOWN")
    best = out["best_new_opportunity"]
    assert best["trend_state"] == "DOWNTREND_OR_BROKEN"
    assert best["trend_regime_stance"] == "WAIT_RECOVERY"
    assert out["rotations"][0]["rotation_action"] == "WAIT_TREND"


def test_crisis_blocks_rotation():
    size_state, trim = paa._rotation_size(0.60, "CRISIS", _policy())
    assert size_state == "NO_ROTATION"
    assert trim == 0
