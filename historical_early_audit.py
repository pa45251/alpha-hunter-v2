"""Audit first observable nominations from Git artifacts, never replay today's story.

A commit timestamp is a conservative public availability bound. Price-session dates
are NOT treated as publication timestamps. Later prices are used for outcomes only.
"""
from __future__ import annotations
import io
import json
import subprocess
from pathlib import Path
import pandas as pd
from opportunity_advisory import assess, validate_company_research

CASES = {'6179':'亞通','8227':'巨有科技','6538':'倉和','3055':'蔚華科','3624':'光頡','2305':'全友'}


def git(*args):
    return subprocess.check_output(['git', *args], text=True, stderr=subprocess.DEVNULL)


def read_at(commit, name, kind='json'):
    try:
        text = git('show', f'{commit}:output/{name}')
        return json.loads(text) if kind == 'json' else pd.read_csv(io.StringIO(text), dtype={'code':str,'taiwan_code':str})
    except (subprocess.CalledProcessError, ValueError):
        return {} if kind == 'json' else pd.DataFrame()


def history(snapshot, ticker):
    item = (snapshot.get('entry_histories') or {}).get(ticker)
    if not item:
        return None
    return pd.DataFrame(item['data'], columns=item['columns'], index=pd.to_datetime(item['index']))


