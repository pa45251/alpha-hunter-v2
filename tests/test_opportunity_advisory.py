import copy
import numpy as np
import pandas as pd
import pytest
from opportunity_advisory import assess, price_plan, validate_company_research, rank_opportunities, evidence_valid
from taiwan_sensor import select_taiwan_candidates, TaiwanScanConfig

ASOF='2026-09-12T08:00:00Z'

def history():
    close=np.r_[np.linspace(125,101,50),np.repeat(100.,49),101.]
    return pd.DataFrame({'Open':close-.2,'High':close+.5,'Low':close-.5,'Close':close,'Volume':np.repeat(1_000_000.,100)},index=pd.bdate_range(end='2026-09-11',periods=100))

def evidence(**changes):
    e=dict(ticker='9999.TW',driver_id='EXACT_DRIVER',metric='BACKLOG',direction='SUPPORTS',claim='Signed backlog increased 20%',source_title='Company disclosure',source_url='https://example.com/filing',published_at='2026-09-10T00:00:00Z',available_at='2026-09-10T00:00:00Z',same_driver=True)
    e.update(changes);return e

def research(**changes):
    r=dict(ticker='9999.TW',driver_id='EXACT_DRIVER',research_run_id='run',driver_state='DEVELOPING',scope='GLOBAL',why='Backlog enters recognized project revenue',driver='Project recognition',company_transmission='Signed company contracts generate revenue',rate_sensitive=False,fundamental_evidence=[evidence()],international_evidence=[evidence()],counter_evidence_reviewed=True,major_counter_evidence=False,main_risk='Project delays',what_would_make_us_wrong='Contract cancellation')
    r.update(changes);return r

def risk(**changes):
    r=dict(status='READY',regime='NORMAL',signals={'rate_pressure':'ADVERSE','vix':{'price':19},'credit_hyg_lqd':{'above_ma60':True,'ret20':.01}});r.update(changes);return r

def evaluate(r=None,h=None,**candidate):
    return assess(dict(ticker='9999.TW',name='unseen company',reaction_state='PRE_CONFIRMATION',**candidate),r or research(),risk(),h if h is not None else history(),ASOF)

def test_developing_evidence_and_price_allow_early_buy_without_v2_confirmation():
    row=evaluate();assert row['action']=='EARLY BUY';assert row['planned_position_fraction']==.35
    assert row['auto_trade_allowed'] is False
    assert price_plan(history())['reward_risk']>=2

def test_confirmed_breakout_promotes_buy():
    assert evaluate(research(driver_state='CONFIRMED'),history().assign(Volume=lambda h: h.Volume.where(h.index!=h.index[-1],2_000_000)))['action']=='BUY'

def test_local_driver_works_in_weak_broad_market():
    r=research(scope='LOCAL',local_scope_reason='Specific signed EPC project recognition independent of global peer cycle',international_evidence=[])
    x=assess({'ticker':'9999.TW'},r,risk(regime='DEFENSIVE'),history(),ASOF)
    assert x['action']=='EARLY BUY';assert x['regime']=='NEUTRAL';assert x['relative']=='LOCAL DRIVER'

@pytest.mark.parametrize('change',[
    {'international_evidence':[evidence(driver_id='OTHER_DRIVER')]},
    {'international_evidence':[evidence(same_driver=False)]},
    {'fundamental_evidence':[evidence(metric='PRICE')]},
    {'fundamental_evidence':[evidence(ticker='OTHER.TW')]},
    {'fundamental_evidence':[evidence(published_at='2026-09-13T00:00:00Z')]},
    {'fundamental_evidence':[evidence(published_at='2025-01-01T00:00:00Z')]},
    {'counter_evidence_reviewed':False},
])
def test_missing_or_wrong_evidence_never_buys(change):
    assert evaluate(research(**change))['action']=='WAIT'

@pytest.mark.parametrize('change',[{'major_counter_evidence':True},{'driver_state':'REJECTED'},{'rate_sensitive':True}])
def test_adverse_conditions_pass(change):
    assert evaluate(research(**change))['action']=='PASS'

def test_unknown_rate_pressure_is_not_neutral_for_growth():
    x=assess({'ticker':'9999.TW'},research(rate_sensitive=True),risk(signals={}),history(),ASOF)
    assert x['regime']=='UNKNOWN' and x['action']=='WAIT'

def test_extreme_extension_not_bought_even_with_confirmed_thesis():
    h=history();h.loc[h.index[-1],['Open','High','Low','Close']]=[150,152,148,151]
    assert evaluate(research(driver_state='CONFIRMED'),h)['action']=='PASS'

def test_bad_reward_risk_waits():
    h=history();h.iloc[:50,:4]=100
    assert evaluate(h=h)['action']=='WAIT'

def test_unmapped_research_can_be_provisional_local_without_taxonomy():
    r=research(driver_id='UNMAPPED_OPPORTUNITY',scope='LOCAL',local_scope_reason='Company-specific EPC backlog',international_evidence=[])
    validate_company_research(r,'run',{('9999.TW','UNMAPPED_OPPORTUNITY')},ASOF)
    assert evaluate(r)['action']=='EARLY BUY'

def test_mixed_snapshot_research_rejected():
    with pytest.raises(ValueError):validate_company_research(research(),'other',{('9999.TW','EXACT_DRIVER')},ASOF)

def test_rank_before_truncation_and_dedup():
    rows=[dict(ticker=str(i),action='WAIT',research_priority=100,evidence=[]) for i in range(30)]
    rows += [dict(ticker='GOOD',action='EARLY BUY',research_priority=0,evidence=[evidence()])]
    result=rank_opportunities(rows)
    assert result[0]['ticker']=='GOOD';assert len(result)==2

def test_extended_fillers_cannot_defeat_scanner_quota():
    x=pd.DataFrame([dict(ticker=str(i),avg_turnover20_twd=20e6,price=50,acceleration=.1,rs_20d_vs_bench=.1,keynes_v2=1,reaction_state='EXTENDED' if i else 'PRE_CONFIRMATION',taiwan_candidate_score_v1=1,taiwan_early_score_v2=1) for i in range(100)])
    result=select_taiwan_candidates(x,TaiwanScanConfig(top_candidates=10))
    assert (result.reaction_state=='EXTENDED').sum()<=1
    assert '0' in set(result.ticker)
