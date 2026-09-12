"""Small, source-backed advisory policy. Never changes Frozen V2 permissions.

Thresholds are uncalibrated risk limits, fixed before the six-case audit. Prices
nominate research; only timestamped non-price evidence can establish a thesis.
"""
from __future__ import annotations

import math
from urllib.parse import urlparse

import pandas as pd

from entry_structure_v2 import simple_atr, tw_stock_tick, _round_up_tick, _round_down_tick

VERSION = 'EARLY_OPPORTUNITY_1'
METRICS = {'REVENUE', 'EPS', 'BACKLOG', 'ASP', 'SHIPMENT', 'ORDER', 'CAPEX',
           'UTILIZATION', 'PROJECT_RECOGNITION', 'FREIGHT_RATE', 'POWER_DEMAND', 'PRODUCTION'}
ACTIONS = {'BUY', 'EARLY BUY', 'WAIT', 'PASS'}


def number(value, default=float('nan')):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default


def timestamp(value):
    return pd.to_datetime(value, utc=True, errors='coerce')


def evidence_valid(item, as_of, ticker=None, driver=None):
    if not isinstance(item, dict) or item.get('metric') not in METRICS:
        return False
    published = timestamp(item.get('published_at'))
    observed = timestamp(item.get('available_at'))
    cutoff = timestamp(as_of)
    if any(pd.isna(x) for x in [published, observed, cutoff]):
        return False
    if not (published <= observed <= cutoff and (cutoff - published).days <= 120):
        return False
    if not item.get('claim') or not item.get('source_title'):
        return False
    url = urlparse(str(item.get('source_url', '')))
    if url.scheme not in {'https', 'http'} or not url.netloc:
        return False
    if ticker and item.get('ticker') != ticker:
        return False
    if driver and item.get('driver_id') != driver:
        return False
    return item.get('direction') == 'SUPPORTS'


def validate_company_research(row, run_id, targets, as_of):
    """Reject malformed/unscoped research, including generic peer substitutions."""
    if not isinstance(row, dict) or row.get('research_run_id') != run_id:
        raise ValueError('COMPANY_RESEARCH_RUN_MISMATCH')
    key = (row.get('ticker'), row.get('driver_id'))
    if key not in targets:
        raise ValueError('COMPANY_RESEARCH_NOT_NOMINATED')
    if row.get('driver_state') not in {'CONFIRMED', 'DEVELOPING', 'REJECTED'}:
        raise ValueError('COMPANY_DRIVER_STATE_INVALID')
    if row.get('scope') not in {'LOCAL', 'GLOBAL'}:
        raise ValueError('COMPANY_SCOPE_INVALID')
    if row.get('rate_sensitive') not in {True, False} or not isinstance(row.get('rate_sensitive'), bool):
        raise ValueError('RATE_SENSITIVITY_REQUIRED')
    for field in ['why', 'driver', 'company_transmission', 'main_risk', 'main_counter_evidence', 'what_would_make_us_wrong']:
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError('COMPANY_RESEARCH_MISSING_' + field)
    if not isinstance(row.get('counter_evidence_reviewed'), bool) or not isinstance(row.get('major_counter_evidence'), bool):
        raise ValueError('COUNTER_REVIEW_REQUIRED')
    if row['scope'] == 'LOCAL' and row.get('driver_id') != 'UNMAPPED_OPPORTUNITY':
        raise ValueError('GLOBAL_DRIVER_CANNOT_BYPASS_INTERNATIONAL_CHECK_AS_LOCAL')
    if row['scope'] == 'LOCAL' and not row.get('local_scope_reason'):
        raise ValueError('LOCAL_SCOPE_REASON_REQUIRED')
    if row['driver_state'] != 'REJECTED':
        if not any(evidence_valid(e, as_of, ticker=row['ticker']) for e in row.get('fundamental_evidence', [])):
            raise ValueError('TIMELY_COMPANY_FUNDAMENTAL_REQUIRED')
    return row


def regime_compatibility(risk, research):
    if risk.get('status') != 'READY':
        return 'UNKNOWN'
    signals = risk.get('signals') or {}
    credit = signals.get('credit_hyg_lqd') or {}
    vix = number((signals.get('vix') or {}).get('price'))
    if (vix >= 35 or (credit.get('above_ma60') is False and number(credit.get('ret20')) < -0.03)):
        return 'ADVERSE'
    rate = signals.get('rate_pressure', 'UNKNOWN')
    if research.get('rate_sensitive') is True:
        if rate == 'ADVERSE':
            return 'ADVERSE'
        if rate == 'UNKNOWN':
            return 'UNKNOWN'
    if research.get('rate_sensitive') not in {True, False}:
        return 'UNKNOWN'
    if risk.get('regime') == 'NORMAL' and rate != 'ADVERSE':
        return 'SUPPORTIVE'
    return 'NEUTRAL'


