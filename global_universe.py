"""Explicit sensor boundary and listing-market benchmark/session policy."""
import pandas as pd

# Benchmark helpers are downloaded, never appended to the Core Sensor universe.
# ADRs use their listing market; issuer domicile is not a trading currency.
MARKETS = {
    '.T': ('^N225', 'Asia/Tokyo', 16, 'JPY'),
    '.KS': ('^KS11', 'Asia/Seoul', 16, 'KRW'),
    '.KQ': ('^KQ11', 'Asia/Seoul', 16, 'KRW'),
    '.HK': ('^HSI', 'Asia/Hong_Kong', 17, 'HKD'),
    '.SS': ('000300.SS', 'Asia/Shanghai', 16, 'CNY'),
    '.SZ': ('000300.SS', 'Asia/Shanghai', 16, 'CNY'),
    '.TW': ('^TWII', 'Asia/Taipei', 14, 'TWD'),
    '.TWO': ('^TWII', 'Asia/Taipei', 14, 'TWD'),
    '.PA': ('^STOXX', 'Europe/Paris', 18, 'EUR'),
    '.DE': ('^STOXX', 'Europe/Berlin', 18, 'EUR'),
    '.AS': ('^STOXX', 'Europe/Amsterdam', 18, 'EUR'),
    '.MI': ('^STOXX', 'Europe/Rome', 18, 'EUR'),
    '.SW': ('^SSMI', 'Europe/Zurich', 18, 'CHF'),
    '.CO': ('^OMXC25', 'Europe/Copenhagen', 18, 'DKK'),
    '.L': ('^FTSE', 'Europe/London', 17, 'GBP'),
    '.TO': ('^GSPTSE', 'America/Toronto', 17, 'CAD'),
}


def market_policy(ticker):
    for suffix, policy in MARKETS.items():
        if ticker.endswith(suffix) or ticker == policy[0]:
            return policy
    return ('SPY', 'America/New_York', 17, 'USD')


def local_benchmark(meta):
    configured = str(meta.get('benchmark', '')).strip()
    default = market_policy(str(meta['ticker']))[0]
    # Legacy non-US rows all used SPY. Resolve them by listing market.
    return default if configured in ('', 'nan', 'SPY') else configured


def core_only(frame):
    """Legacy unlabelled frames are Core; labelled mixed frames fail closed."""
    if frame is None or frame.empty or 'universe_layer' not in frame:
        return frame
    return frame.loc[frame['universe_layer'].eq('CORE')].copy()


def load_core(path):
    frame = pd.read_csv(path)
    if not {'ticker', 'theme'}.issubset(frame):
        raise ValueError('Core universe must contain ticker and theme')
    if frame['ticker'].isna().any() or frame['ticker'].duplicated().any():
        raise ValueError('Core tickers must be nonempty and unique')
    if 'universe_layer' in frame and not frame['universe_layer'].eq('CORE').all():
        raise ValueError('Discovery must not be stored in the Core universe')
    frame['universe_layer'] = 'CORE'
    return frame
