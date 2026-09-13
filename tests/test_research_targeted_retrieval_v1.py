import research_targeted_retrieval_v1 as targeted


def _fetched(row):
    out = dict(row)
    out.setdefault('source_url', 'https://example.com/source')
    out.setdefault('source_title', 'evidence')
    out['fetch_status'] = 'FETCHED'
    out['document_text'] = out.get('document_text') or ('AI server shipment backlog increased ' * 20)
    return out


def test_company_transmission_gap_skips_redundant_can_search(monkeypatch):
    calls = []
    monkeypatch.setattr(targeted, '_search', lambda q, **kwargs: (calls.append(q) or [{
        'source_url': f'https://example.com/{len(calls)}', 'source_title': 'evidence', 'snippet': 'x'
    }], None))
    monkeypatch.setattr(targeted, 'acquire', lambda row, timeout=12: _fetched(row))
    handoff = {'run_id': 'r', 'company_research_targets': [{
        'ticker': '3044.TW', 'name': '健鼎', 'driver_id': 'AI_SERVER_SHIPMENTS',
        'driver_label': 'AI server shipment / ODM cycle',
        'missing_gate': 'COMPANY_TRANSMISSION_UNVERIFIED',
        'exposure_source_urls': ['https://issuer.example/products'],
    }]}
    prefetch = {'research_run_id': 'r', 'targets': [], 'company_targets': [{
        'ticker': '3044.TW', 'driver_id': 'AI_SERVER_SHIPMENTS', 'event_id': '',
        'candidate_sources': [], 'candidate_source_count': 0,
    }]}
    out = targeted.enhance_prefetch(handoff, prefetch, per_query=2)
    packet = out['company_targets'][0]
    assert packet['retrieval_slots'] == ['REACH', 'COUNTER']
    assert len(calls) == 2
    assert all('產品 應用 客戶' not in q for q in calls)


def test_shared_driver_search_uses_measurement_specific_terms(monkeypatch):
    calls = []
    monkeypatch.setattr(targeted, '_search', lambda q, **kwargs: (calls.append(q) or [{
        'source_url': f'https://example.com/{len(calls)}', 'source_title': 'driver evidence', 'snippet': 'x'
    }], None))
    monkeypatch.setattr(targeted, 'acquire', lambda row, timeout=12: _fetched(row))
    handoff = {'run_id': 'r', 'research_targets': [{
        'driver_id': 'AI_SERVER_SHIPMENTS', 'driver_label': 'AI server shipment / ODM cycle',
        'driver_scope': 'AI server units, rack shipments, ODM backlog',
    }]}
    prefetch = {'research_run_id': 'r', 'targets': [{
        'driver_id': 'AI_SERVER_SHIPMENTS', 'candidate_sources': [], 'candidate_source_count': 0,
    }], 'company_targets': []}
    out = targeted.enhance_prefetch(handoff, prefetch, per_query=2)
    assert out['targets'][0]['candidate_source_count'] > 0
    assert any('rack shipments' in q and 'ODM backlog' in q for q in calls)


def test_focused_text_keeps_relevant_window_instead_of_only_document_head():
    text = ('boilerplate ' * 3000) + ' AI server rack shipments increased and ODM backlog expanded ' + ('tail ' * 3000)
    focused = targeted._focused_text(text, ['ai server', 'odm backlog'], max_chars=3000)
    assert 'AI server rack shipments' in focused
    assert 'ODM backlog expanded' in focused
    assert len(focused) <= 3000
