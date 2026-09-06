from __future__ import annotations

import json

import portfolio_allocation_advisory as paa


def test_rotation_prefers_strong_new_edge(tmp_path, monkeypatch):
    policy = {
        "rotation": {
            "min_edge_spread": 0.18,
            "strong_edge_spread": 0.35,
            "max_source_trim_pct": {"RISK_ON": 50, "NORMAL": 40, "CAUTION": 25, "DEFENSIVE": 15, "CRISIS": 0, "UNKNOWN": 0},
            "redeploy_pct_of_trim": {"RISK_ON": 100, "NORMAL": 75, "CAUTION": 50, "DEFENSIVE": 25, "CRISIS": 0, "UNKNOWN": 0},
        }
    }
    pos = {
        "positions": [
            {"alias": "標的D", "advisory_action": "REVIEW_HOLD", "signal_score": 0.41, "confidence": "MEDIUM", "signal_state": "MIXED"},
            {"alias": "標的B", "advisory_action": "HOLD_BIAS", "signal_score": 0.94, "confidence": "MEDIUM", "signal_state": "STRONG"},
        ]
    }
    cand = {
        "top_advisories": [
            {
                "ticker": "2317.TW", "name": "鴻海", "preferred_exposure": "STOCK",
                "advisory_action": "BUY_BIAS_STOCK", "advisory_confidence": "MEDIUM",
                "reaction_state": "PRE_CONFIRMATION", "provenance_status": "SOURCE_BACKED",
                "research_priority_score": 0.67, "driver_id": "AI_SERVER_SHIPMENTS",
                "advisory_missing_evidence": "",
            }
        ]
    }
    regime = {"status": "READY", "regime": "NORMAL", "risk_score": 28, "target_cash_pct": 5}

    files = {}
    for name, payload in [("policy.json", policy), ("pos.json", pos), ("cand.json", cand), ("regime.json", regime)]:
        p = tmp_path / name
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        files[name] = p

    monkeypatch.setattr(paa, "POLICY_PATH", files["policy.json"])
    monkeypatch.setattr(paa, "POSITION_PATH", files["pos.json"])
    monkeypatch.setattr(paa, "CANDIDATE_PATH", files["cand.json"])
    monkeypatch.setattr(paa, "REGIME_PATH", files["regime.json"])

    out = paa.build_portfolio_allocation()
    assert out["status"] == "READY"
    assert out["best_new_opportunity"]["ticker"] == "2317.TW"
    assert len(out["rotations"]) == 1
    r = out["rotations"][0]
    assert r["source_alias"] == "標的D"
    assert r["destination_ticker"] == "2317.TW"
    assert r["rotation_action"] == "ROTATE_PARTIAL_STRONG"
    assert r["suggested_source_trim_pct"] == 40
    assert r["suggested_redeploy_pct_of_trim"] == 75
    assert r["suggested_risk_buffer_pct_of_trim"] == 25


def test_crisis_blocks_rotation():
    policy = {
        "rotation": {
            "min_edge_spread": 0.18, "strong_edge_spread": 0.35,
            "max_source_trim_pct": {"CRISIS": 0, "UNKNOWN": 0},
        }
    }
    action, trim = paa._rotation_action(0.60, "CRISIS", policy)
    assert action == "NO_ROTATION"
    assert trim == 0