def price_plan(hist):
    """Observed support/resistance, ATR noise buffer, no invented target return.

    R/R is upside to an observed 120-session high, not a probability or forecast.
    New highs use a disclosed base-range projection, never an assumed fixed 2R target.
    """
    out = dict(price_ok=False, confirmed=False, early_signal=False, severe=False,
               extended=False, technical='Price history unavailable', entry='Unavailable',
               invalidation='Unavailable', add_trigger='Unavailable', price_reason='Need sealed OHLCV')
    if hist is None or len(hist) < 80:
        return out
    h = hist.sort_index().copy()
    if not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(h.columns):
        return out
    h = h.apply(pd.to_numeric, errors='coerce').dropna(subset=['Open','High','Low','Close','Volume'])
    if len(h) < 80:
        return out
    c = h.Close; close = float(c.iloc[-1]); pre = h.iloc[:-1]
    atr = simple_atr(pre); ma20 = float(c.tail(20).mean())
    if not math.isfinite(atr) or atr <= 0 or close <= 0:
        return out
    bias = close / ma20 - 1; ret5 = close / c.iloc[-6] - 1
    pivot = float(pre.High.tail(20).max())
    support = float(pre.Low.tail(10).min())
    target = float(pre.High.tail(120).max())
    target_basis = "Observed 120-session resistance"
    if target <= close:
        target = pivot + (pivot - float(pre.Low.tail(20).min()))
        target_basis = "20-session base-height projection (scenario, not a forecast)"
    volume = float(h.Volume.iloc[-1] / pre.Volume.tail(20).median()) if pre.Volume.tail(20).median() > 0 else 0
    tick = tw_stock_tick(close)
    stop = _round_down_tick(support - 0.25 * atr, tw_stock_tick(support))
    entry_low = _round_up_tick(max(stop + atr, close - 0.25 * atr), tick)
    entry_high = _round_down_tick(close, tick)
    risk = entry_high - stop
    rr = (target - entry_high) / risk if risk > 0 else -1
    confirmed = close > pivot and volume >= 1.2
    recovery = close > float(c.iloc[-2]) and float(h.Low.iloc[-1]) >= support and close >= ma20
    improving = close > float(c.iloc[-6]) and close >= ma20
    early = improving and (volume >= 1.0 or recovery)
    extended = bias > 0.20 or ret5 > 0.25 or close > pivot + 0.75 * atr
    severe = bias >= 0.40 or ret5 >= 0.40
    liquid = float((h.Close * h.Volume).tail(20).mean()) >= 10_000_000
    valid = early and liquid and not extended and 0 < risk / close <= 0.08 and rr >= 2 and entry_low <= entry_high
    add = _round_up_tick(pivot + 0.25 * atr, tw_stock_tick(pivot))
    reason = (target_basis + ' offers at least 2R before costs; support defines <=8% price risk' if valid
              else 'Wait for a supported pullback with >=2R to observed resistance and <=8% stop distance')
    if target <= close:
        reason = 'No observed upside reference above price; reward/risk is unverified'
    if extended:
        reason = 'Extended price: wait for a new base; do not chase'
    out.update(price_ok=bool(valid), confirmed=bool(confirmed), early_signal=bool(early),
               severe=bool(severe), extended=bool(extended), technical='Confirmed breakout' if confirmed else 'Early strength / support recovery' if early else 'No early strength',
               entry=f'{entry_low:g}–{entry_high:g}' if risk > 0 else 'Unavailable',
               invalidation=f'Exit on loss of {stop:g}; thesis failure also invalidates',
               add_trigger=f'Close above {add:g} with volume >=1.2x prior median; thesis still supported and recheck R/R',
               price_reason=reason, entry_low=entry_low, entry_high=entry_high, stop=stop,
               reference_target=target, target_basis=target_basis, reward_risk=rr, current_price=close, bias20=bias,
               ret_5d=ret5, volume_ratio=volume)
    return out


