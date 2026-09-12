"""Adversarial cross-layer checks: price nomination never supplies causality."""
import hashlib
import json

import pandas as pd
import pytest

from driver_gates import international_price, thesis_gates
from opportunity_advisory import assess, validate_company_research
from research_handoff import company_research_targets, decision_research_handoff
from test_opportunity_advisory import ASOF, evidence, history, local_proof, research, risk


def candidate(**kw):
    return dict(ticker='9999.TW', driver_id='EXACT_DRIVER', global_theme='Test',
                reaction_state='PRE_CONFIRMATION', international_price_state='DEVELOPING', **kw)


@pytest.mark.parametrize('state', ['WEAK', 'WEAKENING', 'REJECTED'])
def test_A_global_veto_beats_beautiful_company_even_without_ingest(state):
    c = candidate(); c['international_price_state'] = state
    r = research(driver_state='CONFIRMED', fundamental_evidence=[evidence(), evidence(metric='EPS')])
    row = assess(c, r, risk(), history(), ASOF)
    assert row['action'] == 'PASS'
    assert row['missing_gate'] == 'GLOBAL_REJECTED'
    assert row['research_task'] == 'NONE'
    assert row['planned_position_fraction'] == 0


def test_B_unknown_is_not_local_from_backlog_or_scope_reason():
    c = candidate(); c['driver_id'] = 'UNMAPPED_OPPORTUNITY'
    r = research(driver_id=c['driver_id'], scope='LOCAL', local_scope_reason='Excellent orders')
    assert assess(c, r, risk(), history(), ASOF)['missing_gate'] == 'DRIVER_UNKNOWN'
    with pytest.raises(ValueError, match='INDEPENDENCE'):
        validate_company_research(r, 'run', {(c['ticker'], c['driver_id'])}, ASOF)


def test_C_proven_independent_event_can_use_local_path():
    c = candidate(); c['driver_id'] = 'UNMAPPED_OPPORTUNITY'
    r = research(driver_id=c['driver_id'], scope='LOCAL', local_scope_reason='Exclusive Taiwan award',
                 local_scope_evidence=local_proof(), international_evidence=[])
    validate_company_research(r, 'run', {(c['ticker'], c['driver_id'])}, ASOF)
    row = assess(c, r, risk(), history(), ASOF)
    assert row['action'] == 'EARLY BUY'
    assert row['driver_scope'] == 'LOCAL'
    assert row['international_price_state'] == 'NOT_REQUIRED'
    c['known_global_link'] = True
    assert assess(c, r, risk(), history(), ASOF)['action'] == 'WAIT'


@pytest.mark.parametrize('key', ['event_evidence', 'global_alternative_evidence'])
def test_local_proof_must_be_timely_and_ticker_specific(key):
    c = candidate(); c['driver_id'] = 'UNMAPPED_OPPORTUNITY'
    proof = local_proof(); proof[key]['ticker'] = 'OTHER.TW'
    r = research(driver_id=c['driver_id'], scope='LOCAL', local_scope_evidence=proof)
    assert assess(c, r, risk(), history(), ASOF)['driver_scope'] == 'UNKNOWN'


def test_D_developing_price_and_cause_are_separate_and_allow_early_buy():
    row = assess(candidate(), research(), risk(), history(), ASOF)
    assert row['international_price_state'] == 'DEVELOPING'
    assert row['international_causal_state'] == 'DEVELOPING'
    assert row['action'] == 'EARLY BUY'
    assert assess(candidate(), research(international_evidence=[]), risk(), history(), ASOF)['missing_gate'] == 'CAUSAL_UNVERIFIED'
    c = candidate(); c.pop('international_price_state')
    assert assess(c, research(), risk(), history(), ASOF)['missing_gate'] == 'GLOBAL_PRICE_UNCONFIRMED'


def test_E_valid_thesis_with_extended_entry_needs_no_fundamental_research():
    c = candidate(); c['reaction_state'] = 'EXTENDED'
    row = assess(c, research(), risk(), history(), ASOF)
    assert row['action'] == 'WAIT'
    assert row['wait_reason'] == 'ENTRY'
    assert row['research_task'] == 'NONE'


