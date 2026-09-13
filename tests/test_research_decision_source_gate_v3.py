import pytest

import research_decision_source_gate_v3 as gate


def _base_quality():
    return {
        'status': 'PASS',
        'evidence_pass': False,
        'transport_pass': False,
        'transport_present': True,
        'transport_status': 'FAIL_CLOSED',
        'target_count': 5,
        'total_sources': 0,
        'sourced_drivers': 0,
        'active_or_inactive': 0,
        'query_attempt_count': 10,
        'successful_query_count': 10,
        'candidate_source_count': 0,
        'sourced_target_count': 0,
        'company_terminal_accounting_pass': True,
        'company_research_complete': True,
    }


def test_exhaustive_unknown_no_evidence_allows_fail_closed_downstream(monkeypatch, capsys):
    monkeypatch.setattr(gate, 'evaluate_research_quality', _base_quality)
    monkeypatch.setattr(gate, '_challenger_is_valid', lambda: (False, 0, 0, 'missing'))
    gate.main()
    out = capsys.readouterr().out
    assert 'exhaustive no-evidence research' in out


def test_no_evidence_does_not_hide_incomplete_company_research(monkeypatch):
    q = _base_quality()
    q['company_research_complete'] = False
    monkeypatch.setattr(gate, 'evaluate_research_quality', lambda: q)
    monkeypatch.setattr(gate, '_challenger_is_valid', lambda: (False, 0, 0, 'missing'))
    with pytest.raises(SystemExit):
        gate.main()


def test_no_evidence_does_not_hide_transport_outage(monkeypatch):
    q = _base_quality()
    q['successful_query_count'] = 0
    monkeypatch.setattr(gate, 'evaluate_research_quality', lambda: q)
    monkeypatch.setattr(gate, '_challenger_is_valid', lambda: (False, 0, 0, 'missing'))
    with pytest.raises(SystemExit):
        gate.main()