def assess(candidate, research, risk, hist, as_of):
    plan = price_plan(hist)
    if candidate.get('reaction_state') == 'EXTENDED' or number(candidate.get('bias20')) > 0.20 or number(candidate.get('ret_5d')) > 0.25:
        plan.update(extended=True, price_ok=False, price_reason='Extended price: wait for a new base; do not chase')
    if number(candidate.get('bias20')) >= 0.40 or number(candidate.get('ret_5d')) >= 0.40:
        plan.update(severe=True, price_ok=False)
    row = dict(ticker=candidate.get('ticker'), name=candidate.get('name'),
               driver=candidate.get('driver_label', 'UNMAPPED / WHY?'), driver_state='UNVERIFIED',
               unmapped=candidate.get('driver_id') == 'UNMAPPED_OPPORTUNITY',
               why='WHY unresolved: obtain company evidence before taking risk',
               international='Unverified — same-driver evidence required', relative='UNVERIFIED',
               regime='UNKNOWN', action='WAIT', main_risk='Unverified causal interpretation',
               what_would_make_us_wrong='A price-only story or weak company transmission',
               planned_position_fraction=0.0, auto_trade_allowed=False, **plan)
    if not research:
        if plan['severe'] or candidate.get('driver_rejected') is True:
            row['action'] = 'PASS'
        return row
    row.update({k:research[k] for k in ['why','driver','driver_state','main_risk','main_counter_evidence','what_would_make_us_wrong']})
    row['regime'] = regime_compatibility(risk, research)
    company_urls = {e.get('source_url') for e in research.get('fundamental_evidence', []) if isinstance(e, dict)}
    if research.get('scope') == 'LOCAL':
        row['relative'] = 'LOCAL DRIVER'
        row['international'] = 'Not required: ' + research.get('local_scope_reason', '')
        international_ok = bool(research.get('local_scope_reason'))
    else:
        same = [e for e in research.get('international_evidence', [])
                if evidence_valid(e, as_of, driver=research.get('driver_id')) and e.get('same_driver') is True and e.get('source_url') not in company_urls]
        international_ok = bool(same)
        row['international_evidence'] = same
        row['international'] = '; '.join(e['claim'] for e in same) or 'Unverified — same-driver evidence required'
        gap = number(candidate.get('transmission_gap_proxy'), 0)
        row['relative'] = 'GLOBAL AHEAD' if gap > 0.08 else 'TAIWAN AHEAD' if gap < -0.08 else 'TOGETHER'
    fundamental = [e for e in research.get('fundamental_evidence', []) if evidence_valid(e, as_of, ticker=row['ticker'])]
    row['evidence'] = fundamental
    row['company_transmission'] = research.get('company_transmission')
    if (candidate.get('driver_rejected') is True or row['driver_state'] == 'REJECTED' or research.get('major_counter_evidence') is True
            or row['regime'] == 'ADVERSE' or plan['severe'] or candidate.get('reaction_state') == 'BROKEN'):
        row['action'] = 'PASS'
    elif (fundamental and international_ok and row['regime'] in {'SUPPORTIVE','NEUTRAL'}
          and research.get('counter_evidence_reviewed') is True and research.get('major_counter_evidence') is False
          and research.get('company_transmission') and plan['price_ok']):
        operating_confirmed = len({e.get('metric') for e in fundamental}) >= 2 and len({e.get('source_url') for e in fundamental}) >= 2
        row['action'] = 'BUY' if row['driver_state'] == 'CONFIRMED' and (plan['confirmed'] or operating_confirmed) else 'EARLY BUY'
        row['planned_position_fraction'] = 0.35 if row['action'] == 'EARLY BUY' else 1.0
    return row


def rank_opportunities(rows, limit=5):
    """Rank every nominated opportunity.

    `limit` is retained for backward compatibility with callers, but presentation
    must not hide candidates. The canonical rule is that every unique candidate
    survives ranking; action/evidence/research quality only changes order.
    """
    ordered = sorted(rows, key=lambda r: ({'BUY':0,'EARLY BUY':1,'WAIT':2,'PASS':3}[r['action']],
                     0 if r.get('evidence') else 1, 0 if r.get('research_completed') else 1,
                     0 if r.get('price_ok') else 1, r.get('extended', False),
                     -number(r.get('research_priority'),0), str(r.get('ticker'))))
    result=[]; seen=set()
    for row in ordered:
        if row['ticker'] in seen:
            continue
        result.append(row); seen.add(row['ticker'])
    return result
