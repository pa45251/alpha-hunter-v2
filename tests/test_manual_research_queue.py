from pathlib import Path

import pandas as pd

from manual_research_queue import build_driver_breadth, build_manual_queue


def test_priority_industry_ontology_has_expected_subindustries():
    m = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str})
    by_code = m.set_index("code")
    assert by_code.loc["3008", "economic_subindustry"] == "Mobile_Optics"
    assert by_code.loc["2481", "economic_subindustry"] == "Diode_Discrete"
    assert by_code.loc["2383", "economic_subindustry"] == "CCL_HighSpeed"
    assert by_code.loc["3533", "economic_subindustry"] == "Server_Connector"
    assert by_code.loc["2472", "economic_subindustry"] == "Capacitor"


def test_every_manual_driver_has_configured_international_peers():
    m = pd.read_csv(Path("config/manual_industry_map.csv"), dtype={"code": str})
    p = pd.read_csv(Path("config/manual_global_peers.csv"))
    mapped = set(m["primary_driver_id"].dropna().astype(str))
    peer_drivers = set(p["driver_id"].dropna().astype(str))
    assert mapped <= peer_drivers
    assert p.groupby("driver_id")["ticker"].nunique().min() >= 2


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
