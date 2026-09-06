import json

import pandas as pd
import pytest

import research_activation_bridge_v3 as bridge


def _write_fixture(tmp_path, research_run_id="run-1"):
    out = tmp_path / "output"
    out.mkdir()
    (out / "manifest.json").write_text(json.dumps({"run_id": "run-1"}), encoding="utf-8")
    pd.DataFrame([
        {"run_id": "run-1", "driver_id": "AI_SERVER_SHIPMENTS"},
        {"run_id": "run-1", "driver_id": "CONTAINER_FREIGHT"},
    ]).to_csv(out / "causal_research_queue.csv", index=False)
    research = {
        "contract": "ALPHA_HUNTER_V3_VALIDATED_RESEARCH",
        "status": "PASS",
        "research_run_id": research_run_id,
        "validated_at_utc": "2026-09-06T06:42:03Z",
        "results": [
            {
                "driver_id": "AI_SERVER_SHIPMENTS",
                "state": "ACTIVE",
                "confidence": 0.83,
                "primary_cause": "orders/backlog evidence",
                "industry_scope": "COMPANY_SPECIFIC",
                "supporting_evidence": [{
                    "claim": "record orders",
                    "source_title": "Primary results",
                    "source_url": "https://example.com/a",
                }],
                "counter_evidence": [],
                "source_count": 1,
                "researched_at_utc": "2026-09-06T06:40:59Z",
                "research_run_id": research_run_id,
            },
            {
                "driver_id": "CONTAINER_FREIGHT",
                "state": "UNKNOWN",
                "confidence": 0.18,
                "primary_cause": "insufficient evidence",
                "industry_scope": "UNKNOWN",
                "supporting_evidence": [],
                "counter_evidence": [],
                "source_count": 0,
                "researched_at_utc": "2026-09-06T06:40:59Z",
                "research_run_id": research_run_id,
            },
        ],
    }
    (out / "research_result_v3.json").write_text(json.dumps(research), encoding="utf-8")
    return out


def _patch_paths(monkeypatch, out):
    monkeypatch.setattr(bridge, "OUT", out)
    monkeypatch.setattr(bridge, "MANIFEST", out / "manifest.json")
    monkeypatch.setattr(bridge, "QUEUE", out / "causal_research_queue.csv")
    monkeypatch.setattr(bridge, "RESEARCH", out / "research_result_v3.json")
    monkeypatch.setattr(bridge, "ACTIVATION_OUT", out / "driver_activation_v3.csv")


def test_bridge_writes_same_snapshot_activation(monkeypatch, tmp_path):
    out = _write_fixture(tmp_path)
    _patch_paths(monkeypatch, out)
    bridge.main()
    df = pd.read_csv(out / "driver_activation_v3.csv")
    assert list(df["driver_id"]) == ["AI_SERVER_SHIPMENTS", "CONTAINER_FREIGHT"]
    assert list(df["activation_state"]) == ["ACTIVE", "UNKNOWN"]
    assert df["research_run_id"].eq("run-1").all()
    assert df["activation_source"].eq("V3_AUTONOMOUS_RESEARCH").all()


def test_bridge_rejects_mixed_snapshot(monkeypatch, tmp_path):
    out = _write_fixture(tmp_path, research_run_id="wrong-run")
    _patch_paths(monkeypatch, out)
    with pytest.raises(RuntimeError, match="MIXED_SNAPSHOT_DATA"):
        bridge.main()