def sealed_fixture(out, weak=False, count=1, extended=False):
    out.mkdir()
    rows = [dict(ticker=f'{9999-i}.TW', driver_id='EXACT_DRIVER', global_theme='Test', name='Test',
                 reaction_state='EXTENDED' if extended else 'PRE_CONFIRMATION', run_id='run', reverse_research_priority=i)
            for i in range(count)]
    pd.DataFrame(rows).to_csv(out/'reverse_transmission_candidates.csv', index=False)
    pd.DataFrame([dict(theme='Test', breadth_confidence='HIGH', above_ma20_pct=.1 if weak else .8,
                      above_ma60_pct=.1 if weak else .8, positive_rs20_pct=.1 if weak else .8,
                      positive_rs5_pct=.1 if weak else .8, near_20d_high_pct=.1 if weak else .8,
                      near_52w_high_pct=.1 if weak else .8, median_rs20=-.1 if weak else .1)]).to_csv(out/'theme_breadth.csv', index=False)
    pd.DataFrame([dict(theme='Test', universe_layer='CORE', raw_leader_state='WEAKENING' if weak else 'EMERGING',
                      rs_5d_vs_bench=.1, rs_20d_vs_bench=.1, rs_60d_vs_bench=-.1, acceleration=.1)]).to_csv(out/'market_snapshot.csv', index=False)
    pd.DataFrame([dict(taiwan_code='9999', driver_id='EXACT_DRIVER')]).to_csv(out/'structural_exposure_graph.csv', index=False)
    from canonical_evidence import encode_histories
    (out/'market_snapshot.json').write_text(json.dumps(dict(run_id='run', entry_histories=encode_histories({r['ticker']:history() for r in rows}))))
    files=[dict(name=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir()]
    (out/'manifest.json').write_text(json.dumps(dict(run_id='run',status='PASS',authoritative_files=files)))
    (out/'research_packet.json').write_text(json.dumps(dict(run_id='run',research_queue_top30=[dict(driver_id='EXACT_DRIVER',global_theme='Test')])))
    return out


def test_F_rejected_global_is_not_sent_to_company_or_driver_research(tmp_path):
    out = sealed_fixture(tmp_path/'output', weak=True)
    all_rows = company_research_targets(out, limit=None)
    assert all_rows[0]['missing_gate'] == 'GLOBAL_REJECTED'
    plan = decision_research_handoff(out)
    assert not plan['company_research_targets'] and not plan['research_targets']
    assert plan['deferred_candidates'][0]['research_task'] == 'NONE'


def test_coverage_is_decision_gap_based_not_top_five(tmp_path):
    out = sealed_fixture(tmp_path/'output', count=8)
    plan = decision_research_handoff(out)
    assert len(plan['company_research_targets']) == 8
    assert len(plan['research_targets']) == 1  # One shared driver task, not eight copies.


def test_entry_blocked_candidates_do_not_consume_research(tmp_path):
    out = sealed_fixture(tmp_path/'output', count=8, extended=True)
    plan = decision_research_handoff(out)
    assert not plan['company_research_targets'] and not plan['research_targets']


def test_tampered_price_evidence_cannot_authorize_entry(tmp_path):
    out = sealed_fixture(tmp_path/'output')
    with (out/'theme_breadth.csv').open('a') as f: f.write('\n')
    c = company_research_targets(out, limit=None)[0]
    assert c['international_price_state'] == 'UNKNOWN'
    assert not c['research_eligible']
    assert assess(c, research(), risk(), history(), ASOF)['action'] == 'WAIT'


def test_unknown_data_is_not_rejected_price():
    b = pd.DataFrame([dict(theme='Test', breadth_confidence='LOW')])
    p = pd.DataFrame([dict(theme='Test')])
    assert international_price('Test', b, p)['international_price_state'] == 'UNKNOWN'


def test_company_cannot_forge_price_gate():
    c = candidate(); c['international_price_state'] = 'REJECTED'
    r = research(international_price_state='CONFIRMED', scope='LOCAL', local_scope_reason='Good company')
    assert assess(c, r, risk(), history(), ASOF)['action'] == 'PASS'


def test_v2_causal_active_cannot_override_attached_price_veto():
    from decision_engine import build_decision_board
    row=dict(driver_id='EXACT_DRIVER',dynamic_driver_state='ACTIVE_RESEARCH_VALIDATED',
             provenance_status='SOURCE_BACKED',polarity='POSITIVE',reaction_state='CONFIRMING',
             previous_reaction_state='PRE_CONFIRMATION',stock_vs_etf_state='STOCK_ALPHA_ELIGIBLE',
             international_price_state='REJECTED')
    board=build_decision_board(pd.DataFrame([row]))
    assert board.iloc[0].decision_stage == 'GATE_0_INTERNATIONAL_PRICE'
    assert 'ENTRY_TRIGGERED' not in board.iloc[0].candidate_action
