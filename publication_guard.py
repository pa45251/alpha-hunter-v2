"""Fail-closed publication envelope around the unchanged Frozen V2 algorithms.

A stored PASS is insufficient: consumers recheck today's run and all sealed digests.
This envelope grants no trading permission and never edits prospective history.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import pandas as pd
from market_sessions import clock, latest_closed_session
from snapshot_lineage_v2 import assert_decision_snapshot_current

CONTRACT = 'ALPHA_HUNTER_PUBLICATION_GUARD_1'
SEAL = 'publication_readiness.json'
INPUTS = ('manifest.json','gate_report.json','decision_packet.json','decision_board.csv',
          'position_alias_actions.json','position_cio_advisory.json')
OUTPUTS = ('cio_advisory.json','risk_regime.json','global_alignment_v2.json',
           'entry_plans_v2.json','portfolio_allocation_v2.json','action_board.md',
           'global_alignment_v2.csv','entry_plans_v2.csv','entry_plan_trace_v2.csv')

def read(out, name):
    value = json.loads((out/name).read_text())
    if not isinstance(value,dict):
        raise ValueError('INVALID_OBJECT:'+name)
    return value

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(ok, code):
    if not ok:
        raise ValueError(code)

def check_current(out, now=None):
    ts=clock(now)
    m=read(out,'manifest.json')
    generated=clock(m['generated_at_taipei'])
    require(generated <= ts and generated.tz_convert('Asia/Taipei').date()==ts.tz_convert('Asia/Taipei').date(), 'STALE_OR_FUTURE_SCAN')
    require(m['taiwan']['latest_price_date']==latest_closed_session('^TWII',ts),'TAIWAN_SESSION_MISMATCH')
    rid=m.get('run_id')
    require(isinstance(rid,str) and bool(rid.strip()),'MISSING_RUN_ID')
    p=read(out,'decision_packet.json')
    require(p.get('run_id')==rid,'DECISION_RUN_MISMATCH')
    require(p.get('snapshot_lineage_layer',{}).get('manifest_sha256')==digest(out/'manifest.json'),'DECISION_MANIFEST_MISMATCH')
    for name in ('position_alias_actions.json','position_cio_advisory.json'):
        require(read(out,name).get('run_id')==rid,'POSITION_RUN_MISMATCH:'+name)
    b=pd.read_csv(out/'decision_board.csv')
    require(not b.empty and 'run_id' in b and b.run_id.notna().all() and b.run_id.eq(rid).all(),'BOARD_RUN_MISMATCH')
    for name in ('market_snapshot.csv','taiwan_candidates.csv'):
        data=pd.read_csv(out/name)
        require(not data.empty and {'ticker','last_price_date'}.issubset(data.columns),'PRICE_SESSION_MISSING')
        for r in data[['ticker','last_price_date']].itertuples(index=False):
            require(str(r.last_price_date)==latest_closed_session(r.ticker,ts),'STALE_OR_OPEN_PRICE:'+str(r.ticker))
    return rid

def check_plan_links(out):
    a=pd.read_csv(out/'global_alignment_v2.csv')
    b=pd.read_csv(out/'decision_board.csv')
    packet=read(out,'entry_plans_v2.json')
    require(packet.get('status')=='READY','ENTRY_DATA_UNAVAILABLE')
    rid=read(out,'manifest.json')['run_id']
    require(packet.get('source_run_id')==rid,'ENTRY_RUN_MISMATCH')
    require('run_id' in a and a.run_id.eq(rid).all(),'ALIGNMENT_RUN_MISMATCH')
    rows=packet.get('all_plans')
    require(isinstance(rows,list) and bool(rows),'NO_ENTRY_PLANS')
    plans={}
    for p in rows:
        key=(p.get('ticker'),p.get('driver_id'))
        require(key[0] not in plans,'DUPLICATE_ENTRY_TICKER')
        require(((a.ticker==key[0]) & (a.driver_id==key[1])).any(),'ALIGNMENT_DRIVER_MISMATCH')
        require(((b.ticker==key[0]) & (b.driver_id==key[1])).any(),'DECISION_DRIVER_MISMATCH')
        require(p.get('entry_executable') is False and p.get('auto_trade_allowed') is False,'EOD_EXECUTION_FORBIDDEN')
        require(p.get('score_is_probability') is False,'SCORE_PROBABILITY_FORBIDDEN')
        if p.get('entry_structure_valid') is True:
            vals=[p.get(k) for k in ('invalidation_price','trigger_price','buy_zone_low','buy_zone_high')]
            require(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in vals),'INVALID_ENTRY_LEVEL')
            require(vals[0]<vals[1] and vals[2]<=vals[3],'INVALID_ENTRY_ORDER')
        plans[key[0]]=p
    rotation=read(out,'portfolio_allocation_v2.json')
    require(rotation.get('status')=='READY','ROTATION_DATA_UNAVAILABLE')
    for r in rotation.get('rotations',[]):
        p=plans.get(r.get('destination_ticker'),{})
        require(bool(p) and r.get('destination_driver')==p.get('driver_id'),'ROTATION_DRIVER_MISMATCH')
        for k in ('trigger_price','buy_zone_low','buy_zone_high','invalidation_price'):
            require(r.get(k)==p.get(k),'ROTATION_PLAN_MISMATCH:'+k)
        require(r.get('suggested_source_trim_pct_now')==0,'EOD_ROTATION_FORBIDDEN')
    regime=read(out,'risk_regime.json')
    require(regime.get('status')=='READY','RISK_DATA_UNAVAILABLE')
    trace=pd.read_csv(out/'entry_plan_trace_v2.csv')
    require(not trace.duplicated(['decision_session','ticker','driver_id','entry_style']).any(),'DUPLICATE_SESSION_TRACE')
    return plans

def begin(out, context, now=None):
    assert_decision_snapshot_current(out)
    from canonical_price_inputs import load
    load(out)
    rid=check_current(out,now)
    state={'run_id':rid,'started_at':clock(now).isoformat(),
           'inputs':{n:digest(out/n) for n in INPUTS}}
    trace=out/'entry_plan_trace_v2.csv'
    # Archive bytes only in ephemeral context; never erase or repair a baseline record here.
    state['old_trace']=trace.read_text() if trace.exists() else None
    context.write_text(json.dumps(state))
    return state

def seal(out,context,now=None):
    state=json.loads(context.read_text())
    require(state['inputs']=={n:digest(out/n) for n in INPUTS},'INPUT_CHANGED_DURING_PUBLICATION')
    require(check_current(out,now)==state['run_id'],'PUBLICATION_RUN_CHANGED')
    check_plan_links(out)
    require(read(out,'risk_regime.json').get('risk_snapshot_date')==latest_closed_session('SPY',now),'RISK_SESSION_MISMATCH')
    for name in OUTPUTS:
        require((out/name).is_file(),'MISSING_OUTPUT:'+name)
        if name.endswith('.json'):
            value=read(out,name)
            require(clock(value['generated_at'])>=clock(state['started_at']),'OUTPUT_NOT_REBUILT:'+name)
    if state['old_trace']:
        from io import StringIO
        old=pd.read_csv(StringIO(state['old_trace']),dtype=str).fillna('')
        new=pd.read_csv(out/'entry_plan_trace_v2.csv',dtype=str).fillna('')
        require(len(new)>=len(old) and new.iloc[:len(old)].reset_index(drop=True).equals(old.reset_index(drop=True)),'HISTORICAL_TRACE_REWRITE')
    files=files_for_seal(out)
    result={'contract':CONTRACT,'status':'READY_CURRENT_SNAPSHOT','source_run_id':state['run_id'],
            'generated_at':clock(now).isoformat(),'hashes':{n:digest(out/n) for n in files},'auto_trade_allowed':False}
    (out/SEAL).write_text(json.dumps(result,indent=2))
    return result

def files_for_seal(out):
    declared = [x['name'] for x in read(out,'manifest.json').get('authoritative_files',[])]
    require(all(Path(n).name==n for n in declared),'UNSAFE_ARTIFACT_PATH')
    return tuple(dict.fromkeys(INPUTS+OUTPUTS+('market_snapshot.csv','taiwan_candidates.csv')+tuple(declared)))

def readiness(out=Path('output'),now=None):
    out=Path(out)
    try:
        s=read(out,SEAL)
        require(s.get('contract')==CONTRACT and s.get('status')=='READY_CURRENT_SNAPSHOT','NOT_READY')
        require(set(s.get('hashes',{}))==set(files_for_seal(out)),'INCOMPLETE_SEAL')
        require(all(digest(out/n)==h for n,h in s['hashes'].items()),'MIXED_OR_MODIFIED_PUBLICATION')
        require(check_current(out,now)==s.get('source_run_id'),'STALE_PUBLICATION')
        require(clock(s['generated_at'])<=clock(now),'FUTURE_PUBLICATION')
        require(read(out,'risk_regime.json').get('risk_snapshot_date')==latest_closed_session('SPY',now),'RISK_SESSION_MISMATCH')
        return {'status':'READY_CURRENT_SNAPSHOT','source_run_id':s['source_run_id'],'auto_trade_allowed':False}
    except Exception as exc:
        return {'status':'NOT_READY','reason':str(exc),'auto_trade_allowed':False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['begin','seal','check'])
    p.add_argument('--output',default='output')
    p.add_argument('--context',default='/tmp/alpha-publication-context.json')
    a=p.parse_args();out=Path(a.output);context=Path(a.context)
    if a.mode=='begin':
        result=begin(out,context)
    elif a.mode=='seal':
        result=seal(out,context)
    else:
        result=readiness(out)
    print(json.dumps(result if a.mode!='begin' else {'run_id':result['run_id'],'status':'BUILDING'}))
    if result.get('status')=='NOT_READY':
        raise SystemExit(1)

if __name__=='__main__':
    main()
