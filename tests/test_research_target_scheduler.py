import pandas as pd

from research_target_scheduler import select_research_targets, build_handoff


def _queue():
    return [
        {"driver_id": "SHIP1", "global_theme": "Shipping", "research_priority": 0.99},
        {"driver_id": "SHIP2", "global_theme": "Shipping", "research_priority": 0.98},
        {"driver_id": "SHIP3", "global_theme": "Shipping", "research_priority": 0.97},
        {"driver_id": "MEM1", "global_theme": "Memory", "research_priority": 0.90},
        {"driver_id": "AI1", "global_theme": "AI_Server", "research_priority": 0.85},
        {"driver_id": "FIN1", "global_theme": "Financials", "research_priority": 0.80},
        {"driver_id": "POWER1", "global_theme": "Power", "research_priority": 0.75},
        {"driver_id": "BIO1", "global_theme": "Biotech", "research_priority": 0.70},
    ]


def test_scheduler_prevents_one_theme_from_consuming_budget():
    out = select_research_targets(_queue(), max_targets=5, max_per_theme=2)
    themes = [x["global_theme"] for x in out]
    assert len(out) == 5
    assert themes.count("Shipping") <= 1
    assert len(set(themes)) == 5


def test_healthy_taiwan_theme_gets_research_attention_without_becoming_causal_evidence():
    structural = pd.DataFrame([
        {"global_theme": "Financials", "semantic_breadth_state": "HEALTHY", "reaction_state": "CONFIRMING"},
        {"global_theme": "Shipping", "semantic_breadth_state": "MIXED", "reaction_state": "PERSISTENT"},
    ])
    out = select_research_targets(_queue(), structural, max_targets=3, max_per_theme=1)
    assert out[0]["global_theme"] == "Financials"
    handoff = build_handoff({"run_id": "r1", "causal_rule": "PRICE_CANNOT_CREATE_CAUSALITY", "research_queue_top30": _queue()}, structural, 3, 1)
    assert handoff["scheduler"]["price_can_create_causality"] is False
    assert all("semantic_breadth_state" not in row for row in handoff["research_targets"])
