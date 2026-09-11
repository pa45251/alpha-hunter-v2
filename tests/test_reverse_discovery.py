import pandas as pd

from causal_engine import CausalConfig, build_structural_matches
from reverse_discovery import (
    ReverseDiscoveryConfig,
    build_reverse_candidates,
    build_reverse_driver_queue,
    merge_research_queues,
)


def _global_stocks():
    return pd.DataFrame([
        {
            "ticker": "PANW", "theme": "Cybersecurity", "rs_20d_vs_bench": 0.12,
            "leader_score_v1": 0.90, "acceleration": 0.06, "last_price_date": "2026-09-10",
            "raw_leader_state": "PERSISTENT",
        },
        {
            "ticker": "CRWD", "theme": "Cybersecurity", "rs_20d_vs_bench": 0.08,
            "leader_score_v1": 0.82, "acceleration": 0.04, "last_price_date": "2026-09-10",
            "raw_leader_state": "EMERGING",
        },
        {
            "ticker": "SPY", "theme": "Market_US", "rs_20d_vs_bench": 0.00,
            "leader_score_v1": 0.20, "acceleration": -0.01, "last_price_date": "2026-09-10",
            "raw_leader_state": "NEUTRAL",
        },
    ])


def _taiwan_stocks():
    rows = []
    for i in range(10):
        rows.append({
            "code": f"{4000+i}", "ticker": f"{4000+i}.TW", "name": f"Other{i}",
            "industry": "其他", "taiwan_candidate_score_v1": 0.10 + i * 0.02,
            "taiwan_early_score_v2": 0.10 + i * 0.02, "rs_20d_vs_bench": -0.05 + i * 0.005,
            "rs_60d_vs_bench": -0.02, "acceleration": 0.00 + i * 0.002,
            "bias20": 0.01, "reaction_state": "UNKNOWN", "keynes_v2": 0.1,
            "last_price_date": "2026-09-11",
        })
    rows.append({
        "code": "3029", "ticker": "3029.TW", "name": "零壹", "industry": "資訊服務業",
        "taiwan_candidate_score_v1": 0.95, "taiwan_early_score_v2": 0.98,
        "rs_20d_vs_bench": 0.01, "rs_60d_vs_bench": -0.01, "acceleration": 0.10,
        "bias20": 0.02, "reaction_state": "PRE_CONFIRMATION", "keynes_v2": 0.6,
        "last_price_date": "2026-09-11",
    })
    return pd.DataFrame(rows)


def _taxonomy():
    return pd.DataFrame([{
        "driver_id": "ENTERPRISE_CYBER_SPEND",
        "driver_label": "Enterprise cybersecurity spending",
        "global_theme": "Cybersecurity",
        "driver_scope": "enterprise security budgets, subscriptions, channel demand",
        "activation_evidence_required": "current non-price evidence for enterprise security spending",
        "counter_evidence_required": "contradictory channel demand or security budget evidence",
        "enabled": 1,
    }])


def _exposure():
    return pd.DataFrame([{
        "driver_id": "ENTERPRISE_CYBER_SPEND",
        "driver_label": "Enterprise cybersecurity spending",
        "global_theme": "Cybersecurity",
        "taiwan_code": "3029",
        "taiwan_name_seed": "零壹",
        "economic_role": "security_distribution",
        "linkage_tier": "SECOND_ORDER",
        "linkage_confidence": 0.64,
        "polarity": "POSITIVE",
        "link_mechanism": "Enterprise security spending may transmit through channel demand",
        "evidence_required": "security product mix / vendor exposure / orders",
        "edge_status": "SEED",
        "provenance_status": "NEEDS_SOURCE_BACKFILL",
        "review_after": "2026-12-31",
        "enabled": 1,
    }])


