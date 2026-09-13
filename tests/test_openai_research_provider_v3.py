import json

import openai_research_provider_v3 as provider


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text if text is not None else json.dumps(self._payload)
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


def valid_model_payload(run_id='run'):
    return {
        'contract': 'ALPHA_HUNTER_V3_AUTONOMOUS_RESEARCH',
        'research_run_id': run_id,
        'results': [],
        'company_opportunities': [],
        'company_research_coverage': [],
        'exposure_resolutions': [],
        'company_execution_failures': [],
    }


def test_openai_provider_calls_responses_api_and_returns_contract(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_RESEARCH_MODEL', 'gpt-5.6-terra')
    monkeypatch.setenv('OPENAI_RESEARCH_REASONING_EFFORT', 'high')
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, request=json, timeout=timeout)
        model_output = json_module.dumps(valid_model_payload())
        return FakeResponse(payload={'id': 'resp_1', 'output_text': model_output, 'usage': {'input_tokens': 10}})

    json_module = json
    monkeypatch.setattr(provider.requests, 'post', fake_post)
    payload, failure = provider.invoke_research(
        {'run_id': 'run', 'research_targets': [], 'company_research_targets': []},
        {'targets': [], 'company_targets': []},
        [],
        'call',
        tmp_path,
        'developer rules',
    )
    assert failure is None
    assert payload['contract'] == 'ALPHA_HUNTER_V3_AUTONOMOUS_RESEARCH'
    assert payload['provider'] == 'OPENAI_RESPONSES_API'
    assert payload['model'] == 'gpt-5.6-terra'
    assert captured['url'] == provider.RESPONSES_URL
    assert captured['request']['store'] is False
    assert captured['request']['reasoning']['effort'] == 'high'
    assert captured['headers']['Authorization'] == 'Bearer test-key'


def test_missing_openai_key_is_transport_failure(monkeypatch, tmp_path):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    payload, failure = provider.invoke_research(
        {'run_id': 'run'}, {}, [], 'call', tmp_path, 'rules'
    )
    assert payload is None
    assert failure == ('TRANSPORT_FAILED', 'OPENAI_API_KEY_MISSING')


def test_openai_http_failure_stays_transport_failure(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(
        provider.requests,
        'post',
        lambda *args, **kwargs: FakeResponse(status_code=429, text='rate limited'),
    )
    payload, failure = provider.invoke_research(
        {'run_id': 'run'}, {}, [], 'call', tmp_path, 'rules'
    )
    assert payload is None
    assert failure == ('TRANSPORT_FAILED', 'OPENAI_HTTP_429')


def test_invalid_model_json_is_schema_failure(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(
        provider.requests,
        'post',
        lambda *args, **kwargs: FakeResponse(payload={'id': 'resp_2', 'output_text': 'not-json'}),
    )
    payload, failure = provider.invoke_research(
        {'run_id': 'run'}, {}, [], 'call', tmp_path, 'rules'
    )
    assert payload is None
    assert failure[0] == 'SCHEMA_FAILED'
