import pandas as pd
import pytest
from market_data import download_histories, YFinanceProvider


def bars():
    return pd.DataFrame({'Close': [1., 2.]}, index=pd.date_range('2026-01-01', periods=2))


def test_batch_failure_retries_only_missing_and_preserves_successes():
    class Provider:
        name = 'test'
        calls = []
        def download(self, tickers, period):
            self.calls.append(tickers)
            if tickers == ['A', 'B']:
                raise TimeoutError()
            return {t: bars() for t in tickers if t != 'B'}
    provider = Provider()
    got = download_histories(['A', 'B', 'C', 'C'], provider=provider,
                             batch_size=2, retries=2, retry_delay=0)
    assert set(got.histories) == {'A', 'C'}
    assert provider.calls == [['A', 'B'], ['C'], ['A'], ['B'], ['B']]
    assert got.diagnostics['missing_tickers'] == ['B']


@pytest.mark.parametrize('layout', ['flat', 'ticker_first', 'field_first'])
def test_yfinance_single_and_multiindex(monkeypatch, layout):
    import market_data
    raw = bars()
    if layout != 'flat':
        raw = pd.concat({'A': raw}, axis=1)
        if layout == 'field_first':
            raw = raw.swaplevel(axis=1)
    monkeypatch.setattr(market_data.yf, 'download', lambda *a, **k: raw)
    pd.testing.assert_frame_equal(YFinanceProvider().download(['A'], '1y')['A'], bars())


def test_all_nan_and_missing_close_are_reported():
    class Provider:
        name = 'bad'
        def download(self, tickers, period):
            return {'A': pd.DataFrame({'Close':[float('nan')]}), 'B': pd.DataFrame({'High':[1]})}
    got = download_histories(['A','B'], provider=Provider(), retries=0)
    assert not got.histories
    assert got.diagnostics['missing_tickers'] == ['A','B']


def test_deadline_stops_new_batches(monkeypatch):
    import market_data
    clock = iter([0, 0, 500, 501])
    monkeypatch.setattr(market_data.time, 'monotonic', lambda: next(clock))
    class Provider:
        name='bounded'
        def download(self,tickers,period):return {t:bars() for t in tickers}
    got=download_histories(['A','B'],provider=Provider(),batch_size=1,max_seconds=100)
    assert set(got.histories)=={'A'}
    assert got.diagnostics['deadline_reached']
    assert got.diagnostics['missing_tickers']==['B']
