import hashlib
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
from broad_discovery import load_discovery, research_clusters, refresh_membership
from scanner_core import run_scan, ScanConfig, compute_theme_breadth, add_cross_section_scores, update_registry
from causal_engine import theme_strength, build_causal_research_queue
from reverse_discovery import _top_global_peers
from test_global_sensors import history


def cache(path, tickers, age=0):
    frame = pd.DataFrame({'ticker':tickers, 'name':tickers, 'industry_cluster':'UnknownCluster',
                          'region':'US','universe_layer':'DISCOVERY'})
    body=frame.to_csv(index=False); path.write_text(body)
    path.with_suffix('.json').write_text(json.dumps({'fetched_at_utc':(datetime.now(timezone.utc)-timedelta(days=age)).isoformat(),
        'sha256':hashlib.sha256(body.encode()).hexdigest(), 'member_count':len(frame)}))


def test_discovery_does_not_change_any_core_output(tmp_path):
    class Provider:
        name='fixture'
        def download(self,tickers,period):
            return {t:history(.003 if t.startswith('D') else .001) for t in tickers}
    core=tmp_path/'core.csv'; disc=tmp_path/'discovery.csv'
    pd.DataFrame({'ticker':['A','B','C'], 'theme':'Memory'}).to_csv(core,index=False)
    cache(disc, ['A','D1','D2','D3','D4'])
    baseline=run_scan(core,ScanConfig(provider=Provider(),output_dir=str(tmp_path)))
    mixed=run_scan(core,ScanConfig(provider=Provider(),output_dir=str(tmp_path),discovery_csv=str(disc)))
    for key in ('stocks','breadth'):
        pd.testing.assert_frame_equal(baseline[key],mixed[key])
    pd.testing.assert_frame_equal(baseline['registry'].drop(columns='updated_at_utc'),mixed['registry'].drop(columns='updated_at_utc'))
    assert set(mixed['discovery'].ticker)=={'D1','D2','D3','D4'}
    assert not set(mixed['discovery'].ticker) & set(mixed['histories'])
    assert len(mixed['discovery_queue'])==1
    assert not mixed['discovery_queue'].decision_eligible.any()
    # An accidental concatenation cannot contaminate boundary functions either.
    injected=mixed['discovery'].assign(theme='Memory',leader_score_v1=999,acceleration=999,raw_leader_state='PERSISTENT')
    both=pd.concat([mixed['stocks'],injected],ignore_index=True)
    pd.testing.assert_frame_equal(compute_theme_breadth(both),mixed['breadth'])
    pd.testing.assert_frame_equal(theme_strength(both),theme_strength(mixed['stocks']))
    assert 'D1' not in _top_global_peers(both,'Memory')
    assert set(add_cross_section_scores(both).ticker)=={'A','B','C'}
    taxonomy=pd.read_csv('config/causal_driver_taxonomy.csv')
    pd.testing.assert_frame_equal(build_causal_research_queue(both,taxonomy),build_causal_research_queue(mixed['stocks'],taxonomy))


def test_source_failure_retains_valid_cache_and_expired_is_disabled(tmp_path,monkeypatch):
    import broad_discovery
    def fail(*a,**k): raise TimeoutError('offline')
    monkeypatch.setattr(broad_discovery.requests,'get',fail)
    path=tmp_path/'discovery.csv';cache(path,['D1'],age=40)
    frame,quality=load_discovery(path,[])
    assert len(frame)==1 and quality['status']=='STALE_CACHE'
    cache(path,['D1'],age=100)
    frame,quality=load_discovery(path,[])
    assert frame.empty and quality['status']=='UNAVAILABLE'


def test_schema_change_does_not_overwrite_snapshot(tmp_path,monkeypatch):
    import broad_discovery
    path=tmp_path/'discovery.csv';cache(path,['D1'])
    old=path.read_bytes()
    class Response:
        text='unexpected\nvalue\n'
        def raise_for_status(self):pass
    monkeypatch.setattr(broad_discovery.requests,'get',lambda *a,**k:Response())
    import pytest
    with pytest.raises(ValueError,match='SCHEMA'):
        refresh_membership(path)
    assert path.read_bytes()==old


def test_single_company_event_cannot_nominate_cluster():
    rows=pd.DataFrame({'ticker':['A','B','C'], 'industry_cluster':'Unknown',
         'rs_20d_vs_bench':[.9,-.01,-.01], 'rs_60d_vs_bench':[.9,-.01,-.01],
         'price':[110,100,100], 'ma20':100, 'ma60':100})
    assert research_clusters(rows).empty


def test_missing_members_cannot_manufacture_breadth():
    rows=pd.DataFrame({'ticker':['A','B','C'], 'industry_cluster':'Unknown',
         'rs_20d_vs_bench':.1, 'rs_60d_vs_bench':.1, 'price':110, 'ma20':100, 'ma60':100})
    universe=pd.DataFrame({'ticker':['A','B','C','D','E','F'], 'industry_cluster':'Unknown'})
    assert research_clusters(rows,universe).empty


def test_share_classes_are_one_company_witness():
    rows=pd.DataFrame({'ticker':['A','AA','B'], 'issuer_id':['1','1','2'], 'industry_cluster':'Unknown',
         'rs_20d_vs_bench':.1, 'rs_60d_vs_bench':.1, 'price':110, 'ma20':100, 'ma60':100})
    assert research_clusters(rows).empty
