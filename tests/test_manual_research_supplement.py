from pathlib import Path

import pandas as pd

from manual_research_queue import load_industry_map, load_peer_map


def test_current_scan_research_supplement_has_118_unique_companies():
    supplement = pd.read_csv(Path("config/manual_industry_map_supplement.csv"), dtype={"code": str})
    assert len(supplement) == 118
    assert supplement["code"].nunique() == 118
    assert not supplement["primary_driver_id"].eq("UNMAPPED").any()
    assert set(supplement["classification_confidence"]) <= {"LOW", "MEDIUM", "HIGH"}


def test_merged_ontology_has_no_duplicate_company_codes():
    merged = load_industry_map()
    assert not merged["code"].duplicated().any()


def test_every_merged_primary_driver_has_at_least_two_global_peers():
    industry = load_industry_map()
    peers = load_peer_map()
    mapped = set(industry["primary_driver_id"].dropna().astype(str))
    peer_drivers = set(peers["driver_id"].dropna().astype(str))
    assert mapped <= peer_drivers
    counts = peers.groupby("driver_id")["ticker"].nunique()
    assert counts.loc[list(mapped)].min() >= 2


def test_researched_supplement_maps_cross_sector_representatives():
    m = load_industry_map().set_index("code")
    expected = {
        "7799": "BNCT_RADIOTHERAPY_ADOPTION",
        "6706": "OPTO_TEST_EQUIPMENT_CYCLE",
        "2254": "AUTO_LIGHTING_AFTERMARKET",
        "9933": "ENGINEERING_EPC_CAPEX",
        "7765": "ENTERPRISE_CYBER_SPEND",
        "3443": "ASIC_DESIGN_SERVICES",
        "3034": "DISPLAY_DRIVER_IC_CYCLE",
        "2636": "GLOBAL_FREIGHT_FORWARDING",
        "2338": "PHOTOMASK_DEMAND",
        "8227": "ASIC_DESIGN_SERVICES",
        "6683": "TEST_INTERFACE_CAPEX",
        "3055": "ADVANCED_PACKAGING_TEST_CAPEX",
        "6620": "SPECIALTY_PHARMA_CYCLE",
    }
    for code, driver in expected.items():
        assert m.loc[code, "primary_driver_id"] == driver


def test_context_only_or_weak_transmissions_are_not_overstated():
    m = load_industry_map().set_index("code")
    assert m.loc["2905", "classification_confidence"] == "LOW"
    assert m.loc["3176", "classification_confidence"] == "LOW"
    assert m.loc["6945", "classification_confidence"] == "LOW"
    assert m.loc["2820", "classification_confidence"] == "MEDIUM"
