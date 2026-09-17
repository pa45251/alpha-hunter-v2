from pathlib import Path

import pandas as pd

from manual_research_queue import load_industry_map, load_peer_map


def test_audited_mapping_corrections_override_supplement():
    m = load_industry_map().set_index("code")
    assert m.loc["2305", "primary_driver_id"] == "DOCUMENT_SCANNER_IMAGING_CYCLE"
    assert m.loc["2305", "classification_confidence"] == "HIGH"
    assert m.loc["6199", "primary_driver_id"] == "FUNERAL_SERVICES_CYCLE"
    assert m.loc["6199", "classification_confidence"] == "HIGH"
    assert m.loc["6199", "secondary_driver_ids"] == ""


def test_document_scanner_driver_has_direct_international_peers():
    p = load_peer_map()
    x = p[p["driver_id"].eq("DOCUMENT_SCANNER_IMAGING_CYCLE")]
    assert {"7751.T", "6724.T"} <= set(x["ticker"].astype(str))
    assert set(x["peer_role"]) == {"DIRECT_PEER"}


def test_stale_peer_tickers_are_excluded_and_replaced():
    p = load_peer_map()
    tickers = set(p["ticker"].astype(str))
    assert {"SNBR", "MPX", "BASF.DE"}.isdisjoint(tickers)
    assert {"PRPL", "MCFT", "BAS.DE"} <= tickers

    smart_bed = p[p["driver_id"].eq("RETAIL_FIXTURE_SMART_BED_DEMAND")]
    luxury_boat = p[p["driver_id"].eq("LUXURY_BOAT_CYCLE")]
    chemicals = p[p["driver_id"].eq("SPECIALTY_CHEMICALS_CYCLE")]
    assert {"PRPL", "SGI"} <= set(smart_bed["ticker"].astype(str))
    assert {"MCFT", "BC"} <= set(luxury_boat["ticker"].astype(str))
    assert {"BAS.DE", "HUN"} <= set(chemicals["ticker"].astype(str))


def test_latest_scan_38_unmapped_candidates_are_curated():
    m = load_industry_map().set_index("code")
    expected = {
        "7717": "OPTICAL_COMPONENT_DEMAND",
        "8103": "HIGH_SPEED_CONNECTOR_DEMAND",
        "2489": "CONSUMER_ELECTRONICS_CYCLE",
        "1560": "SEMICONDUCTOR_FAB_UTILIZATION_CONSUMABLES",
        "6782": "CONTACT_LENS_DEMAND",
        "3491": "LEO_SATCOM_DEPLOYMENT",
        "2371": "GRID_CAPEX",
        "6668": "PRECISION_OPTICS_DEMAND",
        "3714": "LED_COMPONENT_CYCLE",
        "6617": "CLINICAL_REGULATORY_COMMERCIALIZATION",
        "6588": "AI_NETWORKING_UPGRADE",
        "2834": "FINANCIALS_RATE_CREDIT_CYCLE",
        "3532": "SILICON_WAFER_DEMAND_PRICING",
        "2851": "REINSURANCE_PRICING_CATA_CYCLE",
        "6426": "AI_NETWORKING_UPGRADE",
        "2354": "CONSUMER_ELECTRONICS_CYCLE",
        "2377": "PC_DEVICE_CYCLE",
        "2845": "FINANCIALS_RATE_CREDIT_CYCLE",
        "2207": "TAIWAN_AUTO_DEMAND",
        "2426": "LED_COMPONENT_CYCLE",
        "8021": "HIGH_LAYER_PCB_DEMAND",
        "6530": "AI_NETWORKING_UPGRADE",
        "3339": "OPTICAL_COMPONENT_DEMAND",
        "2201": "TAIWAN_AUTO_DEMAND",
        "6291": "ANALOG_PMIC_DEMAND",
        "2855": "CAPITAL_MARKETS_ACTIVITY",
        "3264": "ADVANCED_PACKAGING_TEST_CAPEX",
        "5443": "ADVANCED_PACKAGING_TEST_CAPEX",
        "8431": "AI_SERVER_THERMAL_DENSITY",
        "3105": "MOBILE_RF_FRONTEND_DEMAND",
        "2885": "CAPITAL_MARKETS_ACTIVITY",
        "2466": "POWER_ELECTRONICS_CAPEX",
        "2455": "MOBILE_RF_FRONTEND_DEMAND",
        "6005": "CAPITAL_MARKETS_ACTIVITY",
        "6257": "ADVANCED_PACKAGING_TEST_CAPEX",
        "6933": "AI_SERVER_RACK_BUILD",
        "4770": "WAFER_FAB_EQUIPMENT_CAPEX",
        "4927": "CONSUMER_ELECTRONICS_CYCLE",
    }
    assert len(expected) == 38
    for code, driver in expected.items():
        assert m.loc[code, "primary_driver_id"] == driver
        assert m.loc[code, "classification_confidence"] in {"LOW", "MEDIUM", "HIGH"}


