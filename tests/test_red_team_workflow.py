from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]

def test_daily_research_reaches_action_board():
    w = yaml.safe_load((ROOT / '.github/workflows/action_board_publish.yml').read_text())
    events = w.get('on', w.get(True))
    assert 'Alpha Hunter v3 Autonomous Research' in events['workflow_run']['workflows']

def test_publish_never_rebases_computed_artifacts():
    for p in (ROOT / '.github/workflows').glob('*.yml'):
        assert 'git rebase origin/main' not in p.read_text(), p.name

def test_fast_forward_push_rejects_concurrent_snapshot(tmp_path):
    def git(*args, cwd=tmp_path):
        return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    assert git('init','--bare','remote.git').returncode == 0
    for name in ['scanner','publisher']:
        assert git('clone',str(tmp_path/'remote.git'),name).returncode == 0
        for key,value in [('user.name','fixture'),('user.email','fixture@example.invalid')]:
            assert git('config',key,value,cwd=tmp_path/name).returncode == 0
    a,b=tmp_path/'scanner',tmp_path/'publisher'
    (a/'manifest').write_text('A')
    git('add','.',cwd=a); git('commit','-m','A',cwd=a); git('push','origin','HEAD:main',cwd=a)
    git('fetch','origin','main',cwd=b); git('checkout','-b','main','origin/main',cwd=b)
    (b/'board').write_text('computed from A')
    git('add','.',cwd=b);git('commit','-m','board A',cwd=b)
    (a/'manifest').write_text('B')
    git('add','.',cwd=a);git('commit','-m','B',cwd=a);git('push','origin','HEAD:main',cwd=a)
    assert git('push','origin','HEAD:main',cwd=b).returncode != 0
    # Original workflow cleanly rebases disjoint output files: stale board now looks latest.
    git('fetch','origin','main',cwd=b)
    assert git('rebase','origin/main',cwd=b).returncode == 0
    assert (b/'manifest').read_text() == 'B' and (b/'board').read_text() == 'computed from A'
