"""Read-only live acceptance of production workflow steps, in an isolated checkout copy.

Run only in trusted same-repository GitHub Actions with the workflow's usual secrets.
This runner never executes Git commit/push steps and never uploads private files or raw logs.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import yaml

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'live_runtime_acceptance.json'


def run():
    phases=[]
    result={'mode':'LIVE_EXTERNAL_PROVIDERS','remote_publication_performed':False,
            'private_artifacts_uploaded':False,'source_commit':os.getenv('GITHUB_SHA'),
            'production_branch_identity_simulated_in_isolation':True,'status':'FAILED','phases':phases}
    if os.getenv('GITHUB_ACTIONS')!='true':
        result['blocker']='TRUSTED_ACTIONS_ENVIRONMENT_REQUIRED';REPORT.write_text(json.dumps(result,indent=2));return 1
    required=['COPILOT_GITHUB_TOKEN','ALPHA_HUNTER_RISK_POLICY_JSON','ALPHA_HUNTER_PORTFOLIO_JSON']
    if any(not os.getenv(n) for n in required):
        result['blocker']='REQUIRED_PRODUCTION_CREDENTIAL_OR_PRIVATE_INPUT_MISSING';REPORT.write_text(json.dumps(result,indent=2));return 1
    with tempfile.TemporaryDirectory(prefix='alpha-live-acceptance-') as td:
        work=Path(td)/'repo'
        shutil.copytree(ROOT,work,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache'))
        env=os.environ.copy();env['PYTHONPATH']=str(work)
        # Test the post-merge runtime contract in an isolated, non-publishing directory.
        # The report retains the actual PR source SHA; no artifact can be published as main.
        env['GITHUB_REF_NAME']='main'
        outputs={};outcomes={}
        def command(name,cmd,ident=None,allow_failure=False):
            output_file=Path(td)/'step-output';output_file.write_text('');env['GITHUB_OUTPUT']=str(output_file)
            start=time.monotonic()
            try:
                # Raw logs can contain private provider output: retain only in this ephemeral directory.
                with (Path(td)/'step.log').open('w') as log:
                    p=subprocess.run(['bash','-e','-o','pipefail','-c',cmd],cwd=work,env=env,
                                     stdout=log,stderr=subprocess.STDOUT,timeout=900)
                code=p.returncode
            except subprocess.TimeoutExpired:code=124
            elapsed=round(time.monotonic()-start,1)
            phases.append({'name':name,'exit_code':code,'duration_seconds':elapsed})
            print(f'{name}: exit={code} seconds={elapsed}',flush=True)
            if ident:
                outputs[ident]=dict(line.split('=',1) for line in output_file.read_text().splitlines() if '=' in line)
                outcomes[ident]='success' if code==0 else 'failure'
            if code and not allow_failure:
                if name in {'daily_scan','canonical_price_inputs','research_handoff'}:
                    # These phases consume only public market data, never private handoffs.
                    result['public_data_diagnostic']=(Path(td)/'step.log').read_text()[-4000:]
                raise RuntimeError(name)
        try:
            for mod in ['daily_scan','canonical_price_inputs','research_handoff']:
                command(mod,'python '+mod+'.py')
            workflow=yaml.safe_load((work/'.github/workflows/autonomous_research_v3.yml').read_text())
            steps=workflow['jobs']['research']['steps'];active=False
            for step in steps:
                name=step['name']
                if name=='Build compact opportunity-research handoff':active=True
                if name=='Commit validated public research and guarded V2 decision artifacts':break
                if not active:continue
                condition=step.get('if','')
                if condition:
                    if condition=="steps.maintenance_handoff.outputs.target_count != '0'":
                        if outputs.get('maintenance_handoff',{}).get('target_count')=='0':continue
                    elif condition=="steps.quality_first.outcome == 'failure'":
                        if outcomes.get('quality_first')!='failure':continue
                    else:raise RuntimeError('UNSUPPORTED_WORKFLOW_CONDITION')
                command(name,step['run'],step.get('id'),bool(step.get('continue-on-error')))
            board=yaml.safe_load((work/'.github/workflows/action_board_publish.yml').read_text())
            active=False
            for step in board['jobs']['publish']['steps']:
                name=step['name']
                if name=='Verify current canonical publication inputs':active=True
                if name=='Commit advisory, trace and action board':break
                if active:command(name,step['run'])
            command('Read-time freshness and integrity acceptance','python publication_guard.py check')
            result['status']='PASS'
        except Exception as exc:
            result['blocker']=str(exc)
        finally:
            # Unvalidated model and private maintenance artifacts are never uploaded.
            for name in ['portfolio_maintenance_handoff.json','portfolio_maintenance_result.raw.txt',
                         'portfolio_maintenance_result.json','alpha_hunter_private_position_actions.json']:
                (Path('/tmp')/name).unlink(missing_ok=True)
            REPORT.write_text(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(run())
