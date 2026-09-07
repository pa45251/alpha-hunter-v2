import json
from pathlib import Path
import pandas as pd
import pytest
import publication_guard as pg
from test_portfolio_allocation_v2 import _policy, _positions, _candidates, _regime, _entries, _plan
from portfolio_allocation_v2 import build_portfolio_allocation_v2

NOW='2026-09-07T00:30:00Z'

def dump(out,name,obj):
    (out/name).write_text(json.dumps(obj))

def fixture(out):
    dump(out,'manifest.json',{'run_id':'R','generated_at_taipei':'2026-09-07T08:00:00+08:00','taiwan':{'latest_price_date':'2026-09-04'}})
    dump(out,'gate_report.json',{})
    dump(out,'decision_packet.json',{'run_id':'R','snapshot_lineage_layer':{'manifest_sha256':pg.digest(out/'manifest.json')}})
    for n in ('position_alias_actions.json','position_cio_advisory.json'):
        dump(out,n,{'run_id':'R'})
    pd.DataFrame([{'run_id':'R','ticker':'2317.TW','driver_id':'AI_SERVER_SHIPMENTS'}]).to_csv(out/'decision_board.csv',index=False)
    pd.DataFrame([{'ticker':'SPY','last_price_date':'2026-09-04'}]).to_csv(out/'market_snapshot.csv',index=False)
    pd.DataFrame([{'ticker':'2317.TW','last_price_date':'2026-09-04'}]).to_csv(out/'taiwan_candidates.csv',index=False)
    pd.read_csv(out/'decision_board.csv').to_csv(out/'global_alignment_v2.csv',index=False)
    plan=_plan(driver_id='AI_SERVER_SHIPMENTS',entry_executable=False,auto_trade_allowed=False,score_is_probability=False)
    dump(out,'entry_plans_v2.json',dict(_entries(plan),source_run_id='R',generated_at=NOW))
    rotation=build_portfolio_allocation_v2(_policy(),_positions(),_candidates(),_regime(),_entries(plan))
    rotation['generated_at']=NOW
    dump(out,'portfolio_allocation_v2.json',rotation)
    dump(out,'risk_regime.json',dict(_regime(),generated_at=NOW,risk_snapshot_date='2026-09-04'))
    for n in ('cio_advisory.json','global_alignment_v2.json'):
        dump(out,n,{'generated_at':NOW})
    pd.DataFrame([plan]).to_csv(out/'entry_plans_v2.csv',index=False)
    pd.DataFrame([{'decision_session':'2026-09-04','ticker':'2317.TW','driver_id':'AI_SERVER_SHIPMENTS','entry_style':'FRESH_BREAKOUT'}]).to_csv(out/'entry_plan_trace_v2.csv',index=False)
    (out/'action_board.md').write_text('fixture board')
    return plan

def seal_fixture(out):
    fixture(out)
    context=out/'context.json'
    dump(out,'context.json',{'run_id':'R','started_at':'2026-09-07T00:10:00Z','inputs':{n:pg.digest(out/n) for n in pg.INPUTS},'old_trace':None})
    pg.seal(out,context,NOW)
    return context

def test_ready_current_and_same_session_repeat(tmp_path):
    seal_fixture(tmp_path)
    assert pg.readiness(tmp_path,NOW)['status']=='READY_CURRENT_SNAPSHOT'
    assert pg.readiness(tmp_path,NOW)==pg.readiness(tmp_path,NOW)

@pytest.mark.parametrize('kind',['yesterday','mixed','missing','future','modified_board'])
def test_readiness_fail_closed(tmp_path,kind):
    seal_fixture(tmp_path)
    now=NOW
    if kind=='yesterday': now='2026-09-08T00:30:00Z'
    elif kind=='future': now='2026-09-06T00:30:00Z'
    elif kind=='missing': (tmp_path/'entry_plans_v2.json').unlink()
    elif kind=='mixed': dump(tmp_path,'manifest.json',{'run_id':'OTHER'})
    else: (tmp_path/'action_board.md').write_text('wrong old board')
    assert pg.readiness(tmp_path,now)['status']=='NOT_READY'

def test_frozen_rotation_driver_bypass_is_blocked_by_publication(tmp_path):
    fixture(tmp_path)
    wrong=_plan(driver_id='OTHER',entry_executable=False,auto_trade_allowed=False,score_is_probability=False)
    # Reproduction against unchanged frozen implementation: ticker-only join borrows wrong driver.
    bad=build_portfolio_allocation_v2(_policy(),_positions(),_candidates(),_regime(),_entries(wrong))
    assert len(bad['rotations'])==1
    bad['rotations'][0]['destination_driver']='OTHER'
    dump(tmp_path,'portfolio_allocation_v2.json',bad)
    with pytest.raises(ValueError,match='ROTATION_DRIVER_MISMATCH'):
        pg.check_plan_links(tmp_path)

def test_trace_duplicate_session_different_action_rejected(tmp_path):
    fixture(tmp_path)
    t=pd.read_csv(tmp_path/'entry_plan_trace_v2.csv')
    pd.concat([t,t]).to_csv(tmp_path/'entry_plan_trace_v2.csv',index=False)
    with pytest.raises(ValueError,match='DUPLICATE_SESSION_TRACE'):
        pg.check_plan_links(tmp_path)

def test_changed_input_during_build_rejected(tmp_path):
    context=seal_fixture(tmp_path)
    dump(tmp_path,'decision_packet.json',{})
    with pytest.raises(ValueError,match='INPUT_CHANGED'):
        pg.seal(tmp_path,context,NOW)

@pytest.mark.parametrize('value',[float('nan'),float('inf'),None])
def test_invalid_price_levels_rejected(tmp_path,value):
    fixture(tmp_path)
    p=pg.read(tmp_path,'entry_plans_v2.json');p['all_plans'][0]['trigger_price']=value
    dump(tmp_path,'entry_plans_v2.json',p)
    with pytest.raises(ValueError,match='INVALID_ENTRY_LEVEL'):
        pg.check_plan_links(tmp_path)

def test_missing_seal_never_ready(tmp_path):
    fixture(tmp_path)
    assert pg.readiness(tmp_path,NOW)['status']=='NOT_READY'

def test_frozen_trace_repeats_session_when_status_changes(tmp_path,monkeypatch):
    import entry_plan_trace_v2 as tr
    from test_entry_plan_trace_v2 import _patch_paths, _manifest, _plan_row
    _patch_paths(monkeypatch,tmp_path)
    _manifest(tr.MANIFEST)
    pd.DataFrame([_plan_row()]).to_csv(tr.PLANS,index=False)
    tr.append_entry_plan_trace()
    pd.DataFrame([_plan_row(current_action='AVOID',entry_status='INVALID')]).to_csv(tr.PLANS,index=False)
    result=tr.append_entry_plan_trace()
    # This documents a frozen implementation defect, not an approved sampling rule.
    assert len(result)==2
    assert result.duplicated(['decision_session','ticker','driver_id','entry_style']).any()

def test_seal_refuses_historical_trace_deletion(tmp_path):
    context=seal_fixture(tmp_path)
    state=json.loads(context.read_text())
    old=pd.read_csv(tmp_path/'entry_plan_trace_v2.csv')
    old.loc[0,'decision_session']='2026-09-03'
    state['old_trace']=old.to_csv(index=False)
    context.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='HISTORICAL_TRACE_REWRITE'):
        pg.seal(tmp_path,context,NOW)
