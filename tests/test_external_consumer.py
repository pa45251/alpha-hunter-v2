import json
from types import SimpleNamespace
import pytest
import publication_guard as pg
import external_consumer as ec
from test_publication_guard import fixture,dump,NOW


def ready(out):
    fixture(out)
    for name in ec.REQUIRED_AUTHORITATIVE_FILES:
        if not (out/name).exists():(out/name).write_text('PUBLIC_FIXTURE')
    m=pg.read(out,'manifest.json')
    m['authoritative_files']=[{'name':n,'sha256':pg.digest(out/n)} for n in sorted(ec.REQUIRED_AUTHORITATIVE_FILES)]
    dump(out,'manifest.json',m)
    p=pg.read(out,'decision_packet.json');p['snapshot_lineage_layer']['manifest_sha256']=pg.digest(out/'manifest.json');dump(out,'decision_packet.json',p)
    context=out/'context.json'
    dump(out,'context.json',{'run_id':'R','started_at':'2026-09-07T00:10:00Z','inputs':{n:pg.digest(out/n) for n in pg.INPUTS},'old_trace':None})
    pg.seal(out,context,NOW)


def transport(out):
    calls=[]
    def get(url,**kwargs):
        calls.append(url)
        content=json.dumps({'sha':'a'*40}).encode() if url.endswith('/commits/main') else (out/url.rsplit('/',1)[1]).read_bytes()
        return SimpleNamespace(content=content,raise_for_status=lambda:None)
    return get,calls

@pytest.mark.parametrize('case',['today_complete','scanner_only','old_board','decision_run','entry_run','rotation_run','seal_hash','all_current'])
def test_consumer_public_transport_cases(tmp_path,case):
    ready(tmp_path)
    if case=='scanner_only':
        m=pg.read(tmp_path,'manifest.json');m['run_id']='NEW_SCAN';dump(tmp_path,'manifest.json',m)
    elif case=='old_board':(tmp_path/'action_board.md').write_text('- Run: `YESTERDAY`')
    elif case in ('decision_run','entry_run','rotation_run'):
        name={'decision_run':'decision_packet.json','entry_run':'entry_plans_v2.json','rotation_run':'portfolio_allocation_v2.json'}[case]
        p=pg.read(tmp_path,name);p['run_id' if case=='decision_run' else 'source_run_id']='OTHER';dump(tmp_path,name,p)
    elif case=='seal_hash':
        p=pg.read(tmp_path,pg.SEAL);p['hashes']['action_board.md']='0'*64;dump(tmp_path,pg.SEAL,p)
    get,calls=transport(tmp_path)
    result=ec.fetch_public(now=NOW,get=get)
    assert result['status']==('READY_CURRENT_SNAPSHOT' if case in ('today_complete','all_current') else 'NOT_READY')
    assert all('/'+'a'*40+'/output/' in u for u in calls if '/output/' in u)
    assert not result['auto_trade_allowed']


def test_rotation_wrong_run_even_with_recomputed_seal_hash(tmp_path):
    ready(tmp_path)
    p=pg.read(tmp_path,'portfolio_allocation_v2.json');p['source_run_id']='OTHER';dump(tmp_path,'portfolio_allocation_v2.json',p)
    s=pg.read(tmp_path,pg.SEAL);s['hashes']['portfolio_allocation_v2.json']=pg.digest(tmp_path/'portfolio_allocation_v2.json');s['external_lineage']=ec.lineage(tmp_path);dump(tmp_path,pg.SEAL,s)
    assert ec.validate(tmp_path,NOW)['status']=='NOT_READY'


def test_yesterday_never_used(tmp_path):
    ready(tmp_path)
    assert ec.fetch_public(now='2026-09-08T00:40:00Z',get=transport(tmp_path)[0])['status']=='NOT_READY'


def test_main_advances_during_download(tmp_path):
    ready(tmp_path);get,calls=transport(tmp_path)
    def race(url,**kwargs):
        response=get(url,**kwargs)
        if url.endswith('/commits/main') and len(calls)>1:response.content=json.dumps({'sha':'b'*40}).encode()
        return response
    assert ec.fetch_public(now=NOW,get=race)['status']=='NOT_READY'


def test_public_lineage_contains_only_identities_and_hashes(tmp_path):
    ready(tmp_path)
    s=pg.read(tmp_path,pg.SEAL)['external_lineage']
    text=json.dumps(s)
    assert '2317' not in text and 'AI_SERVER' not in text and 'weight_pct' not in text
