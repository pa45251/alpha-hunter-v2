import json

import research_quality_gate_v3 as qg


def test_quality_gate_rejects_zero_source_pass(tmp_path):
    p = tmp_path / 'research.json'
    p.write_text(json.dumps({
        'status': 'PASS',
        'results': [
            {'state': 'UNKNOWN', 'source_count': 0},
            {'state': 'UNKNOWN', 'source_count': 0},
        ],
    }), encoding='utf-8')
    q = qg.evaluate(p)
    assert q['quality_pass'] is False
    assert q['total_sources'] == 0


def test_quality_gate_accepts_source_backed_unknown(tmp_path):
    p = tmp_path / 'research.json'
    p.write_text(json.dumps({
        'status': 'PASS',
        'results': [
            {'state': 'UNKNOWN', 'source_count': 1},
            {'state': 'UNKNOWN', 'source_count': 0},
        ],
    }), encoding='utf-8')
    q = qg.evaluate(p)
    assert q['quality_pass'] is True
    assert q['sourced_drivers'] == 1


def test_quality_gate_rejects_nonpass_even_with_sources(tmp_path):
    p = tmp_path / 'research.json'
    p.write_text(json.dumps({
        'status': 'RESEARCH_UNAVAILABLE',
        'results': [{'state': 'ACTIVE', 'source_count': 2}],
    }), encoding='utf-8')
    q = qg.evaluate(p)
    assert q['quality_pass'] is False
