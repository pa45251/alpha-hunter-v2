from datetime import datetime, timezone
from copy import deepcopy

import pytest

from research_handoff import _apply_exposure_cache
from driver_gates import attach_price_gates
from opportunity_advisory import assess, rank_opportunities
from research_admission_v4 import audit_completeness, _classify
from test_ordered_driver_gates import sealed_fixture
from test_opportunity_advisory import ASOF, research, risk, history, local_proof


def remapped(monkeypatch, out):
    import research_handoff as handoff
    monkeypatch.setattr(handoff, '_driver_taxonomy', lambda: {'EXACT_DRIVER':dict(driver_id='EXACT_DRIVER', driver_label='Driver', global_theme='Test',driver_scope='GLOBAL')})
    monkeypatch.setattr(handoff, '_fresh_exposure_cache', lambda *args: {'9999.TW':[dict(resolved_driver_id='EXACT_DRIVER', source_urls=['https://issuer.example/facts'])]})
    rows=_apply_exposure_cache([dict(ticker='9999.TW',driver_id='UNMAPPED_OPPORTUNITY',reaction_state='PRE_CONFIRMATION')],out,datetime.now(timezone.utc))
    return attach_price_gates(rows,out)[0]


def test_late_resolved_weak_theme_reblocks(monkeypatch,tmp_path):
    out=sealed_fixture(tmp_path/'out',weak=True)
    candidate=remapped(monkeypatch,out)
    row=assess(candidate,research(),risk(),history(),ASOF)
    assert row['missing_gate']=='GLOBAL_PRICE_WEAK'
    assert row['action']=='PASS'


def test_late_resolved_developing_requires_economic_cause(monkeypatch,tmp_path):
    out=sealed_fixture(tmp_path/'out')
    candidate=remapped(monkeypatch,out)
    row=assess(candidate,research(international_evidence=[]),risk(),history(),ASOF)
    assert row['international_price_state']=='DEVELOPING'
    assert row['missing_gate']=='CAUSAL_UNVERIFIED'
    assert row['action'] not in {'BUY','EARLY BUY'}


def test_same_ticker_local_thesis_survives_global_veto(monkeypatch,tmp_path):
    out=sealed_fixture(tmp_path/'out',weak=True)
    candidate=remapped(monkeypatch,out)
    global_row=assess(candidate,research(),risk(),history(),ASOF)
    local=dict(candidate,driver_id='UNMAPPED_OPPORTUNITY',event_id='exclusive-contract')
    local_research=research(driver_id='UNMAPPED_OPPORTUNITY',scope='LOCAL',local_scope_reason='Independent award',local_scope_evidence=local_proof(),international_evidence=[])
    local_row=assess(local,local_research,risk(),history(),ASOF)
    rows=rank_opportunities([global_row,local_row])
    assert len(rows)==2
    assert global_row['action']=='PASS'
    assert local_row['action']=='EARLY BUY'


def test_admission_predicates_not_identity_or_rank_determine_state():
    rows=[dict(ticker=str(i),driver_id='D',missing_gate='CAUSAL_UNVERIFIED',reaction_state='PERSISTENT',entry_research_ready=True,price_data_status='VALID',research_priority=i) for i in range(205)]
    audit=audit_completeness(rows)
    assert audit['evaluated']==205 and audit['predicate_classes']==1
    assert {r['admission_state'] for r in audit['ledger']}=={'FACT_CHECK'}


def test_missing_price_is_not_failed_setup():
    row=dict(missing_gate='DRIVER_UNKNOWN',entry_research_ready=False,price_data_status='MISSING_OR_INSUFFICIENT')
    assert _classify(row)[2]=='PRICE_DATA_REPAIRED'
