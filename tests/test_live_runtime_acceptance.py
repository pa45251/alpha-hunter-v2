import json
from pathlib import Path
from types import SimpleNamespace
import scripts.live_runtime_acceptance as live


def test_live_acceptance_never_claims_pass_without_credentials(tmp_path,monkeypatch):
    monkeypatch.setattr(live,'REPORT',tmp_path/'result.json')
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    monkeypatch.delenv('COPILOT_GITHUB_TOKEN',raising=False)
    assert live.run()==1
    report=json.loads(live.REPORT.read_text())
    assert report['status']=='FAILED' and not report['phases']


def test_live_runner_stops_on_failed_scan_without_running_research_or_publish(tmp_path,monkeypatch):
    monkeypatch.setattr(live,'REPORT',tmp_path/'result.json')
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    for name in ['COPILOT_GITHUB_TOKEN','ALPHA_HUNTER_RISK_POLICY_JSON','ALPHA_HUNTER_PORTFOLIO_JSON']:
        monkeypatch.setenv(name,'SYNTHETIC_PRIVATE_SENTINEL')
    calls=[]
    def fail(args,**kwargs):calls.append(args);return SimpleNamespace(returncode=2)
    monkeypatch.setattr(live.subprocess,'run',fail)
    assert live.run()==1 and len(calls)==1
    report=live.REPORT.read_text()
    assert 'SYNTHETIC_PRIVATE_SENTINEL' not in report
    assert json.loads(report)['blocker']=='daily_scan'
    assert 'git push' not in str(calls)


def test_seal_failure_exposes_only_guard_code(tmp_path,monkeypatch):
    monkeypatch.setattr(live,'REPORT',tmp_path/'result.json')
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    for name in ['COPILOT_GITHUB_TOKEN','ALPHA_HUNTER_RISK_POLICY_JSON','ALPHA_HUNTER_PORTFOLIO_JSON']:
        monkeypatch.setenv(name,'SYNTHETIC_PRIVATE_SENTINEL')
    def execute(args,**kwargs):
        if 'publication_guard.py seal' in args[-1]:
            kwargs['stdout'].write('private details SYNTHETIC_PRIVATE_SENTINEL\nValueError: DUPLICATE_SESSION_TRACE\n')
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(live.subprocess,'run',execute)
    assert live.run()==1
    report=live.REPORT.read_text()
    assert 'SYNTHETIC_PRIVATE_SENTINEL' not in report
    assert json.loads(report)['publication_guard_code']=='DUPLICATE_SESSION_TRACE'


def test_standalone_runner_resolves_diagnostic_without_pythonpath(tmp_path):
    import subprocess,sys
    script=Path(live.__file__).resolve()
    p=subprocess.run([sys.executable,'-I','-c',
        'import runpy,sys; runpy.run_path(sys.argv[1],run_name="import_probe"); assert "research_runtime_diagnostic" in sys.modules',str(script)],
        cwd=tmp_path,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
