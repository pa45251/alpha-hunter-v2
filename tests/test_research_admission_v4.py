from __future__ import annotations

import research_admission_v4 as admission


def _row(ticker, driver, gate, *, entry_ready=True, reaction="PERSISTENT"):
    return {
        "ticker": ticker,
        "name": ticker,
        "driver_id": driver,
        "driver_label": driver,
        "missing_gate": gate,
        "entry_research_ready": entry_ready,
        "reaction_state": reaction,
        "international_price_state": "DEVELOPING",
    }


def test_price_not_ready_unknown_is_deferred_not_deep(monkeypatch):
    rows = [_row("1111.TW", "UNMAPPED_OPPORTUNITY", "DRIVER_UNKNOWN", entry_ready=False)]
    monkeypatch.setattr("research_handoff.company_research_targets", lambda *a, **k: rows)
    source = {"research_targets": [], "company_research_targets": []}
    out = admission.apply_admission(source)
    assert out["company_research_targets"] == []
    assert out["deferred_candidates"][0]["admission_state"] == "OBSERVE"
    assert out["deferred_candidates"][0]["wake_condition"] == "ENTRY_SETUP_OR_NEW_NONPRICE_EVENT"


def test_same_driver_shared_once_company_theses_each_kept(monkeypatch):
    rows = [
        _row("1111.TW", "DRIVER_A", "CAUSAL_UNVERIFIED"),
        _row("2222.TW", "DRIVER_A", "CAUSAL_UNVERIFIED"),
    ]
    monkeypatch.setattr("research_handoff.company_research_targets", lambda *a, **k: rows)
    source = {
        "research_targets": [
            {"driver_id": "DRIVER_A", "driver_label": "A"},
            {"driver_id": "DRIVER_A", "driver_label": "A duplicate"},
        ],
        "company_research_targets": [],
    }
    out = admission.apply_admission(source)
    assert len(out["company_research_targets"]) == 2
    assert len(out["research_targets"]) == 1
    assert out["research_targets"][0]["driver_id"] == "DRIVER_A"
    assert len({x["thesis_id"] for x in out["company_research_targets"]}) == 2


def test_market_price_gap_observes_without_llm(monkeypatch):
    rows = [_row("1111.TW", "DRIVER_A", "GLOBAL_PRICE_UNCONFIRMED")]
    monkeypatch.setattr("research_handoff.company_research_targets", lambda *a, **k: rows)
    out = admission.apply_admission({"research_targets": [], "company_research_targets": []})
    assert out["company_research_targets"] == []
    assert out["deferred_candidates"][0]["admission_state"] == "OBSERVE"
    assert out["deferred_candidates"][0]["wake_condition"] == "GLOBAL_PRICE_STATE_CHANGE"


def test_broken_candidate_drops_this_run(monkeypatch):
    rows = [_row("1111.TW", "DRIVER_A", "CAUSAL_UNVERIFIED", reaction="BROKEN")]
    monkeypatch.setattr("research_handoff.company_research_targets", lambda *a, **k: rows)
    out = admission.apply_admission({"research_targets": [], "company_research_targets": []})
    assert out["company_research_targets"] == []
    assert out["deferred_candidates"][0]["admission_state"] == "DROP_THIS_RUN"


def test_unknown_with_ready_setup_enters_bounded_fact_check(monkeypatch):
    rows = [_row("1111.TW", "UNMAPPED_OPPORTUNITY", "DRIVER_UNKNOWN")]
    monkeypatch.setattr("research_handoff.company_research_targets", lambda *a, **k: rows)
    out = admission.apply_admission({"research_targets": [], "company_research_targets": []})
    assert len(out["company_research_targets"]) == 1
    target = out["company_research_targets"][0]
    assert target["admission_state"] == "FACT_CHECK"
    assert "independent of its stock price" in target["research_question"]
