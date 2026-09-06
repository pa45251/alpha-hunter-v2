from __future__ import annotations

import numpy as np
import pandas as pd

import risk_regime as rr


def _hist(start: float, end: float, n: int = 100):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    vals = np.linspace(start, end, n)
    return pd.DataFrame({"Close": vals, "Adj Close": vals}, index=idx)


def _risk_on_histories():
    h = {
        "^VIX": _hist(16, 15), "^VXN": _hist(22, 20),
        "SPY": _hist(500, 620), "QQQ": _hist(500, 650),
        "RSP": _hist(100, 130), "IWM": _hist(100, 135), "MTUM": _hist(100, 132),
        "HYG": _hist(80, 90), "LQD": _hist(100, 105),
    }
    for t in rr.GLOBAL_TICKERS:
        h[t] = _hist(100, 125)
    return h


def _risk_off_histories():
    h = {
        "^VIX": _hist(22, 42), "^VXN": _hist(28, 48),
        "SPY": _hist(620, 480), "QQQ": _hist(650, 450),
        "RSP": _hist(130, 85), "IWM": _hist(135, 75), "MTUM": _hist(132, 82),
        "HYG": _hist(90, 72), "LQD": _hist(105, 110),
    }
    for t in rr.GLOBAL_TICKERS:
        h[t] = _hist(125, 80)
    return h


def test_risk_on_has_low_cash_target():
    out = rr.build_risk_regime(_risk_on_histories())
    assert out["status"] == "READY"
    assert out["regime"] in {"RISK_ON", "NORMAL"}
    assert out["target_cash_pct"] <= 5


def test_risk_off_raises_cash_target():
    out = rr.build_risk_regime(_risk_off_histories())
    assert out["status"] == "READY"
    assert out["regime"] in {"DEFENSIVE", "CRISIS"}
    assert out["target_cash_pct"] >= 30


def test_missing_vix_fails_closed():
    h = _risk_on_histories()
    h.pop("^VIX")
    out = rr.build_risk_regime(h)
    assert out["status"] == "DATA_UNAVAILABLE"
    assert out["target_cash_pct"] is None
