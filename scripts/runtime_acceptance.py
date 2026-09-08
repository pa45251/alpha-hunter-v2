"""Execute production entrypoints in an isolated process with deterministic provider fixtures.

No real research, private portfolio or frozen output is used or written. Run from repository root.
The price provider deliberately returns a future sentinel; actual production clipping must remove it.
"""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def worker():
    import hashlib
    import numpy as np
    import pandas as pd
    import yfinance as yf
    import taiwan_sensor
    import market_sessions as ms
    import runtime_input_guard
    now=ms.clock()
    os.environ['ALPHA_HUNTER_ACTIVATION_SOURCE']='V3_VALIDATED'
    policy={'policy_version':'SYNTHETIC_RUNTIME_ACCEPTANCE','max_single_position_pct':50,
            'max_theme_exposure_pct':70,'max_gross_exposure_pct':100,'max_new_position_pct':3,
            'min_avg_turnover_twd':100000000,'max_position_loss_pct':10}
    portfolio={'market_value_twd':100000,'financing_debt_twd':0,'cash_twd':900000,
               'positions':[{'ticker':'2317.TW','market_value_twd':100000,'risk_groups':['AI_CAPEX']}]}
    os.environ['ALPHA_HUNTER_RISK_POLICY_JSON']=json.dumps(policy)
    os.environ['ALPHA_HUNTER_PORTFOLIO_JSON']=json.dumps(portfolio)
    os.environ['ALPHA_HUNTER_POSITION_ALIAS_JSON']=json.dumps({'2317':'SYNTHETIC_A'})
    os.environ['ALPHA_HUNTER_POSITION_THESIS_JSON']='{}'
    os.environ['ALPHA_HUNTER_MAINTENANCE_RESEARCH_PATH']=str(Path('nonexistent-private-fixture.json').resolve())

    def hist(ticker):
        idx=ms.closed_sessions(ticker,now)[-250:]
        seed=int(hashlib.sha256(ticker.encode()).hexdigest()[:4],16)
        rate=0.0004 if ticker in ('SPY','^TWII') else 0.0015+(seed%10)*0.00012
        close=80*np.exp(np.arange(len(idx))*rate)
        # A controlled final base creates conditional plans without changing strategy rules.
        if ticker not in ('SPY','^TWII'):
            close[-20:]=close[-21]*(1+0.001*np.sin(np.arange(20)))
        x=pd.DataFrame({'Open':close*0.999,'High':close*1.004,'Low':close*0.996,
                        'Close':close,'Adj Close':close,'Volume':10000000.0},index=idx)
        x.loc[pd.Timestamp(now.date())+pd.Timedelta(days=5)]=[99999]*6
        return x

    def download(tickers,**kwargs):
        if isinstance(tickers,str):tickers=tickers.split()
        return pd.concat({t:hist(t) for t in tickers},axis=1)
    yf.download=download
    class Ticker:
        def __init__(self,t):self.t=t
        def history(self,**kwargs):return hist(self.t)
    yf.Ticker=Ticker
    graph=pd.read_csv('config/structural_exposure_graph.csv',dtype={'taiwan_code':str})
    codes=graph.taiwan_code.drop_duplicates().tolist()
    universe=pd.DataFrame([{'ticker':c+'.TW','code':c,'name':'SYNTHETIC_'+c,
                            'industry':'SYNTHETIC','exchange':'TWSE','market':'TWSE'} for c in codes])
    taiwan_sensor.fetch_taiwan_universe=lambda *a,**kw:universe.copy()
    phases=[]
    def run(module,guard=False):
        if guard:
            saved=sys.argv;sys.argv=['runtime_input_guard.py',module]
            try:runtime_input_guard.main()
            finally:sys.argv=saved
        else:runpy.run_module(module,run_name='__main__')
        phases.append(module)
    run('daily_scan')
    run('canonical_price_inputs')
    def forbidden_download(*a,**kw):
        raise AssertionError('DOWNSTREAM_LIVE_PRICE_READ_FORBIDDEN')
    yf.download=forbidden_download
    run('research_handoff')
    out=Path('output');packet=json.loads((out/'research_packet.json').read_text())
    rid=packet['run_id'];stamp=now.isoformat()
    results=[]
    for row in packet['research_queue_top30'][:5]:
        results.append({'driver_id':row['driver_id'],'state':'ACTIVE','confidence':0.9,
          'primary_cause':'SYNTHETIC_ACCEPTANCE_ONLY','industry_scope':'INDUSTRY_WIDE',
          'supporting_evidence':[{'claim':'SYNTHETIC_ACCEPTANCE_ONLY','source_title':'Fixture',
          'source_url':'https://example.invalid/fixture/'+row['driver_id'],'published_at':stamp,
          'evidence_type':'PRIMARY'}], 'counter_evidence':[], 'source_count':1,
          'researched_at_utc':stamp,'research_run_id':rid})
    (out/'research_result_v3.raw.txt').write_text(json.dumps({'contract':'ALPHA_HUNTER_V3_AUTONOMOUS_RESEARCH','research_run_id':rid,'results':results}))
    run('research_ingest_v3');run('research_decision_source_gate_v3');run('research_activation_bridge_v3')
    run('decision_run_with_maintenance_v2',True)
    first=pd.read_csv(out/'decision_board.csv')
    run('decision_run_with_maintenance_v2',True)
    second=pd.read_csv(out/'decision_board.csv')
    pd.testing.assert_frame_equal(first,second)
    run('position_alias_output_v2',True);run('position_cio_advisory',True)
    from publication_guard import begin,seal,readiness
    context=Path('publication-context.json')
    begin(out,context)
    for module in ['cio_advisory','risk_regime','portfolio_allocation_advisory','global_alignment',
                   'global_alignment_v2','entry_plan_run_v2','entry_plan_trace_v2','portfolio_allocation_v2',
                   'action_board_summary','global_alignment_summary','portfolio_allocation_summary','entry_action_board_v2']:
        run(module,module=='entry_plan_run_v2')
    seal(out,context)
    assert readiness(out)['status']=='READY_CURRENT_SNAPSHOT'
    before=(out/'entry_plan_trace_v2.csv').read_bytes()
    run('entry_plan_trace_v2')
    assert (out/'entry_plan_trace_v2.csv').read_bytes()==before
    (out/'entry_plans_v2.json').unlink()
    assert readiness(out)['status']=='NOT_READY'
    print('RUNTIME_ACCEPTANCE_RESULT='+json.dumps({'mode':'DETERMINISTIC_PROVIDER_FIXTURES',
       'phases':phases,'same_session_decision_equal':True,'same_session_trace_equal':True,
       'missing_output_fail_closed':True,'production_credentials_used':False,'live_research_verified':False,
       'status':'PASS'}))


def main():
    if '--worker' in sys.argv:
        worker();return
    with tempfile.TemporaryDirectory(prefix='alpha-runtime-') as td:
        dst=Path(td)
        for p in ROOT.glob('*.py'):shutil.copy2(p,dst/p.name)
        for name in ('config','input'):
            shutil.copytree(ROOT/name,dst/name)
        (dst/'output').mkdir()
        env=os.environ.copy();env['PYTHONPATH']=str(dst)
        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],cwd=dst,env=env)
        raise SystemExit(child.returncode)

if __name__=='__main__':main()
