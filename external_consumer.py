"""Public, read-only consumer: pin one main commit and independently verify every byte."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import requests
import publication_guard as pg
from canonical_gate import REQUIRED_AUTHORITATIVE_FILES

CONTRACT='ALPHA_HUNTER_EXTERNAL_CONSUMER_1'
ROLES=('decision_packet.json','action_board.md','entry_plans_v2.json','portfolio_allocation_v2.json')

def lineage(out):
    rid=pg.read(out,'manifest.json')['run_id']
    plans=pg.read(out,'entry_plans_v2.json')['all_plans']
    identities=[{k:p.get(k) for k in ('ticker','driver_id','entry_style','trigger_price','buy_zone_low','buy_zone_high','invalidation_price')} for p in plans]
    identities.sort(key=lambda p:(str(p['ticker']),str(p['driver_id'])))
    return {'contract':CONTRACT,'source_run_id':rid,
            'manifest_sha256':pg.digest(out/'manifest.json'),
            'artifacts':{n:{'source_run_id':rid,'sha256':pg.digest(out/n)} for n in ROLES},
            'selected_entry_identity_sha256':hashlib.sha256(json.dumps(identities,sort_keys=True,allow_nan=False).encode()).hexdigest()}

def validate(out,now=None):
    out=Path(out)
    try:
        status=pg.readiness(out,now)
        pg.require(status['status']=='READY_CURRENT_SNAPSHOT','PUBLICATION_NOT_CURRENT')
        m=pg.read(out,'manifest.json');rid=m['run_id']
        entries=m.get('authoritative_files',[])
        names=[e['name'] for e in entries]
        pg.require(len(names)==len(set(names)) and REQUIRED_AUTHORITATIVE_FILES.issubset(names),'CANONICAL_HASH_SET_INCOMPLETE')
        pg.require(all(Path(n).name==n for n in names),'INVALID_PATH')
        pg.require(all(pg.digest(out/e['name'])==e['sha256'] for e in entries),'CANONICAL_HASH_MISMATCH')
        pg.check_plan_links(out)
        pg.require(f'- Run: `{rid}`' in (out/'action_board.md').read_text(),'ACTION_BOARD_RUN_MISMATCH')
        for name in ('entry_plans_v2.json','portfolio_allocation_v2.json'):
            data=pg.read(out,name)
            for key in ('source_run_id','run_id'):
                if key in data:pg.require(data[key]==rid,'DOWNSTREAM_RUN_MISMATCH')
        pg.require(pg.read(out,pg.SEAL).get('external_lineage')==lineage(out),'EXTERNAL_LINEAGE_MISMATCH')
        return {'contract':CONTRACT,**status,'checked_at_utc':pg.clock(now).isoformat(),
                'taipei_date':str(pg.clock(now).tz_convert('Asia/Taipei').date()),
                'taiwan_closed_session':m['taiwan']['latest_price_date'],
                'risk_session':pg.read(out,'risk_regime.json')['risk_snapshot_date']}
    except Exception:
        # Never return stale advisory content or exception text from external inputs.
        return {'contract':CONTRACT,'status':'NOT_READY','reason':'PUBLICATION_VALIDATION_FAILED','auto_trade_allowed':False}

def fetch_public(repository='pa45251/alpha-hunter-v2',now=None,get=requests.get):
    def read_url(url):
        r=get(url,timeout=30,headers={'Cache-Control':'no-cache'});r.raise_for_status();return r.content
    def head():
        return json.loads(read_url(f'https://api.github.com/repos/{repository}/commits/main'))['sha']
    try:
        sha=head()
        if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('INVALID_SHA')
        base=f'https://raw.githubusercontent.com/{repository}/{sha}/output/'
        seal_bytes=read_url(base+pg.SEAL);seal=json.loads(seal_bytes)
        with tempfile.TemporaryDirectory(prefix='alpha-external-consumer-') as td:
            out=Path(td);(out/pg.SEAL).write_bytes(seal_bytes)
            for name in seal['hashes']:
                if Path(name).name!=name or name in ('','.', '..'):raise ValueError('INVALID_PATH')
                (out/name).write_bytes(read_url(base+name))
            result=validate(out,now)
        if head()!=sha:raise ValueError('MAIN_ADVANCED_DURING_READ')
        result['repository_commit']=sha
        return result
    except Exception:
        return {'contract':CONTRACT,'status':'NOT_READY','reason':'PUBLIC_FETCH_OR_COHERENCE_FAILED','auto_trade_allowed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--repository',default='pa45251/alpha-hunter-v2');a=p.parse_args()
    result=validate(a.output) if a.output else fetch_public(a.repository)
    print(json.dumps(result));return 0 if result['status']=='READY_CURRENT_SNAPSHOT' else 1

if __name__=='__main__':raise SystemExit(main())
