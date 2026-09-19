from pathlib import Path

import pandas as pd

from manual_research_queue import build_driver_breadth, build_manual_queue, load_industry_map


def test_priority_industry_ontology_has_expected_subindustries():
    m = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str})
    by_code = m.set_index("code")
    assert by_code.loc["3008", "economic_subindustry"] == "Mobile_Optics"
    assert by_code.loc["2481", "economic_subindustry"] == "Diode_Discrete"
    assert by_code.loc["2383", "economic_subindustry"] == "CCL_HighSpeed"
    assert by_code.loc["3533", "economic_subindustry"] == "Server_Connector"
    assert by_code.loc["2472", "economic_subindustry"] == "Capacitor"


def test_core_sector_ontology_expansion_maps_representative_taiwan_names():
    m = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str}).set_index("code")
    expected = {
        "3029": "ENTERPRISE_CYBER_SPEND",
        "6689": "CLOUD_MSP_ENTERPRISE_SPEND",
        "2345": "AI_NETWORKING_UPGRADE",
        "2382": "AI_SERVER_SHIPMENTS",
        "3017": "DATACENTER_COOLING_INFRA",
        "3131": "WAFER_FAB_EQUIPMENT_CAPEX",
        "6223": "ADVANCED_PACKAGING_TEST_CAPEX",
        "2408": "DRAM_PRICING",
        "8299": "NAND_STORAGE_CYCLE",
        "1519": "GRID_CAPEX",
        "2330": "LEADING_EDGE_FOUNDRY_AI_DEMAND",
        "2303": "MATURE_NODE_FOUNDRY_UTILIZATION",
        "2603": "CONTAINER_FREIGHT",
        "2606": "DRY_BULK_FREIGHT",
        "2801": "FINANCIALS_RATE_CREDIT_CYCLE",
    }
    for code, driver in expected.items():
        assert m.loc[code, "primary_driver_id"] == driver


def test_core_sector_mapping_keeps_weak_transmission_conservative():
    m = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str}).set_index("code")
    assert m.loc["3029", "classification_confidence"] == "MEDIUM"
    assert m.loc["6416", "classification_confidence"] == "MEDIUM"
    assert m.loc["2801", "classification_confidence"] == "MEDIUM"
    assert "context only" in m.loc["2801", "notes"].lower()


def test_manual_industry_map_has_unique_company_codes():
    m = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str})
    assert not m["code"].duplicated().any()


def test_every_manual_driver_has_configured_international_peers():
    m = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str})
    p = pd.read_csv(Path("config/manual_global_peers.csv"))
    mapped = set(m["primary_driver_id"].dropna().astype(str))
    peer_drivers = set(p["driver_id"].dropna().astype(str))
    assert mapped <= peer_drivers
    assert p.groupby("driver_id")["ticker"].nunique().min() >= 2


def test_new_core_sector_peer_baskets_have_expected_context():
    p = pd.read_csv(Path("config/manual_global_peers.csv"))
    peers = p.groupby("driver_id")["ticker"].apply(set).to_dict()
    assert {"HACK", "PANW"} <= peers["ENTERPRISE_CYBER_SPEND"]
    assert {"SKYY", "MSFT"} <= peers["CLOUD_MSP_ENTERPRISE_SPEND"]
    assert {"ANET", "MRVL"} <= peers["AI_NETWORKING_UPGRADE"]
    assert {"DELL", "SMCI"} <= peers["AI_SERVER_SHIPMENTS"]
    assert {"VRT", "ETN"} <= peers["DATACENTER_POWER_INFRA"]
    assert {"AMAT", "LRCX"} <= peers["WAFER_FAB_EQUIPMENT_CAPEX"]
    assert {"MU", "000660.KS"} <= peers["DRAM_PRICING"]
    assert {"GEV", "HUBB"} <= peers["GRID_CAPEX"]
    assert {"TSM", "005930.KS"} <= peers["LEADING_EDGE_FOUNDRY_AI_DEMAND"]
    assert {"GFS", "0981.HK"} <= peers["MATURE_NODE_FOUNDRY_UTILIZATION"]
    assert {"ZIM", "MAERSK-B.CO"} <= peers["CONTAINER_FREIGHT"]
    assert {"SBLK", "9101.T"} <= peers["DRY_BULK_FREIGHT"]
    assert {"XLF", "JPM"} <= peers["FINANCIALS_RATE_CREDIT_CYCLE"]


def test_peer_map_excludes_delisted_shinko_and_uses_live_replacements():
    p = pd.read_csv(Path("config/manual_global_peers.csv"))
    tickers = set(p["ticker"].astype(str))
    assert "6967.T" not in tickers
    assert "6787.T" in tickers
    package = p[p["driver_id"].eq("PACKAGE_SUBSTRATE_DEMAND")]
    assert "009150.KS" in set(package["ticker"].astype(str))


