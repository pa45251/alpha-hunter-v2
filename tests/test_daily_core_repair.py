import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import canonical_evidence as ce
import risk_regime as rr
from decision_run import _activation_source_for_run


def seal(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'status': 'PASS', 'run_id': 'TODAY', 'authoritative_files': [
            {'name': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]}))


def test_risk_reader_rejects_relabelled_and_mutated_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, 'OUT', tmp_path)
    seal(tmp_path, 'risk_regime.json', {'source_run_id': 'YESTERDAY', 'status': 'READY'})
    with pytest.raises(RuntimeError, match='RUN_MISMATCH'):
        rr.build_risk_regime()
    seal(tmp_path, 'risk_regime.json', {'source_run_id': 'TODAY', 'status': 'READY'})
    assert rr.build_risk_regime()['source_run_id'] == 'TODAY'
    (tmp_path / 'risk_regime.json').write_text('{}')
    with pytest.raises(RuntimeError, match='HASH_MISMATCH'):
        rr.build_risk_regime()


def test_no_current_research_cannot_fall_back_to_legacy(tmp_path, monkeypatch):
    import decision_run
    monkeypatch.setattr(decision_run, 'OUT', tmp_path)
    monkeypatch.setenv('ALPHA_HUNTER_ACTIVATION_SOURCE', 'AUTO')
    pd.DataFrame({'research_run_id':['YESTERDAY'], 'activation_source':['V3_AUTONOMOUS_RESEARCH']}).to_csv(tmp_path / 'driver_activation_v3.csv', index=False)
    path, source = _activation_source_for_run('TODAY')
    assert not path.exists()
    assert source == 'UNKNOWN_NO_CURRENT_RESEARCH'


def test_missing_yield_does_not_become_supportive():
    index = pd.bdate_range(end=datetime.now().date(), periods=100)
    h = {t:pd.DataFrame({'Close':np.linspace(100,120,100)},index=index) for t in rr.RISK_TICKERS}
    h['^TNX'] = pd.DataFrame({'Close':np.linspace(5,4,100)},index=index)
    del h['^UST2Y']
    result = rr.build_risk_regime(h)
    assert result['signals']['rate_pressure'] == 'UNKNOWN'


def test_stale_yield_does_not_support_today():
    index = pd.bdate_range(end=datetime.now().date(), periods=100)
    h = {t:pd.DataFrame({'Close':np.linspace(100,120,100)},index=index) for t in rr.RISK_TICKERS}
    h['^UST2Y'].index -= timedelta(days=40)
    r = rr.build_risk_regime(h, validate_freshness=True)
    assert r['signals']['ust2y']['pressure_state'] == 'UNKNOWN'


def test_fred_parser_preserves_percent_and_missing_days(monkeypatch):
    dates = pd.bdate_range('2026-01-01',periods=70)
    text = 'observation_date,DGS2\n' + '\n'.join(f'{d.date()},{"." if i==4 else "4.25"}' for i,d in enumerate(dates))
    class Response:
        def raise_for_status(self): pass
    response = Response(); response.text = text
    monkeypatch.setattr(rr.requests,'get',lambda *a,**k:response)
    frame = rr.download_ust2y()
    assert len(frame)==69
    assert frame.Close.eq(4.25).all()
    assert dates[4] not in frame.index


def test_history_roundtrip_has_no_downstream_download(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out=tmp_path/'output';out.mkdir()
    h=pd.DataFrame({'Close':[1.,2.], 'High':[1.5,2.5]},index=pd.to_datetime(['2026-09-09','2026-09-10']))
    seal(out,'market_snapshot.json',{'run_id':'TODAY','entry_histories':ce.encode_histories({'XYZ.TW':h})})
    got=ce.load_histories(['XYZ.TW','MISSING'])
    pd.testing.assert_frame_equal(got['XYZ.TW'],h,check_like=True)
    assert 'MISSING' not in got


def test_daily_workflow_does_not_require_research_or_full_test_suite():
    text=Path('.github/workflows/daily_scan.yml').read_text()
    assert 'run: python -m pytest -q\n' not in text
    assert 'python decision_run_v2.py' in text
    assert 'python action_board_summary.py --refresh' in text
    assert 'git rebase' not in text
    assert 'python -m pytest -q\n' in Path('.github/workflows/pr_ci_v2.yml').read_text()
