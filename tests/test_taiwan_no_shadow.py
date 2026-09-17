import json

import pandas as pd

import daily_scan


def test_write_taiwan_outputs_removes_legacy_shadow(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    legacy = out / "taiwan_shadow_universe.csv"
    legacy.write_text("ticker\nOLD.TW\n", encoding="utf-8")
    monkeypatch.setattr(daily_scan, "OUT", out)
    tw = {
        "candidates": pd.DataFrame([{"ticker": "A.TW"}]),
        "breadth": pd.DataFrame([{"theme": "X"}]),
        "universe": pd.DataFrame([{"ticker": "A.TW"}, {"ticker": "B.TW"}]),
    }
    daily_scan.write_taiwan_outputs(tw)
    assert (out / "taiwan_candidates.csv").exists()
    assert not legacy.exists()


def test_manifest_has_rejected_count_but_no_shadow_contract(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr(daily_scan, "OUT", out)

    required = [
        "global_scan_quality.json", "discovery_snapshot.csv", "discovery_research_queue.csv",
        "risk_regime.json", "market_snapshot.csv", "theme_breadth.csv", "leader_registry.csv", "feature_history.csv",
        "market_snapshot.json", "taiwan_candidates.csv", "taiwan_candidate_history.csv",
        "taiwan_industry_breadth.csv", "taiwan_universe.csv", "causal_research_queue.csv",
        "reverse_transmission_candidates.csv", "structural_matches.csv", "causal_graph_audit.csv",
        "causal_driver_taxonomy.csv", "structural_exposure_graph.csv",
    ]
    for name in required:
        (out / name).write_text("x", encoding="utf-8")

    global_results = {
        "stocks": pd.DataFrame([
            {"ticker": f"G{i}", "theme": "T", "last_price_date": "2026-09-16"}
            for i in range(100)
        ]),
        "core_quality": {"universe_count": 100},
        "discovery_quality": {},
    }
    stocks = pd.DataFrame([
        {"ticker": "A.TW", "industry": "I", "last_price_date": "2026-09-16"},
        {"ticker": "B.TW", "industry": "I", "last_price_date": "2026-09-16"},
        {"ticker": "C.TW", "industry": "J", "last_price_date": "2026-09-16"},
    ])
    tw = {
        "stocks": stocks,
        "universe": stocks.copy(),
        "candidates": stocks.iloc[:1].copy(),
        "universe_source_status": "TEST",
    }
    research_queue = pd.DataFrame([{"driver_id": "D"}])
    reverse = pd.DataFrame([{"driver_id": "D"}])
    structural = pd.DataFrame([{"dynamic_driver_state": "UNRESOLVED"}])
    graph_audit = pd.DataFrame([{"ok": True}])
    activations = pd.DataFrame()

    daily_scan.build_manifest(
        global_results, tw, research_queue, reverse, structural, graph_audit,
        activations, "run", {"no_shadow_contract": True},
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    names = {f["name"] for f in manifest["authoritative_files"]}
    assert "taiwan_shadow_universe.csv" not in names
    assert manifest["taiwan"]["candidate_count"] == 1
    assert manifest["taiwan"]["rejected_count"] == 2
    assert "shadow_count" not in manifest["taiwan"]
    assert "primary_shadow_partition_complete" not in manifest["taiwan"]
    assert manifest["status"] == "PASS"