def run(ref='01b7a9005df409c5ceec7c85cafabeab1292c36a', out=Path('docs/audit')):
    commits = git('log','--reverse','--format=%H %cI',ref,'--','output/taiwan_candidates.csv','output/reverse_transmission_candidates.csv').splitlines()
    latest = read_at(ref, 'market_snapshot.json')
    first={}; observations=[]; seen=set()
    for item in commits:
        sha, available = item.split(' ',1)
        candidates = read_at(sha, 'taiwan_candidates.csv','csv')
        reverse = read_at(sha,'reverse_transmission_candidates.csv','csv')
        frames=[x for x in [candidates,reverse] if not x.empty and 'ticker' in x]
        if not frames:
            continue
        df=pd.concat(frames,ignore_index=True).drop_duplicates('ticker')
        df=df[df.ticker.astype(str).str.split('.').str[0].isin(CASES)]
        if df.empty:
            continue
        snapshot=read_at(sha,'market_snapshot.json'); risk=read_at(sha,'risk_regime.json')
        manifest=read_at(sha,'manifest.json'); research=read_at(sha,'research_result_v3.json')
        for r in df.to_dict('records'):
            code=r['ticker'].split('.')[0]; session=r.get('last_price_date')
            key=(code,session)
            # Preserve first public version per session; later revisions cannot backfill it.
            if key in seen:
                continue
            seen.add(key)
            h=history(snapshot,r['ticker'])
            if h is not None:
                cutoff=snapshot.get('canonical_closed_price_date')
                h=h[h.index <= pd.Timestamp(cutoff)] if cutoff else None
            evidence=None
            if research.get('research_run_id') == manifest.get('run_id') and research.get('status') == 'PASS':
                for e in research.get('company_opportunities',[]):
                    try:
                        validate_company_research(e,manifest.get('run_id'),{(r['ticker'],e.get('driver_id'))},available)
                        if e.get('ticker')==r['ticker']:
                            evidence=e;break
                    except ValueError:
                        continue
            if risk.get('source_run_id') != manifest.get('run_id'):
                risk={}
            a=assess(r,evidence,risk,h,available)
            row=dict(code=code,name=CASES[code],commit=sha,available_at=available,price_session=session,
                     reaction=r.get('reaction_state','UNRECORDED'),rs20=r.get('rs_20d_vs_bench'),
                     acceleration=r.get('acceleration'),volume_ratio=r.get('volume_ratio20'),
                     bias20=r.get('bias20'),ret5=r.get('ret_5d'),
                     company_evidence_at_time='PRESENT' if evidence else 'NOT_ARCHIVED: availability cannot be established',
                     international_at_time='PRESENT' if evidence and evidence.get('international_evidence') else 'NOT_ESTABLISHED',
                     hypothetical_action=a['action'], price_reason=a['price_reason'],
                     price_history_available=h is not None, price=r.get('price'),
                     status='REPLAYABLE' if evidence and h is not None else 'INSUFFICIENT_POINT_IN_TIME_EVIDENCE')
            # Outcome starts at first next tradable session AFTER publication, not the already closed signal price.
            future=history(latest,r['ticker'])
            row['outcome_basis']='NEXT_SESSION_OPEN_TO_NTH_SESSION_CLOSE; unadjusted indicative, not strategy P&L'
            if future is not None:
                publication=pd.Timestamp(available).tz_convert('Asia/Taipei')
                future=future[future.index.date > publication.date()] if publication.hour >= 9 else future[future.index.date >= publication.date()]
                for horizon in [1,3,5,10]:
                    row[f'outcome_{horizon}d']=float(future.Close.iloc[horizon-1]/future.Open.iloc[0]-1) if len(future)>=horizon and future.Open.iloc[0]>0 else None
            publication = pd.Timestamp(available).tz_convert('Asia/Taipei')
            session_ts = pd.to_datetime(session, errors='coerce')
            row['closed_session_at_publication'] = bool(pd.notna(session_ts) and (session_ts.date() < publication.date() or (session_ts.date() == publication.date() and (publication.hour, publication.minute) >= (13,30))))
            row['archived_global_driver_states'] = ';'.join(str(e.get('driver_id')) + ':' + str(e.get('state')) for e in research.get('results', [])) if research.get('research_run_id') == manifest.get('run_id') else 'MIXED_OR_MISSING'
            if not row['closed_session_at_publication']:
                row['status'] = 'OPEN_OR_UNDATED_BAR_NOT_A_CLOSED_SIGNAL'
                row['hypothetical_action'] = 'WAIT'
            observations.append(row)
            first.setdefault(code,row)
    out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(observations).to_csv(out/'early_detection_observations.csv',index=False)
    lines=['# Historical early detection audit','',f'Source main: `{ref}`. Rules fixed before audit; no six-stock tuning.',
           '', 'Commit availability controls decision time. Missing evidence stays missing; later news and prices never establish past causality.',
           '', '| Stock | First archived nomination (UTC) | Price session | Reaction | EARLY BUY / ADD |', '|---|---|---|---|---|']
    for code,name in CASES.items():
        r=first.get(code,{})
        lines.append(f"| {code} {name} | {r.get('available_at','NOT_FOUND')} | {r.get('price_session','UNKNOWN')} | {r.get('reaction','UNKNOWN')} | Not established from archived company evidence |")
    lines += ['', '| Stock | First extended nomination (UTC) | 1D | 3D | 5D | 10D |', '|---|---|---|---|---|---|']
    for code,name in CASES.items():
        rows=[r for r in observations if r['code']==code]
        extended=next((r for r in rows if pd.to_numeric(r.get('bias20'), errors='coerce') > .20 or pd.to_numeric(r.get('ret5'), errors='coerce') > .25),{})
        initial=first.get(code,{})
        returns=['UNAVAILABLE' if initial.get(f'outcome_{n}d') is None else f"{initial[f'outcome_{n}d']:.1%}" for n in [1,3,5,10]]
        lines.append(f"| {code} {name} | {extended.get('available_at','NOT_ESTABLISHED')} | " + ' | '.join(returns) + ' |')
    lines += ['', 'No defensible claim of 1–3-session early tradability can be made from these archives. Scanner nomination and executable economic evidence are different events.',
              'Per-session metrics, extension state, missing-evidence flags, commit IDs and 1/3/5/10-session outcomes are in early_detection_observations.csv.',
              'Outcomes unavailable at the latest snapshot remain blank (right-censored). Indicative raw-price outcomes may include corporate-action effects and exclude costs, slippage and limit-up fill risk.',
              'Prospective validation: retain immutable Git publication time, snapshot, company evidence, policy version and all candidate actions. Evaluate future unseen candidates after 1/3/5/10 sessions; do not tune rules to these six winners. Include all nominations, rejected names, missed names and a holdout period. No calibrated expected value or success rate is claimed.', '']
    (out/'early_detection_audit.md').write_text('\n'.join(lines))
    print(json.dumps({'observations':len(observations),'first':{k:{x:v.get(x) for x in ['available_at','price_session','reaction']} for k,v in first.items()}},ensure_ascii=False))

if __name__=='__main__':
    run()
