import json

import research_quality_gate_v3 as qg


def test_quality_gate_rejects_zero_source_pass_without_transport(tmp_path):
    p = tmp_path / 'research.json'
    p.write_text(json.dumps({
        'status': 'PASS',
        'research_run_id': 'run-1',
        'results': [
            {'state': 'UNKNOWN', 'source_count': 0},
            {'state': 'UNKNOWN', 'source_count': 0},
        ],
    }), encoding='utf-8')
    q = qg.evaluate(p, tmp_path / 'missing-transport.json')
    assert q['quality_pass'] is False
    assert q['total_sources'] == 0
    assert q['transport_pass'] is False


def test_quality_gate_accepts_source_backed_unknown(tmp_path):
    p = tmp_path / 'research.json'
    p.write_text(json.dumps({
        'status': 'PASS',
        'research_run_id': 'run-1',
        'results': [
            {'state': 'UNKNOWN', 'source_count': 1},
            {'state': 'UNKNOWN', 'source_count': 0},
        ],
    }), encoding='utf-8')
    q = qg.evaluate(p, tmp_path / 'missing-transport.json')
    assert q['quality_pass'] is True
    assert q['evidence_pass'] is True
    assert q['sourced_drivers'] == 1


def test_quality_gate_rejects_nonpass_even_with_sources(tmp_path):
    p = tmp_path / 'research.json'
    p.write_text(json.dumps({
        'status': 'RESEARCH_UNAVAILABLE',
        'research_run_id': 'run-1',
        'results': [{'state': 'ACTIVE', 'source_count': 2}],
    }), encoding='utf-8')
    q = qg.evaluate(p, tmp_path / 'missing-transport.json')
    assert q['quality_pass'] is False


def test_quality_gate_accepts_zero_source_when_deterministic_transport_proves_search(tmp_path):
    p = tmp_path / 'research.json'
    transport = tmp_path / 'transport.json'
    p.write_text(json.dumps({
        'status': 'PASS',
        'research_run_id': 'run-1',
        'results': [
            {'state': 'UNKNOWN', 'source_count': 0},
            {'state': 'UNKNOWN', 'source_count': 0},
        ],
    }), encoding='utf-8')
    transport.write_text(json.dumps({
        'contract': 'ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH',
        'status': 'PASS',
        'research_run_id': 'run-1',
        'target_count': 2,
        'query_attempt_count': 4,
        'successful_query_count': 4,
        'candidate_source_count': 6,
        'sourced_target_count': 2,
    }), encoding='utf-8')
    q = qg.evaluate(p, transport)
    assert q['quality_pass'] is True
    assert q['evidence_pass'] is False
    assert q['transport_pass'] is True
    assert q['candidate_source_count'] == 6


def test_quality_gate_rejects_transport_run_id_mismatch(tmp_path):
    p = tmp_path / 'research.json'
    transport = tmp_path / 'transport.json'
    p.write_text(json.dumps({
        'status': 'PASS',
        'research_run_id': 'run-1',
        'results': [{'state': 'UNKNOWN', 'source_count': 0}],
    }), encoding='utf-8')
    transport.write_text(json.dumps({
        'contract': 'ALPHA_HUNTER_V3_RESEARCH_SOURCE_PREFETCH',
        'status': 'PASS',
        'research_run_id': 'stale-run',
        'target_count': 1,
        'query_attempt_count': 2,
        'successful_query_count': 2,
        'candidate_source_count': 2,
        'sourced_target_count': 1,
    }), encoding='utf-8')
    q = qg.evaluate(p, transport)
    assert q['quality_pass'] is False
    assert q['transport_status'] == 'RUN_ID_MISMATCH'
