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
