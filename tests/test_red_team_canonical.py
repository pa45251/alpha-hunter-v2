import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import canonical_gate as cg

ROOT=Path(__file__).resolve().parents[1]

def fixture(tmp_path,monkeypatch):
    from test_canonical_gate import test_gate_rejects_mixed_run
    test_gate_rejects_mixed_run(tmp_path)
    out=tmp_path/'output'
    matches=pd.read_csv(out/'structural_matches.csv')
    matches['run_id']='A';matches.to_csv(out/'structural_matches.csv',index=False)
    # Complete scanner contract, independently of mutable production outputs.
    required=('market_snapshot.csv','theme_breadth.csv','leader_registry.csv','feature_history.csv',
              'market_snapshot.json','taiwan_candidate_history.csv','taiwan_industry_breadth.csv','taiwan_universe.csv')
    for name in required:
        (out/name).write_text('{}' if name.endswith('.json') else 'ticker,price\nSPY,100\n')
    m=json.loads((out/'manifest.json').read_text())
    m['authoritative_files']=[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                              for p in out.iterdir() if p.name!='manifest.json']
    (out/'manifest.json').write_text(json.dumps(m))
    assert cg.validate_canonical_snapshot(out)['gate_status']=='PASS'
    return out

def test_omitted_hash_cannot_authorize_tampered_source(tmp_path,monkeypatch):
    out=fixture(tmp_path,monkeypatch)
    m=json.loads((out/'manifest.json').read_text())
    m['authoritative_files']=[x for x in m['authoritative_files'] if x['name']!='market_snapshot.csv']
    (out/'manifest.json').write_text(json.dumps(m))
    (out/'market_snapshot.csv').write_text('ticker,price\nSPY,999999\n')
    assert cg.validate_canonical_snapshot(out)['gate_status']=='FAIL'

def test_null_run_row_cannot_hide_in_dropna(tmp_path,monkeypatch):
    out=fixture(tmp_path,monkeypatch)
    p=out/'causal_research_queue.csv';q=pd.read_csv(p)
    q.loc[q.index[0],'run_id']=None;q.to_csv(p,index=False)
    m=json.loads((out/'manifest.json').read_text())
    for x in m['authoritative_files']:
        if x['name']==p.name:x['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(m))
    assert cg.validate_canonical_snapshot(out)['gate_status']=='FAIL'