def test_taiwan_price_can_nominate_but_not_activate_driver():
    candidates = build_reverse_candidates(
        _taiwan_stocks(), _global_stocks(), _exposure(), _taxonomy(),
        ReverseDiscoveryConfig(anomaly_percentile_gate=0.85),
    )
    assert list(candidates["ticker"]) == ["3029.TW"]
    row = candidates.iloc[0]
    assert row["driver_id"] == "ENTERPRISE_CYBER_SPEND"
    assert row["activation_state"] == "UNRESOLVED_RESEARCH_REQUIRED"
    assert bool(row["price_cannot_activate_driver"])
    assert bool(row["local_catalyst_check_required"])
    assert not bool(row["decision_eligible"])
    assert "PANW" in row["global_peer_evidence"]


def test_reverse_driver_queue_requires_local_catalyst_counter_check():
    candidates = build_reverse_candidates(
        _taiwan_stocks(), _global_stocks(), _exposure(), _taxonomy(),
        ReverseDiscoveryConfig(anomaly_percentile_gate=0.85),
    )
    queue = build_reverse_driver_queue(candidates, _taxonomy())
    assert len(queue) == 1
    row = queue.iloc[0]
    assert row["nomination_origin"] == "TAIWAN_REVERSE"
    assert row["activation_state"] == "UNRESOLVED_RESEARCH_REQUIRED"
    assert "3029.TW|零壹" in row["reverse_nominees"]
    assert "local catalysts" in row["counter_evidence_required"]
    assert "must not be used to activate the global driver" in row["counter_evidence_required"]


def test_merge_preserves_global_and_reverse_origins_without_activation():
    global_queue = pd.DataFrame([{
        "research_priority": 0.90,
        "global_theme": "Cybersecurity",
        "driver_id": "ENTERPRISE_CYBER_SPEND",
        "driver_label": "Enterprise cybersecurity spending",
        "driver_scope": "enterprise security budgets",
        "global_theme_strength_v2": 0.90,
        "global_latest_price_date": "2026-09-10",
        "global_leaders_evidence": "PANW:PERSISTENT",
        "activation_state": "UNRESOLVED_RESEARCH_REQUIRED",
        "activation_confidence": None,
        "activation_evidence_required": "exact driver evidence",
        "counter_evidence_required": "global counter evidence",
        "price_cannot_activate_driver": True,
    }])
    candidates = build_reverse_candidates(
        _taiwan_stocks(), _global_stocks(), _exposure(), _taxonomy(),
        ReverseDiscoveryConfig(anomaly_percentile_gate=0.85),
    )
    reverse_queue = build_reverse_driver_queue(candidates, _taxonomy())
    merged = merge_research_queues(global_queue, reverse_queue)
    row = merged.iloc[0]
    assert set(row["nomination_origin"].split("+")) == {"GLOBAL_THEME", "TAIWAN_REVERSE"}
    assert row["activation_state"] == "UNRESOLVED_RESEARCH_REQUIRED"
    assert bool(row["local_catalyst_check_required"])
    assert "3029.TW|零壹" in row["counter_evidence_required"]


def test_reverse_nomination_can_surface_existing_edge_below_global_theme_gate():
    global_other = pd.DataFrame([{
        "ticker": "SPY", "theme": "Market_US", "rs_20d_vs_bench": 0.0,
        "leader_score_v1": 0.5, "acceleration": 0.0, "last_price_date": "2026-09-10",
        "raw_leader_state": "NEUTRAL",
    }])
    tw = _taiwan_stocks()
    empty_candidates = pd.DataFrame(columns=["code"])
    empty_breadth = pd.DataFrame()

    no_reverse = build_structural_matches(
        global_other, tw, empty_candidates, empty_breadth, _exposure(), _taxonomy(), CausalConfig()
    )
    assert no_reverse.empty

    with_reverse = build_structural_matches(
        global_other, tw, empty_candidates, empty_breadth, _exposure(), _taxonomy(), CausalConfig(),
        nominated_driver_ids={"ENTERPRISE_CYBER_SPEND"},
    )
    assert len(with_reverse) == 1
    row = with_reverse.iloc[0]
    assert bool(row["reverse_nominated_driver"])
    assert row["dynamic_driver_state"] == "UNRESOLVED"
    assert not bool(row["decision_eligible"])
