"""Maintained S&P 500 membership -> isolated research-WHY cluster sensor.

Membership updates never edit Core Sensors, taxonomy, exposure edges or activations.
The checked-in snapshot is generated, not a hand-maintained permanent ticker list.
"""
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import json
import hashlib

import pandas as pd
import requests

SOURCE = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'
COLUMNS = ['ticker', 'name', 'industry_cluster', 'region', 'universe_layer']
QUEUE_COLUMNS = ['industry_cluster', 'member_count', 'positive_rs20_pct', 'median_rs20',
                 'witnesses', 'activation_state', 'decision_eligible', 'price_cannot_activate_driver',
                 'research_question']


def refresh_membership(path):
    response = requests.get(SOURCE, timeout=15)
    response.raise_for_status()
    raw = pd.read_csv(StringIO(response.text))
    if not {'Symbol', 'Security', 'GICS Sub-Industry'}.issubset(raw):
        # The DataHub source exposes Name and Sector in some schema versions.
        if not {'Symbol', 'Name', 'Sector'}.issubset(raw):
            raise ValueError('DISCOVERY_SOURCE_SCHEMA_CHANGED')
        raw = raw.rename(columns={'Name':'Security', 'Sector':'GICS Sub-Industry'})
    frame = pd.DataFrame({
        'ticker': raw['Symbol'].astype(str).str.replace('.', '-', regex=False),
        'name': raw['Security'], 'industry_cluster': raw['GICS Sub-Industry'],
        'region':'US', 'universe_layer':'DISCOVERY',
        'issuer_id': raw['CIK'].astype(str) if 'CIK' in raw else raw['Security'],
    })
    if not 400 <= len(frame) <= 600 or frame.ticker.duplicated().any() or frame.isna().any().any():
        raise ValueError('DISCOVERY_MEMBERSHIP_INVALID')
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    body = frame.to_csv(index=False)
    meta = {'source':SOURCE, 'fetched_at_utc':datetime.now(timezone.utc).isoformat(),
            'member_count':len(frame), 'sha256':hashlib.sha256(body.encode()).hexdigest()}
    temp = path.with_suffix('.tmp'); temp.write_text(body); temp.replace(path)
    path.with_suffix('.json').write_text(json.dumps(meta, indent=2))
    return frame


def load_discovery(path, core_tickers, *, refresh=True, max_age_days=30):
    empty = pd.DataFrame(columns=COLUMNS)
    if not path:
        return empty, {'status':'DISABLED', 'member_count':0, 'discovery_count':0}
    path = Path(path)
    def cached():
        meta = json.loads(path.with_suffix('.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta['sha256']:
            raise ValueError('DISCOVERY_CACHE_HASH_MISMATCH')
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(meta['fetched_at_utc'])).total_seconds()/86400
        frame = pd.read_csv(path)
        if not set(COLUMNS).issubset(frame) or not frame.universe_layer.eq('DISCOVERY').all():
            raise ValueError('DISCOVERY_CACHE_SCHEMA_INVALID')
        if age < -1 or age > 90:
            raise ValueError('DISCOVERY_CACHE_EXPIRED')
        return frame, meta, age
    error = ''
    try:
        frame, meta, age = cached()
    except Exception:
        frame, meta, age = empty, {}, float('inf')
    if age > max_age_days and refresh:
        try:
            refresh_membership(path)
            frame, meta, age = cached()
        except Exception as exc:
            error = type(exc).__name__ + ':' + str(exc)[:160]
    if frame.empty:
        return empty, {'status':'UNAVAILABLE', 'error':error, 'member_count':0, 'discovery_count':0}
    frame = frame.loc[~frame.ticker.isin(set(core_tickers))].copy()
    return frame, {**meta, 'status':'STALE_CACHE' if age > max_age_days else 'READY',
                   'age_days':round(age,2), 'error':error, 'discovery_count':len(frame)}


def research_clusters(stocks, universe=None):
    rows = []
    if stocks.empty:
        return pd.DataFrame(columns=QUEUE_COLUMNS)
    for cluster, members in stocks.groupby('industry_cluster'):
        if 'issuer_id' in members:
            members = members.sort_values('ticker').drop_duplicates('issuer_id')
        expected = len(members)
        if universe is not None and not universe.empty:
            configured = universe[universe.industry_cluster.eq(cluster)]
            expected = configured.issuer_id.nunique() if 'issuer_id' in configured else configured.ticker.nunique()
        # Missing members cannot turn a small surviving subset into broad confirmation.
        if len(members) / max(1, expected) < .8:
            continue
        # Multi-week relative strength + MA participation, not one-day gainers.
        strong = members[(members.rs_20d_vs_bench > 0) & (members.rs_60d_vs_bench > 0)
                         & (members.price > members.ma20) & (members.price > members.ma60)]
        if len(strong) < 3 or len(strong)/len(members) < .5:
            continue
        rows.append({
            'industry_cluster':cluster, 'member_count':len(members),
            'positive_rs20_pct':float((members.rs_20d_vs_bench > 0).mean()),
            'median_rs20':float(members.rs_20d_vs_bench.median()),
            'witnesses':';'.join(strong.sort_values('rs_20d_vs_bench',ascending=False).ticker.head(10)),
            'activation_state':'RESEARCH_WHY_REQUIRED', 'decision_eligible':False,
            'price_cannot_activate_driver':True,
            'research_question':'Identify shared economic cause versus company events; verify independent earnings/ASP/orders/margin evidence, counter-evidence and exact Taiwan transmission. Promotion requires reviewed Core and causal-graph changes.',
        })
    return pd.DataFrame(rows, columns=QUEUE_COLUMNS).sort_values('median_rs20',ascending=False)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='config/discovery_universe.csv')
    args = parser.parse_args()
    print('Refreshed discovery members:', len(refresh_membership(args.output)))