def test_new_driver_peer_baskets_are_explicit_and_not_generic_sector_proxies():
    p = load_peer_map()
    peers = p.groupby("driver_id")["ticker"].apply(set).to_dict()
    assert {"COHR", "LITE", "IPGP"} <= peers["OPTICAL_COMPONENT_DEMAND"]
    assert {"ENTG", "5384.T", "6146.T"} <= peers["SEMICONDUCTOR_FAB_UTILIZATION_CONSUMABLES"]
    assert {"MTSI", "VSAT", "IRDM"} <= peers["LEO_SATCOM_DEPLOYMENT"]
    assert {"3436.T", "4063.T"} <= peers["SILICON_WAFER_DEMAND_PRICING"]
    assert {"SREN.SW", "MUV2.DE", "HNR1.DE"} <= peers["REINSURANCE_PRICING_CATA_CYCLE"]
    assert {"7203.T", "7201.T"} <= peers["TAIWAN_AUTO_DEMAND"]
    assert {"MPWR", "POWI", "MCHP"} <= peers["ANALOG_PMIC_DEMAND"]
    assert {"QRVO", "SWKS", "MTSI"} <= peers["MOBILE_RF_FRONTEND_DEMAND"]


def test_company_specific_clinical_driver_keeps_sector_prices_as_risk_context_only():
    p = load_peer_map()
    x = p[p["driver_id"].eq("CLINICAL_REGULATORY_COMMERCIALIZATION")]
    assert {"XBI", "IBB"} <= set(x["ticker"].astype(str))
    assert set(x["peer_role"]) == {"RISK_CONTEXT"}

    m = load_industry_map().set_index("code")
    assert m.loc["6617", "classification_confidence"] == "LOW"
    assert "must not validate" in m.loc["6617", "notes"].lower()


def test_new_causal_taxonomy_rows_encode_hard_indicators_and_counter_evidence():
    taxonomy = pd.read_csv(Path("config/causal_driver_taxonomy.csv"))
    by_driver = taxonomy.set_index("driver_id")
    expected = {
        "OPTICAL_COMPONENT_DEMAND",
        "SEMICONDUCTOR_FAB_UTILIZATION_CONSUMABLES",
        "LEO_SATCOM_DEPLOYMENT",
        "CLINICAL_REGULATORY_COMMERCIALIZATION",
        "SILICON_WAFER_DEMAND_PRICING",
        "REINSURANCE_PRICING_CATA_CYCLE",
        "TAIWAN_AUTO_DEMAND",
        "ANALOG_PMIC_DEMAND",
        "MOBILE_RF_FRONTEND_DEMAND",
    }
    assert expected <= set(by_driver.index)
    for driver in expected:
        assert str(by_driver.loc[driver, "driver_scope"]).strip()
        assert str(by_driver.loc[driver, "activation_evidence_required"]).strip()
        assert str(by_driver.loc[driver, "counter_evidence_required"]).strip()
        assert int(by_driver.loc[driver, "enabled"]) == 1

    assert "must not validate" in by_driver.loc["CLINICAL_REGULATORY_COMMERCIALIZATION", "counter_evidence_required"].lower()
    assert "generic ai strength is not confirmation" in by_driver.loc["OPTICAL_COMPONENT_DEMAND", "counter_evidence_required"].lower()
