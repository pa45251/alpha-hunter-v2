import json
import pytest
import runtime_input_guard as guard
from test_portfolio_risk import base_policy, triggered_board
from portfolio_risk import apply_portfolio_risk_gate

@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,True])
def test_invalid_private_risk_cannot_enter_runtime(monkeypatch,value):
    monkeypatch.setenv('ALPHA_HUNTER_RISK_POLICY_JSON',json.dumps(base_policy()))
    monkeypatch.setenv('ALPHA_HUNTER_PORTFOLIO_JSON',json.dumps({'gross_exposure_pct':value,'positions':[]}))
    with pytest.raises(ValueError,match='PRIVATE_RISK_INPUTS_NOT_READY'):
        guard.validate()

def test_frozen_nan_gross_reproduction_and_runtime_block(monkeypatch):
    monkeypatch.setenv('ALPHA_HUNTER_RISK_POLICY_JSON',json.dumps(base_policy()))
    monkeypatch.setenv('ALPHA_HUNTER_PORTFOLIO_JSON',json.dumps({'gross_exposure_pct':float('nan'),'positions':[]}))
    board,meta=apply_portfolio_risk_gate(triggered_board())
    assert meta['risk_inputs_valid'] and board.iloc[0]['portfolio_action']=='BUY_STOCK'
    with pytest.raises(ValueError):guard.validate()

def test_complete_numeric_risk_passes(monkeypatch):
    monkeypatch.setenv('ALPHA_HUNTER_RISK_POLICY_JSON',json.dumps(base_policy()))
    monkeypatch.setenv('ALPHA_HUNTER_PORTFOLIO_JSON',json.dumps({'gross_exposure_pct':50,'positions':[]}))
    guard.validate()

def test_missing_private_risk_blocks_before_entrypoint(monkeypatch):
    monkeypatch.setattr(guard,'load_risk_policy',lambda:{})
    monkeypatch.setattr(guard,'load_portfolio_state',lambda:{})
    monkeypatch.setattr(guard.sys,'argv',['runtime_input_guard.py','decision_run_v2'])
    called=[];monkeypatch.setattr(guard.runpy,'run_module',lambda *a,**k:called.append(1))
    with pytest.raises(ValueError):guard.main()
    assert called==[]
