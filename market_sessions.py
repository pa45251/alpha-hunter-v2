"""Operational market-data integrity; no trading thresholds or score changes."""
from functools import lru_cache
import pandas as pd
import exchange_calendars as xc


def exchange(ticker):
    t = str(ticker).upper()
    if t.endswith(('.TW', '.TWO')) or t == '^TWII':
        return 'XTAI'
    if t.endswith('.T'):
        return 'XTKS'
    if t.endswith(('.KS', '.KQ')):
        return 'XKRX'
    if '.' in t or '=' in t or t.endswith('-USD'):
        raise ValueError('UNSUPPORTED_EXCHANGE')
    return 'XNYS'  # Includes US-listed ADRs; issuer domicile is not trading venue.

@lru_cache(maxsize=32)
def calendar(name, year):
    return xc.get_calendar(name, start=f'{year-5}-01-01', end=f'{year+1}-12-31')


def clock(now=None):
    ts = pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if ts.tzinfo is None:
        raise ValueError('CLOCK_TIMEZONE_REQUIRED')
    return ts.tz_convert('UTC')


def closed_sessions(ticker, now=None):
    ts = clock(now)
    schedule = calendar(exchange(ticker), ts.year).schedule
    return schedule.index[schedule['close'] <= ts]


def latest_closed_session(ticker, now=None):
    sessions = closed_sessions(ticker, now)
    if sessions.empty:
        raise ValueError('CLOSED_SESSION_UNAVAILABLE')
    return sessions[-1].date().isoformat()


def clip_closed_bars(hist, ticker, now=None):
    if hist is None or hist.empty:
        return pd.DataFrame() if hist is None else hist.copy()
    x = hist.copy()
    if isinstance(x.columns, pd.MultiIndex):
        # yfinance returns a MultiIndex even for a single ticker.
        if ticker in x.columns.get_level_values(-1):
            x = x.xs(ticker, axis=1, level=-1)
        elif ticker in x.columns.get_level_values(0):
            x = x[ticker]
        else:
            raise ValueError('PRICE_COLUMN_IDENTITY_MISMATCH')
    idx = pd.DatetimeIndex(pd.to_datetime(x.index, errors='coerce'))
    if idx.tz is not None:
        idx = idx.tz_convert(calendar(exchange(ticker), clock(now).year).tz).tz_localize(None)
    dates = idx.normalize()
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError('INVALID_OR_DUPLICATE_PRICE_SESSION')
    x = x.loc[dates.isin(closed_sessions(ticker, now))].copy()
    return x.sort_index()
