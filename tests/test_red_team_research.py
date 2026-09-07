"""Adversarial regressions: persisted PASS is not authorization."""
import json
import math
import pytest
import research_activation_bridge_v3 as bridge
import research_decision_source_gate_v3 as source
from test_research_activation_bridge_v3 import _write_fixture, _patch_paths

@pytest.mark.parametrize('confidence', [float('nan'), float('inf'), -float('inf'), True])
def test_bridge_rejects_nonfinite_or_boolean_confidence(tmp_path, monkeypatch, confidence):
    out = _write_fixture(tmp_path)
    _patch_paths(monkeypatch, out)
    p = out / 'research_result_v3.json'
    research = json.loads(p.read_text())
    research['results'][0]['confidence'] = confidence
    p.write_text(json.dumps(research))
    with pytest.raises(RuntimeError, match='confidence'):
        bridge.main()
    assert not (out / 'driver_activation_v3.csv').exists()

@pytest.mark.parametrize('mutation', ['old_run', 'missing_manifest', 'row_run'])
def test_source_gate_rejects_stale_pass(tmp_path, monkeypatch, mutation):
    out = _write_fixture(tmp_path)
    monkeypatch.setattr(source, 'OUT', out)
    p = out / 'research_result_v3.json'
    research = json.loads(p.read_text())
    if mutation == 'old_run':
        research['research_run_id'] = 'yesterday'
    elif mutation == 'row_run':
        research['results'][0]['research_run_id'] = 'yesterday'
    else:
        (out / 'manifest.json').unlink()
    p.write_text(json.dumps(research))
    with pytest.raises(SystemExit):
        source.main()

from test_research_contract_v3 import research as research_fixture
from research_contract_v3 import validate_research_result, ResearchContractError

def test_future_publication_cannot_support_research():
    r=research_fixture()
    r['supporting_evidence'][0]['published_at']='2099-01-01T00:00:00Z'
    with pytest.raises(ResearchContractError,match='future'):
        validate_research_result(r,{'AI_SERVER_SHIPMENTS'})
