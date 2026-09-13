import copy
import pytest
from entry_risk import entry_risk, risk_narrative, validate_plan
from opportunity_advisory import assess, price_plan
from test_opportunity_advisory import history, research, risk, ASOF


def test_A_five_percent_passes_risk_gate():
    m=entry_risk(100,100,95,110)
    assert m['risk_pct']==pytest.approx(.05)
    assert m['risk_gate'] and m['entry_risk_eligible']
    assert m['reward_risk']==2


def test_B_large_reward_cannot_rescue_fifteen_percent_risk():
    m=entry_risk(100,100,85,200)
    assert m['risk_pct']==pytest.approx(.15)
    assert not m['risk_gate'] and not m['entry_risk_eligible']
    text=risk_narrative(m,'Observed resistance')
    assert '15.00%' in text and 'exceeds 8%' in text
    assert 'support defines <=8%' not in text


def test_C_whole_zone_uses_highest_entry_and_same_rr_denominator():
    m=entry_risk(100,105,96,125)
    assert m['risk_amount']==9
    assert m['risk_pct']==pytest.approx(9/105)
    assert m['reward_risk']==pytest.approx(20/9)
    assert not m['risk_gate']


def wide_risk_history():
    h=history()
    # Technical support really is lower; never pull stop closer to manufacture eligibility.
    h.iloc[-8,h.columns.get_loc('Low')]=85
    return h


def candidate():
    return dict(ticker='9999.TW',driver_id='EXACT_DRIVER',international_price_state='CONFIRMED',reaction_state='PRE_CONFIRMATION')


def test_D_good_thesis_with_bad_actual_risk_waits_for_entry():
    h=wide_risk_history();p=price_plan(h)
    assert p['risk_pct']>.08 and p['stop']<85
    row=assess(candidate(),research(driver_state='CONFIRMED'),risk(),h,ASOF)
    assert row['action']=='WAIT' and row['wait_reason']=='WAIT_FOR_ENTRY'
    assert row['entry_state']=='WAIT_FOR_ENTRY' and not row['price_ok']
    validate_plan(row)


def test_E_good_entry_cannot_rescue_weak_global_price():
    c=candidate();c['international_price_state']='REJECTED'
    row=assess(c,research(),risk(),history(),ASOF)
    assert row['risk_gate'] and row['action']=='PASS'
    assert row['missing_gate']=='GLOBAL_PRICE_WEAK'
    assert row['global_price_risk_veto'] is True
    assert row['economic_driver_rejected'] is False


@pytest.mark.parametrize('hist',[history,wide_risk_history])
def test_F_numbers_narrative_permission_and_display_agree(hist):
    p=price_plan(hist());validate_plan(p)
    assert p['risk_pct']==pytest.approx((p['entry_high']-p['stop'])/p['entry_high'])
    assert p['reward_risk']==pytest.approx((p['reference_target']-p['entry_high'])/(p['entry_high']-p['stop']))
    assert f"{p['risk_pct']:.2%}" in p['price_reason']
    assert p['reference_is_target'] is False
    for key,value in [('risk_pct',.01),('entry','100–105'),('invalidation','Exit on loss of 99'),('price_reason','support defines <=8% price risk')]:
        broken=copy.deepcopy(p);broken[key]=value
        with pytest.raises(ValueError):validate_plan(broken)


@pytest.mark.parametrize('values',[(1305,1330,1110,1680),(35.3,35.75,27.35,39.5)])
def test_reported_live_examples_are_not_risk_eligible(values):
    m=entry_risk(*values)
    assert m['risk_pct']>.15 and not m['risk_gate']
    assert 'WAIT_FOR_ENTRY' in risk_narrative(m,'Observed resistance')


@pytest.mark.parametrize('values',[(100,99,95,110),(100,100,100,110),(100,100,-1,110),(100,float('nan'),95,110),(100,100,95,None)])
def test_invalid_or_missing_numbers_fail_closed(values):
    assert not entry_risk(*values)['entry_risk_eligible']


def test_rounded_entry_not_raw_close_is_risk_denominator():
    # Raw close 1014.9 rounds down to executable entry 1010. The old
    # denominator would pass this setup even though actual downside exceeds 8%.
    assert (1010-929)/1014.9 < .08
    m=entry_risk(1005,1010,929,1300)
    assert m['risk_pct']>.08 and not m['risk_gate']
