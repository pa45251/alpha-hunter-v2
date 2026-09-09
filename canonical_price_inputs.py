"""Capture public risk/entry price inputs into the scanner's hash-bound snapshot.

Frozen algorithms consume the same raw frames via the runtime entrypoint adapter.
No policy, score or trigger threshold is changed.
"""
import hashlib
import json
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf
from market_sessions import clip_closed_bars, latest_closed_session

NAME='canonical_price_inputs.json'
CONTRACT='ALPHA_HUNTER_CANONICAL_PRICE_INPUTS_1'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def capture(out=Path('output')):
    from risk_regime import RISK_TICKERS, CORE_TICKERS
    from canonical_gate import run_gate
    out=Path(out);m=json.loads((out/'manifest.json').read_text())
    board=pd.read_csv(out/'structural_matches.csv')
    tickers=sorted(set(board.ticker.dropna().astype(str)) | set(RISK_TICKERS))
    raw=yf.download(tickers,period='2y',auto_adjust=False,group_by='ticker',progress=False,threads=True)
    frames={};unavailable=[]
    for ticker in tickers:
        try:
            h=raw[ticker] if isinstance(raw.columns,pd.MultiIndex) and ticker in raw.columns.get_level_values(0) else raw
            h=clip_closed_bars(h,ticker,m['generated_at_utc'])
            if h.empty or pd.Timestamp(h.index[-1]).date().isoformat()!=latest_closed_session(ticker,m['generated_at_utc']):
                raise ValueError('STALE')
            if 'Close' not in h or not np.isfinite(float(h['Close'].iloc[-1])) or float(h['Close'].iloc[-1])<=0:
                raise ValueError('LATEST_CLOSE_MISSING')
            # JSON nulls preserve missing data; never impute a valid quote or turn missing into zero.
            h=h.tail(500)
            frames[ticker]={'dates':[pd.Timestamp(d).isoformat() for d in h.index],
                            'columns':list(h.columns),'data':h.replace({np.nan:None,np.inf:None,-np.inf:None}).values.tolist()}
        except (KeyError,ValueError,TypeError):unavailable.append(ticker)
    if set(CORE_TICKERS)-set(frames):raise RuntimeError('CANONICAL_RISK_CORE_UNAVAILABLE')
    payload={'contract':CONTRACT,'source_run_id':m['run_id'],'snapshot_as_of_utc':m['generated_at_utc'],
             'histories':frames,'unavailable_tickers':unavailable}
    path=out/NAME;path.write_text(json.dumps(payload,allow_nan=False,separators=(',',':')))
    entry={'name':NAME,'relative_path':'output/'+NAME,'raw_url':f'https://raw.githubusercontent.com/pa45251/alpha-hunter-v2/main/output/{NAME}',
           'sha256':sha(path),'bytes':path.stat().st_size}
    m['authoritative_files']=[x for x in m['authoritative_files'] if x['name']!=NAME]+[entry]
    (out/'manifest.json').write_text(json.dumps(m,indent=2,ensure_ascii=False))
    gate=run_gate(out)
    if gate['gate_status']!='PASS':raise RuntimeError('CANONICAL_PRICE_GATE_FAILED')
    return payload

def load(out=Path('output')):
    out=Path(out);m=json.loads((out/'manifest.json').read_text());p=out/NAME
    entries=[x for x in m.get('authoritative_files',[]) if x.get('name')==NAME]
    if len(entries)!=1 or entries[0].get('sha256')!=sha(p):raise RuntimeError('CANONICAL_PRICE_HASH_MISMATCH')
    payload=json.loads(p.read_text())
    if payload.get('contract')!=CONTRACT or payload.get('source_run_id')!=m.get('run_id'):
        raise RuntimeError('CANONICAL_PRICE_RUN_MISMATCH')
    result={}
    for t,row in payload['histories'].items():
        h=pd.DataFrame(row['data'],columns=row['columns'],index=pd.to_datetime(row['dates']))
        result[t]=h
    return result

if __name__=='__main__':
    p=capture();print(f"Canonical public prices captured: {len(p['histories'])} instruments")
