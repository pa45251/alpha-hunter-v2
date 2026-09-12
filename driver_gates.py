"""Ordered thesis gates. Scanner price evidence is never supplied by research.

Reuse global_alignment's existing breadth/trend limits; no new ranking score.
Missing or thin data is UNKNOWN, never negative evidence or local permission.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from global_alignment import DRIVER_THEME_MAP, _breadth_score

UNMAPPED = 'UNMAPPED_OPPORTUNITY'
PRICE_ACCEPTED = {'DEVELOPING', 'CONFIRMED'}
PRICE_REJECTED = {'WEAK', 'WEAKENING', 'REJECTED'}


def sealed_csv(name, out):
    manifest = json.loads((out / 'manifest.json').read_text())
    path = out / name
    entries = [r for r in manifest.get('authoritative_files', []) if r.get('name') == name]
    if (manifest.get('status') != 'PASS' or len(entries) != 1 or not path.exists()
            or hashlib.sha256(path.read_bytes()).hexdigest() != entries[0].get('sha256')):
        raise RuntimeError('THESIS_PRICE_LINEAGE_INVALID:' + name)
    frame = pd.read_csv(path)
    if 'run_id' in frame and not frame.run_id.astype(str).eq(manifest['run_id']).all():
        raise RuntimeError('THESIS_PRICE_RUN_MISMATCH:' + name)
    return frame


def international_price(theme, breadth, peers):
    result = {'international_price_state': 'UNKNOWN', 'international_price_reason': 'Missing exact-theme price evidence'}
    if not theme or breadth.empty or peers.empty:
        return result
    b = breadth[breadth.theme.eq(theme)]
    p = peers[peers.theme.eq(theme)]
    if 'universe_layer' in p:
        p = p[p.universe_layer.eq('CORE')]
    if len(b) != 1 or p.empty:
        return result
    b = b.iloc[0]
    required = ['above_ma20_pct', 'above_ma60_pct', 'positive_rs20_pct', 'positive_rs5_pct',
                'near_20d_high_pct', 'near_52w_high_pct', 'median_rs20']
    if b.get('breadth_confidence') not in {'MEDIUM', 'HIGH'} or pd.to_numeric(b[required], errors='coerce').isna().any():
        result['international_price_reason'] = 'Insufficient breadth coverage'
        return result
    trend, width = _breadth_score(b)
    states = p.get('raw_leader_state', pd.Series(dtype=str)).dropna()
    rs = {k: pd.to_numeric(p.get(k, pd.Series(dtype=float)), errors='coerce').median()
          for k in ['rs_5d_vs_bench', 'rs_20d_vs_bench', 'rs_60d_vs_bench', 'acceleration']}
    # The same not-supportive limits already used by the alignment layer now veto entry.
    rejected = trend < .45 or width < .40 or (len(states) == len(p) and states.isin(['WEAKENING', 'BROKEN', 'REJECTED']).all())
    complete = all(pd.notna(v) for v in rs.values()) and len(states) == len(p)
    confirmed = complete and all(v > 0 for v in rs.values()) and states.isin(['PERSISTENT', 'CONFIRMED']).any()
    result.update(international_price_state='REJECTED' if rejected else 'CONFIRMED' if confirmed else 'DEVELOPING' if complete else 'UNKNOWN',
                  international_price_reason=f'{theme}: trend={trend:.3f}; breadth={width:.3f}; leader_states={sorted(set(states))}',
                  international_price_metrics=rs)
    return result


def attach_price_gates(candidates, out=Path('output')):
    try:
        breadth = sealed_csv('theme_breadth.csv', out)
        peers = sealed_csv('market_snapshot.csv', out)
    except (RuntimeError, OSError, ValueError) as exc:
        return [dict(c, international_price_state='UNKNOWN', international_price_reason=str(exc)) for c in candidates]
    cache = {}
    for c in candidates:
        driver = c.get('driver_id')
        theme = c.get('global_theme') or DRIVER_THEME_MAP.get(driver)
        if theme not in cache:
            cache[theme] = international_price(theme, breadth, peers)
        c.update(cache[theme])
    return candidates


def local_proven(research, candidate, as_of):
    from opportunity_advisory import evidence_valid
    if (candidate.get('driver_id') != UNMAPPED or research.get('driver_id') != UNMAPPED
            or candidate.get('known_global_link') is True):
        return False
    proof = research.get('local_scope_evidence')
    if not isinstance(proof, dict):
        return False
    if (proof.get('event_type') not in {'CORPORATE_ACTION', 'REGULATORY_DECISION', 'TAIWAN_POLICY', 'COMPANY_SPECIFIC_CONTRACT'}
            or proof.get('global_industry_not_primary') is not True
            or not proof.get('global_alternative_test') or not proof.get('event_to_price_mechanism')):
        return False
    # Two distinct source-backed claims: the event and the exclusion of a global explanation.
    return all(evidence_valid(proof.get(key), as_of, ticker=research.get('ticker'))
               for key in ['event_evidence', 'global_alternative_evidence']) and (
        proof['event_evidence']['source_url'] != proof['global_alternative_evidence']['source_url'])


def thesis_gates(candidate, research, as_of):
    from opportunity_advisory import evidence_valid
    r = research or {}
    mapped = bool(candidate.get('driver_id')) and candidate.get('driver_id') != UNMAPPED
    local = r.get('scope') == 'LOCAL' and local_proven(r, candidate, as_of)
    scope = 'GLOBAL' if mapped else 'LOCAL' if local else 'UNKNOWN'
    price = candidate.get('international_price_state', 'UNKNOWN') if scope == 'GLOBAL' else 'NOT_REQUIRED' if local else 'UNKNOWN'
    company = [e for e in r.get('fundamental_evidence', [])
               if evidence_valid(e, as_of, ticker=candidate.get('ticker'), driver=candidate.get('driver_id') if mapped else None)]
    company_urls = {e.get('source_url') for e in r.get('fundamental_evidence', []) if isinstance(e, dict)}
    causal = [e for e in r.get('international_evidence', [])
              if evidence_valid(e, as_of, driver=candidate.get('driver_id')) and e.get('same_driver') is True
              and e.get('source_url') not in company_urls]
    state = r.get('driver_state', 'UNKNOWN')
    rejected = candidate.get('driver_rejected') is True or state == 'REJECTED' or r.get('major_counter_evidence') is True
    causal_state = 'REJECTED' if rejected else state if (causal or local) and state in PRICE_ACCEPTED else 'UNKNOWN'
    transmission = bool(company and r.get('company_transmission') and r.get('counter_evidence_reviewed') is True
                        and r.get('major_counter_evidence') is False and r.get('driver_id') == candidate.get('driver_id'))
    gap = ('GLOBAL_REJECTED' if rejected or (scope == 'GLOBAL' and price in PRICE_REJECTED)
           else 'DRIVER_UNKNOWN' if scope == 'UNKNOWN'
           else 'GLOBAL_PRICE_UNCONFIRMED' if scope == 'GLOBAL' and price not in PRICE_ACCEPTED
           else 'CAUSAL_UNVERIFIED' if causal_state not in PRICE_ACCEPTED
           else 'COMPANY_TRANSMISSION_UNVERIFIED' if not transmission else 'ENTRY')
    return dict(driver_scope=scope, international_price_state=price, international_causal_state=causal_state,
                company_transmission_state='CONFIRMED' if transmission else 'UNKNOWN', missing_gate=gap,
                research_task={'DRIVER_UNKNOWN':'IDENTIFY_DRIVER_AND_TEST_GLOBAL_ALTERNATIVE',
                               'GLOBAL_REJECTED':'NONE', 'GLOBAL_PRICE_UNCONFIRMED':'WAIT_FOR_MARKET_DATA',
                               'CAUSAL_UNVERIFIED':'INTERNATIONAL_CAUSAL',
                               'COMPANY_TRANSMISSION_UNVERIFIED':'COMPANY_TRANSMISSION', 'ENTRY':'NONE'}[gap])
