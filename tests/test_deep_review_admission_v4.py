from __future__ import annotations

from deep_review_admission_v4 import _admit


def _row():
    return {
        "decision_state": "EARLY BUY",
        "entry_risk_eligible": True,
        "missing_gate": "ENTRY",
        "company_transmission": "Orders and shipments are rising through the stated mechanism.",
        "driver_scope": "GLOBAL",
        "what_would_make_us_wrong": "Orders reverse while driver remains active.",
        "exposure_evidence": [{
            "claim": "Product exposure",
            "source_url": "https://example.com/company",
            "source_title": "Company filing",
        }],
        "evidence": [{
            "claim": "Current shipment growth",
            "source_url": "https://example.com/current",
            "source_title": "Company update",
        }],
        "international_evidence": [{
            "claim": "Driver demand improved",
            "source_url": "https://example.com/driver",
            "source_title": "Industry data",
        }],
    }


def test_price_only_candidate_cannot_enter_deep_review():
    row = _row()
    row["company_transmission"] = ""
    ok, reason = _admit(row)
    assert not ok
    assert reason == "COMPANY_TRANSMISSION_MISSING"


def test_global_thesis_needs_current_driver_evidence():
    row = _row()
    row["international_evidence"] = []
    ok, reason = _admit(row)
    assert not ok
    assert reason == "CURRENT_DRIVER_EVIDENCE_MISSING"


def test_entry_risk_is_hard_admission_gate():
    row = _row()
    row["entry_risk_eligible"] = False
    ok, reason = _admit(row)
    assert not ok
    assert reason == "ENTRY_RISK_NOT_ELIGIBLE"


def test_complete_early_buy_can_enter_deep_review_without_breakout_requirement():
    row = _row()
    row["technical"] = "Early strength / support recovery"
    ok, reason = _admit(row)
    assert ok
    assert reason == "ADMITTED"
