import numpy as np
import pandas as pd
import pytest
from global_universe import local_benchmark, load_core, market_policy
from scanner_core import ScanConfig, run_scan


def history(rate):
    c = 100 * (1 + rate) ** np.arange(180)
    return pd.DataFrame({'Close': c, 'High': c * 1.01, 'Low': c * .99, 'Volume': 1000},
                        index=pd.bdate_range('2025-01-01', periods=180))


@pytest.mark.parametrize('ticker,benchmark', [('6981.T','^N225'), ('000660.KS','^KS11'),
    ('356680.KQ','^KQ11'), ('0700.HK','^HSI'), ('600000.SS','000300.SS'),
    ('SU.PA','^STOXX'), ('MAERSK-B.CO','^OMXC25'), ('ASML','SPY')])
def test_listing_benchmark(ticker, benchmark):
    assert local_benchmark({'ticker':ticker, 'benchmark':'SPY'}) == benchmark


def test_local_leader_is_not_created_by_market_rally(tmp_path):
    class Provider:
        name = 'synthetic'
        def download(self, tickers, period):
            return {t: history(.002 if t in ('JP.T','^N225') else .0001) for t in tickers}
    path = tmp_path/'core.csv'
    pd.DataFrame([{'ticker':'JP.T','theme':'Memory'}]).to_csv(path,index=False)
    got = run_scan(path, ScanConfig(provider=Provider(), output_dir=str(tmp_path)))
    row = got['stocks'].iloc[0]
    assert row.rs_20d_vs_local == pytest.approx(0)
    assert row.rs_20d_vs_bench == pytest.approx(0)
    assert row.rs_20d_vs_global > .03
    assert '^N225' not in set(got['stocks'].ticker)


def test_missing_local_benchmark_is_not_silently_spy(tmp_path):
    class Provider:
        name = 'partial'
        def download(self, tickers, period):
            return {t: history(.001) for t in tickers if t != '^N225'}
    path = tmp_path/'core.csv'
    pd.DataFrame([{'ticker':'JP.T','theme':'Memory'}]).to_csv(path,index=False)
    got = run_scan(path, ScanConfig(provider=Provider(), retries=0, output_dir=str(tmp_path)))
    row = got['stocks'].iloc[0]
    assert np.isnan(row.rs_20d_vs_local)
    assert np.isnan(row.leader_score_v1)
    assert row.local_rs_status == 'MISSING_OR_SHORT_BENCHMARK'


def test_core_universe_preserved():
    core = load_core('config/universe.csv')
    assert len(core) == 221
    assert core.universe_layer.eq('CORE').all()


def test_open_asian_session_excluded_by_local_clock(monkeypatch):
    import scanner_core
    from datetime import datetime
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026,9,10,3,tzinfo=__import__('datetime').timezone.utc).astimezone(tz)
    monkeypatch.setattr(scanner_core,'datetime',Clock)
    hist=pd.DataFrame({'Close':[100,101]},index=pd.to_datetime(['2026-09-09','2026-09-10']))
    # Noon Tokyo/Seoul: today's still-forming bar must be excluded.
    for ticker in ('6981.T','000660.KS','356680.KQ','0700.HK','600000.SS'):
        assert len(scanner_core.closed_history(hist,ticker))==1


def test_bad_ohlc_one_ticker_does_not_abort_scan(tmp_path):
    class Provider:
        name='partial_ohlc'
        def download(self,tickers,period):
            return {t:history(.001).drop(columns=['High']) if t=='BAD' else history(.001) for t in tickers}
    path=tmp_path/'core.csv'
    pd.DataFrame({'ticker':['A','BAD'],'theme':'Memory'}).to_csv(path,index=False)
    got=run_scan(path,ScanConfig(provider=Provider(),output_dir=str(tmp_path)))
    assert set(got['stocks'].ticker)=={'A'}
    assert got['core_quality']['missing_feature_tickers']==['BAD']
