import hashlib
import json

import pandas as pd
import pytest

from driver_gates import _company_breadth_row, _independent_company_peers, international_price, sealed_csv
from research_contract_v3 import ResearchContractError
from research_ingest_v3 import _assert_urls_prefetched, _prefetch_allowlists


def _peer(ticker, name, state='PERSISTENT', rs=0.10):
    return {
        'ticker': ticker,
        'name': name,
        'theme': 'Cybersecurity',
        'universe_layer': 'CORE',
        'price': 110.0,
        'ma20': 100.0,
        'ma60': 95.0,
        'rs_5d_vs_bench': rs,
        'rs_20d_vs_bench': rs,
        'rs_60d_vs_bench': rs,
        'acceleration': rs / 2,
        'dist_20d_high': -0.01,
        'dist_52w_high': -0.02,
        'raw_leader_state': state,
    }


def test_independent_company_breadth_excludes_etf_wrapper():
    peers = pd.DataFrame([
        _peer('HACK', 'Cybersecurity ETF'),
        _peer('PANW', 'Palo Alto Networks'),
        _peer('CRWD', 'CrowdStrike'),
        _peer('FTNT', 'Fortinet'),
    ])
    independent = _independent_company_peers(peers)
    assert set(independent['ticker']) == {'PANW', 'CRWD', 'FTNT'}
    breadth = _company_breadth_row(peers)
    assert breadth is not None
    assert breadth['independent_company_count'] == 3


def test_international_price_fails_closed_when_only_etf_plus_two_companies():
    breadth = pd.DataFrame([{
        'theme': 'Cybersecurity',
        'breadth_confidence': 'MEDIUM',
        'above_ma20_pct': 1.0,
        'above_ma60_pct': 1.0,
        'positive_rs20_pct': 1.0,
        'positive_rs5_pct': 1.0,
        'near_20d_high_pct': 1.0,
        'near_52w_high_pct': 1.0,
        'median_rs20': 0.2,
    }])
    peers = pd.DataFrame([
        _peer('HACK', 'Cybersecurity ETF'),
        _peer('PANW', 'Palo Alto Networks'),
        _peer('CRWD', 'CrowdStrike'),
    ])
    result = international_price('Cybersecurity', breadth, peers)
    assert result['international_price_state'] == 'UNKNOWN'
    assert 'independent company breadth' in result['international_price_reason']


def test_prefetch_allowlist_blocks_unseen_model_url(tmp_path, monkeypatch):
    transport = tmp_path / 'prefetch.json'
    transport.write_text(json.dumps({
        'contract': 'ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH',
        'status': 'PASS',
        'research_run_id': 'run-1',
        'targets': [{
            'driver_id': 'AI_SERVER_SHIPMENTS',
            'candidate_sources': [{'source_url': 'https://example.com/known'}],
        }],
        'company_targets': [{
            'ticker': '3231.TW',
            'driver_id': 'AI_SERVER_SHIPMENTS',
            'candidate_sources': [{'source_url': 'https://example.com/company'}],
        }],
    }), encoding='utf-8')
    monkeypatch.setenv('ALPHA_HUNTER_RESEARCH_TRANSPORT_PATH', str(transport))
    drivers, companies = _prefetch_allowlists('run-1')
    assert drivers['AI_SERVER_SHIPMENTS'] == {'https://example.com/known'}
    assert companies[('3231.TW', 'AI_SERVER_SHIPMENTS')] == {'https://example.com/company'}
    _assert_urls_prefetched({'https://example.com/known'}, drivers['AI_SERVER_SHIPMENTS'], 'driver')
    with pytest.raises(ResearchContractError, match='UNPREFETCHED_EVIDENCE_URL'):
        _assert_urls_prefetched({'https://invented.invalid/story'}, drivers['AI_SERVER_SHIPMENTS'], 'driver')


def test_sealed_csv_accepts_authoritative_candidate_without_embedded_run_id(tmp_path):
    frame = pd.DataFrame([{'ticker': '6179.TWO', 'name': '亞通', 'reaction_state': 'PERSISTENT'}])
    csv_path = tmp_path / 'taiwan_candidates.csv'
    frame.to_csv(csv_path, index=False)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'status': 'PASS',
        'run_id': 'run-1',
        'authoritative_files': [{'name': 'taiwan_candidates.csv', 'sha256': digest}],
    }), encoding='utf-8')
    loaded = sealed_csv('taiwan_candidates.csv', tmp_path)
    assert loaded.iloc[0]['ticker'] == '6179.TWO'
    assert 'run_id' not in loaded.columns
