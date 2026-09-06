from datetime import datetime, timezone

import pandas as pd

from shadow_validation import build_validation_report, evaluate_shadow_audit


def prices(start="2026-01-05", periods=90, open0=100.0, daily=1.0):
    idx = pd.bdate_range(start, periods=periods)
    opens = [open0 + i * daily for i in range(periods)]
    closes = [x + 0.5 * daily for x in opens]
    return pd.DataFrame({"Open": opens, "Close": closes}, index=idx)


def audit(action="BUY_STOCK", candidate="ENTRY_TRIGGERED_STOCK_RISK_PENDING"):
    return pd.DataFrame([{
        "audit_at_utc": "2026-01-05T00:00:00+00:00",  # 08:00 Taipei
        "run_id": "r1",
        "ticker": "SYN1.TW",
        "driver_id": "AI_SERVER_SHIPMENTS",
        "candidate_action": candidate,
        "portfolio_action": action,
    }])


def test_uses_next_session_open_not_same_day_price():
    px = prices()
    bench = prices(open0=100.0, daily=0.0)

    def loader(ticker, start, end):
        return bench if ticker == "^TWII" else px

    out = evaluate_shadow_audit(audit(), price_loader=loader, horizons=(5,), now_utc=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert len(out) == 1
    assert out.iloc[0]["entry_date"] == "2026-01-06"
    assert out.iloc[0]["entry_basis"] == "NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_DATE"


def test_unmatured_horizon_is_not_scored():
    short = prices(periods=3)

    def loader(ticker, start, end):
        return short

    out = evaluate_shadow_audit(audit(), price_loader=loader, horizons=(5,), now_utc=datetime(2026, 1, 8, tzinfo=timezone.utc))
    assert out.empty


def test_buy_is_directionally_scored_against_benchmark():
    stock = prices(daily=2.0)
    bench = prices(daily=0.2)

    def loader(ticker, start, end):
        return bench if ticker == "^TWII" else stock

    out = evaluate_shadow_audit(audit(), price_loader=loader, horizons=(5,), now_utc=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert bool(out.iloc[0]["directional_scored"]) is True
    assert bool(out.iloc[0]["directional_correct"]) is True
    assert out.iloc[0]["excess_return"] > 0


def test_watch_entry_is_observation_only_not_called_correct_or_wrong():
    stock = prices(daily=-0.5)
    bench = prices(daily=0.0)

    def loader(ticker, start, end):
        return bench if ticker == "^TWII" else stock

    out = evaluate_shadow_audit(audit(action="WATCH_ENTRY", candidate="WATCH_ENTRY"), price_loader=loader, horizons=(5,), now_utc=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert bool(out.iloc[0]["directional_scored"]) is False
    assert pd.isna(out.iloc[0]["directional_correct"])


def test_avoid_broken_is_correct_when_it_underperforms():
    stock = prices(daily=-0.5)
    bench = prices(daily=0.2)

    def loader(ticker, start, end):
        return bench if ticker == "^TWII" else stock

    out = evaluate_shadow_audit(audit(action="AVOID_BROKEN", candidate="AVOID_BROKEN"), price_loader=loader, horizons=(5,), now_utc=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert bool(out.iloc[0]["directional_scored"]) is True
    assert bool(out.iloc[0]["directional_correct"]) is True


def test_report_does_not_tune_thresholds():
    stock = prices(daily=2.0)
    bench = prices(daily=0.2)

    def loader(ticker, start, end):
        return bench if ticker == "^TWII" else stock

    out = evaluate_shadow_audit(audit(), price_loader=loader, horizons=(5, 20), now_utc=datetime(2026, 6, 1, tzinfo=timezone.utc))
    report = build_validation_report(out)
    assert report["threshold_tuning_allowed"] is False
    assert report["matured_outcomes"] == 2
    assert report["directional_scored_outcomes"] == 2
