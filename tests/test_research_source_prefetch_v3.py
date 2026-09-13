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


def _company_handoff():
    return {
        'run_id': 'run-1',
        'company_research_targets': [
            {
                'ticker': '2605.TW',
                'name': '新興',
                'driver_id': 'DRY_BULK_FREIGHT',
                'driver_label': 'Dry-bulk freight / commodity shipping cycle',
                'research_task': 'VALIDATE_COMPANY_TRANSMISSION',
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


def test_company_transport_recomputed_after_official_evidence_enrichment(monkeypatch):
    monkeypatch.setattr(prefetch, '_search', lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(prefetch, 'official_company_revenue', lambda *args, **kwargs: {
        '2605.TW': [{
            'source_title': 'Official monthly revenue',
            'source_url': 'https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv',
            'published_at': '2026-09-13T00:00:00+00:00',
            'snippet': 'Official company revenue evidence.',
            'search_lane': 'OFFICIAL_COMPANY_REVENUE',
        }]
    })
    out = prefetch.build_prefetch(_company_handoff(), per_query=3)
    assert out['status'] == 'PASS'
    assert out['driver_transport_status'] == 'NOT_REQUIRED'
    assert out['company_transport_status'] == 'PASS'
    assert out['company_targets'][0]['candidate_source_count'] == 1


def test_company_transport_still_fails_closed_without_any_final_source(monkeypatch):
    monkeypatch.setattr(prefetch, '_search', lambda *args, **kwargs: ([], None))
    monkeypatch.setattr(prefetch, 'official_company_revenue', lambda *args, **kwargs: {})
    out = prefetch.build_prefetch(_company_handoff(), per_query=3)
    assert out['status'] == 'FAIL_CLOSED'
    assert out['company_transport_status'] == 'FAIL_CLOSED'
    assert out['company_targets'][0]['candidate_source_count'] == 0
