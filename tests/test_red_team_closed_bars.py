import pandas as pd
import scanner_core as sc

def test_scanner_download_discards_future_daily_bar(monkeypatch):
    hist = pd.DataFrame({'Open':[100,9999], 'High':[101,9999], 'Low':[99,9999], 'Close':[100,9999], 'Volume':[100,100]},index=pd.to_datetime(['2026-01-02','2099-01-02']))
    monkeypatch.setattr(sc.yf, 'download', lambda *a, **kw: hist)
    result = sc._download(['SPY'])['SPY']
    assert result.index.max().year == 2026

from market_sessions import clip_closed_bars, latest_closed_session
import pytest

@pytest.mark.parametrize('ticker,now,expected', [
    ('2317.TW','2026-09-07T05:29:00Z','2026-09-04'),
    ('2317.TW','2026-09-07T05:31:00Z','2026-09-07'),
    ('SPY','2026-09-07T23:00:00Z','2026-09-04'), # Labor Day
    ('SPY','2026-03-09T19:59:00Z','2026-03-06'), # DST
    ('SPY','2026-03-09T20:01:00Z','2026-03-09'),
    ('SPY','2026-11-27T18:01:00Z','2026-11-27'), # early close
    ('6981.T','2026-09-07T00:36:00Z','2026-09-04'),
    ('005930.KS','2026-09-07T00:36:00Z','2026-09-04'),
])
def test_exchange_close_holiday_and_dst(ticker,now,expected):
    assert latest_closed_session(ticker,now)==expected

def test_holiday_sentinel_removed():
    h=pd.DataFrame({'Close':[100,9999]},index=pd.to_datetime(['2026-09-04','2026-09-07']))
    assert len(clip_closed_bars(h,'SPY','2026-09-08T01:00:00Z'))==1

def test_duplicate_session_fails_closed():
    h=pd.DataFrame({'Close':[100,9999]},index=pd.to_datetime(['2026-09-04','2026-09-04']))
    with pytest.raises(ValueError,match='DUPLICATE'):
        clip_closed_bars(h,'SPY','2026-09-08T01:00:00Z')