def test_manual_queue_preserves_unmapped_candidates_for_human_research():
    candidates = pd.DataFrame([
        {"candidate_rank": 1, "code": "3008", "ticker": "3008.TW", "name": "大立光", "industry": "光電業"},
        {"candidate_rank": 2, "code": "9999", "ticker": "9999.TW", "name": "Unknown", "industry": "其他"},
    ])
    industry_map = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str})
    peers = pd.read_csv(Path("config/manual_global_peers.csv"))
    breadth = build_driver_breadth(pd.DataFrame(), peers)
    queue = build_manual_queue(candidates, industry_map, breadth)
    mapped = queue.set_index("code")
    assert mapped.loc["3008", "primary_driver_id"] == "MOBILE_OPTICS_UPGRADE"
    assert mapped.loc["9999", "primary_driver_id"] == "UNMAPPED"
    assert bool(mapped.loc["9999", "manual_deep_research_required"])


def test_driver_breadth_is_context_not_trade_action():
    peers = pd.DataFrame([
        {"driver_id": "X", "driver_label": "X driver", "global_theme": "X", "ticker": "A", "name": "A", "benchmark": "SPY"},
        {"driver_id": "X", "driver_label": "X driver", "global_theme": "X", "ticker": "B", "name": "B", "benchmark": "SPY"},
    ])
    live = pd.DataFrame([
        {"driver_id": "X", "above_ma20": True, "above_ma60": True, "rs_20d_vs_local_benchmark": 0.05, "ret_20d": 0.10},
        {"driver_id": "X", "above_ma20": True, "above_ma60": False, "rs_20d_vs_local_benchmark": 0.02, "ret_20d": 0.04},
    ])
    out = build_driver_breadth(live, peers)
    assert out.iloc[0]["peer_signal"] == "BROADLY_POSITIVE"
    assert not any(c.lower() in {"buy", "sell", "action"} for c in out.columns)


def test_missing_relative_strength_fails_closed():
    peers = pd.DataFrame([
        {"driver_id": "X", "driver_label": "X driver", "global_theme": "X",
         "ticker": "A", "name": "A", "benchmark": "SPY"},
        {"driver_id": "X", "driver_label": "X driver", "global_theme": "X",
         "ticker": "B", "name": "B", "benchmark": "SPY"},
    ])
    live = pd.DataFrame([
        {"driver_id": "X", "above_ma20": True, "above_ma60": True,
         "rs_20d_vs_local_benchmark": float("nan"), "ret_20d": 0.10},
        {"driver_id": "X", "above_ma20": True, "above_ma60": True,
         "rs_20d_vs_local_benchmark": float("nan"), "ret_20d": 0.08},
    ])
    out = build_driver_breadth(live, peers)
    assert out.iloc[0]["peer_signal"] == "DATA_UNAVAILABLE"


def test_canonical_structural_graph_covers_current_taiwan_candidates():
    candidates = pd.read_csv(Path("output/taiwan_candidates.csv"), dtype={"code": str})
    mapping = load_industry_map().set_index("code")
    codes = candidates["code"].astype(str).str.zfill(4)
    missing = [code for code in codes if code not in mapping.index]
    assert missing == []


def test_manual_research_mapping_preserves_base_and_thesis_layers():
    mapping = load_industry_map().set_index("code")
    row = mapping.loc["3035"]
    assert row["mapping_source"] == "STRUCTURAL_EXPOSURE_GRAPH"
    assert "ASIC_DESIGN_SERVICE_CYCLE" in row["base_driver_ids"].split(";")
    assert "ADVANCED_PACKAGING_TEST_CAPEX" in row["thesis_driver_ids"].split(";")
    assert row["primary_driver_id"] == "ADVANCED_PACKAGING_TEST_CAPEX"


def test_new_candidate_mapping_uses_structural_source_not_legacy_fallback():
    mapping = load_industry_map().set_index("code")
    expected = {
        "2449": "SEMICONDUCTOR_TEST_CYCLE",
        "6533": "ASIC_DESIGN_SERVICE_CYCLE",
        "4979": "OPTICAL_COMPONENT_DEMAND",
        "6278": "ELECTRONICS_MANUFACTURING_SERVICES_CYCLE",
        "2395": "INDUSTRIAL_EDGE_COMPUTING_CYCLE",
        "8932": "ENTERPRISE_SOFTWARE_CYCLE",
    }
    for code, driver in expected.items():
        assert mapping.loc[code, "primary_driver_id"] == driver
        assert mapping.loc[code, "mapping_source"] == "STRUCTURAL_EXPOSURE_GRAPH"


def test_every_enabled_structural_driver_has_international_peer_context():
    graph = pd.read_csv(Path("config/structural_exposure_graph.csv"), dtype={"taiwan_code": str})
    graph = graph[pd.to_numeric(graph["enabled"], errors="coerce").fillna(0).eq(1)]
    peers = pd.read_csv(Path("config/manual_global_peers.csv"))
    used = set(graph["driver_id"].dropna().astype(str))
    peer_drivers = set(peers["driver_id"].dropna().astype(str))
    assert used <= peer_drivers
