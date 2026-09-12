"""Exercise the actual daily -> decision -> action chain with synthetic providers.

This proves integration and fail-closed behavior, not live market-data acceptance.
"""
import json
import runpy
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def test_daily_chain_seals_discovery_without_activating_drivers(tmp_path, monkeypatch):
    import market_data
    import taiwan_sensor
    import risk_regime
    root=Path(__file__).resolve().parents[1]
    for source in root.glob('*.py'):
        shutil.copy2(source,tmp_path/source.name)
    shutil.copytree(root/'config',tmp_path/'config')
    (tmp_path/'input').mkdir()
    source_uni=pd.read_csv(root/'output/taiwan_universe.csv',dtype={'code':str})
    graph=pd.read_csv(root/'config/structural_exposure_graph.csv',dtype={'taiwan_code':str})
    uni=source_uni[source_uni.code.isin(graph.taiwan_code)].copy()
    assert len(uni)>20
    end=datetime.now().date()-timedelta(days=1)
    index=pd.bdate_range(end=end,periods=200)
    def bars(ticker):
        slope=.0002 if ticker.startswith('^') or ticker=='SPY' else .001+(sum(map(ord,ticker))%15)*.0001
        close=100*np.exp(slope*np.arange(200))
        if ticker=='^UST2Y':close=np.linspace(4.5,4.1,200)
        return pd.DataFrame({'Open':close,'High':close*1.01,'Low':close*.99,
                             'Close':close,'Volume':10_000_000.},index=index)
    def download(self,tickers,period):return {t:bars(t) for t in tickers if t!='ABB'}
    monkeypatch.setattr(market_data.YFinanceProvider,'download',download)
    monkeypatch.setattr(taiwan_sensor,'fetch_taiwan_universe',lambda:uni)
    monkeypatch.setattr(taiwan_sensor,'_download_chunked',lambda tickers,*a,**k:{t:bars(t) for t in tickers})
    class Ticker:
        def __init__(self,ticker):self.ticker=ticker
        def history(self,**kwargs):return bars(self.ticker)
    monkeypatch.setattr(taiwan_sensor.yf,'Ticker',Ticker)
    monkeypatch.setattr(risk_regime,'download_ust2y',lambda:bars('^UST2Y'))
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(tmp_path/'daily_scan.py'),run_name='__main__')
    out=tmp_path/'output'
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['status']=='PASS'
    assert manifest['global']['core_universe_count']==221
    assert manifest['global']['scanned_count']==220
    quality=json.loads((out/'global_scan_quality.json').read_text())
    assert quality['core_download']['missing_tickers']==['ABB']
    assert quality['discovery']['scanned_count']==433
    sealed={r['name'] for r in manifest['authoritative_files']}
    assert {'discovery_snapshot.csv','discovery_research_queue.csv','global_scan_quality.json'} <= sealed
    core=pd.read_csv(out/'market_snapshot.csv')
    discovery=pd.read_csv(out/'discovery_snapshot.csv')
    assert not set(core.ticker)&set(discovery.ticker)
    assert core.universe_layer.eq('CORE').all()
    assert not pd.read_csv(out/'structural_matches.csv').decision_eligible.any()
    assert pd.read_csv(out/'causal_research_queue.csv').activation_state.eq('UNRESOLVED_RESEARCH_REQUIRED').all()
    # All downstream scripts run normally from sealed data, without network mocks.
    for script,args in [('decision_run_v2.py',[]),('action_board_summary.py',['--refresh']),('research_handoff.py',[])]:
        completed=subprocess.run([sys.executable,script,*args],cwd=tmp_path,capture_output=True,text=True,timeout=60)
        assert completed.returncode==0,completed.stdout+completed.stderr
    assert (out/'action_board.md').exists()
    assert json.loads((out/'research_handoff.json').read_text())['handoff_status']=='PASS'
