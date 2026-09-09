import hashlib
import json
import pytest
import canonical_price_inputs as cp
import risk_regime as rr


def fixture(out):
    data={'contract':cp.CONTRACT,'source_run_id':'R','histories':{'SPY':{'dates':['2026-09-04'],'columns':['Close'],'data':[[100.0]]}}}
    p=out/cp.NAME;p.write_text(json.dumps(data))
    m={'run_id':'R','authoritative_files':[{'name':cp.NAME,'sha256':cp.sha(p)}]}
    (out/'manifest.json').write_text(json.dumps(m))
    return p,m

def test_price_frame_bound_to_run_and_hash(tmp_path):
    fixture(tmp_path)
    assert cp.load(tmp_path)['SPY'].iloc[0]['Close']==100

@pytest.mark.parametrize('fault',['mixed','tampered','missing','undeclared'])
def test_reject_mixed_or_missing_price_bundle(tmp_path,fault):
    p,m=fixture(tmp_path)
    if fault=='mixed':m['run_id']='OTHER'
    elif fault=='tampered':p.write_text(p.read_text().replace('100.0','999.0'))
    elif fault=='missing':p.unlink()
    else:m['authoritative_files']=[]
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises((RuntimeError,OSError)):cp.load(tmp_path)

def test_missing_canonical_risk_never_falls_back_to_network(tmp_path,monkeypatch):
    def missing():raise RuntimeError('MISSING_CANONICAL_INPUT')
    monkeypatch.setattr(cp,'load',missing)
    calls=[];monkeypatch.setattr(rr,'_download',lambda:calls.append(1))
    with pytest.raises(RuntimeError,match='MISSING_CANONICAL_INPUT'):
        rr.build_risk_regime()
    assert calls==[]
