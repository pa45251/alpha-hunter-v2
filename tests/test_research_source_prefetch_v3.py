import research_source_prefetch_v3 as prefetch


def _handoff():
    return {
        'run_id': 'run-1',
        'research_targets': [
            {
                'driver_id': 'DRIVER_A',
                'driver_label': 'Driver A',
                'driver_scope': 'industry demand',
                'activation_evidence_required': 'orders backlog utilization',
                'counter_evidence_required': 'cancellations inventory weakness',
            },
            {
                'driver_id': 'DRIVER_B',
                'driver_label': 'Driver B',
                'driver_scope': 'pricing cycle',
                'activation_evidence_required': 'pricing demand utilization',
                'counter_evidence_required': 'price cuts oversupply',
            },
        ],
    }


def test_prefetch_attempts_support_and_counter_for_every_target(monkeypatch):
    calls = []

    def fake_search(query, timeout=15.0, limit=6):
        calls.append(query)
        idx = len(calls)
        return ([{
            'source_title': f'Source {idx}',
            'source_url': f'https://example.com/{idx}',
            'published_at': '2026-09-09T00:00:00+00:00',
            'snippet': 'Relevant evidence.',
        }], None)

    monkeypatch.setattr(prefetch, '_search', fake_search)
    out = prefetch.build_prefetch(_handoff(), per_query=3)
    assert out['status'] == 'PASS'
    assert out['query_attempt_count'] == 4
    assert out['successful_query_count'] == 4
    assert out['candidate_source_count'] == 4
    assert out['sourced_target_count'] == 2
    assert [q['lane'] for q in out['targets'][0]['queries']] == ['SUPPORT', 'COUNTER']


def test_prefetch_fails_closed_when_search_returns_no_candidates(monkeypatch):
    monkeypatch.setattr(prefetch, '_search', lambda *args, **kwargs: ([], None))
    out = prefetch.build_prefetch(_handoff(), per_query=3)
    assert out['status'] == 'FAIL_CLOSED'
    assert out['query_attempt_count'] == 4
    assert out['successful_query_count'] == 4
    assert out['candidate_source_count'] == 0
    assert out['sourced_target_count'] == 0


def test_prefetch_fails_closed_when_transport_errors(monkeypatch):
    monkeypatch.setattr(prefetch, '_search', lambda *args, **kwargs: ([], 'network down'))
    out = prefetch.build_prefetch(_handoff(), per_query=3)
    assert out['status'] == 'FAIL_CLOSED'
    assert out['successful_query_count'] == 0
    assert len(out['errors']) == 4
