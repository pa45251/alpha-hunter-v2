"""Replaceable daily-bar providers with bounded, partial-failure-safe downloads."""
from dataclasses import dataclass, field
from typing import Protocol
import time

import pandas as pd
import yfinance as yf


class MarketDataProvider(Protocol):
    name: str

    def download(self, tickers: list[str], period: str) -> dict[str, pd.DataFrame]: ...


class YFinanceProvider:
    name = "yfinance"

    def download(self, tickers, period):
        raw = yf.download(tickers, period=period, auto_adjust=False,
                          group_by="ticker", progress=False, threads=8, timeout=12)
        result = {}
        if raw is None or raw.empty:
            return result
        for ticker in tickers:
            if isinstance(raw.columns, pd.MultiIndex):
                frame = None
                for level in range(raw.columns.nlevels):
                    if ticker in raw.columns.get_level_values(level):
                        frame = raw.xs(ticker, axis=1, level=level).copy()
                        break
            else:
                frame = raw.copy() if len(tickers) == 1 else None
            if frame is not None:
                result[ticker] = frame
        return result


@dataclass
class DownloadResult:
    histories: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)


def download_histories(tickers, period="2y", provider=None, *, batch_size=40,
                       retries=2, retry_delay=0.5, max_seconds=300):
    if batch_size < 1 or retries < 0:
        raise ValueError("batch_size must be positive and retries nonnegative")
    provider = provider or YFinanceProvider()
    requested = list(dict.fromkeys(str(t) for t in tickers if t))
    histories, errors, attempts = {}, {}, {}
    started = time.monotonic()
    pending = requested
    deadline_reached = False
    for attempt in range(retries + 1):
        # Smaller retry batches isolate provider errors without refetching successes.
        size = max(1, batch_size // (2 ** attempt))
        for start in range(0, len(pending), size):
            if time.monotonic() - started >= max_seconds:
                deadline_reached = True
                break
            batch = pending[start:start + size]
            for ticker in batch:
                attempts[ticker] = attempts.get(ticker, 0) + 1
            try:
                received = provider.download(batch, period)
            except Exception as exc:
                received = {}
                for ticker in batch:
                    errors[ticker] = type(exc).__name__
            for ticker in batch:
                try:
                    frame = received.get(ticker)
                    if frame is None or frame.empty or "Close" not in frame:
                        raise ValueError("MISSING_CLOSE")
                    frame = frame.copy()
                    for column in ("Open", "High", "Low", "Close", "Adj Close", "Volume"):
                        if column in frame:
                            frame[column] = pd.to_numeric(frame[column], errors="coerce").replace([float("inf"), -float("inf")], float("nan"))
                    frame.index = pd.to_datetime(frame.index, errors="coerce")
                    frame = frame.loc[frame.index.notna()]
                    frame = frame.loc[frame["Close"].gt(0) & frame["Close"].lt(float("inf"))]
                    if frame.empty:
                        raise ValueError("NO_VALID_CLOSE")
                    frame = frame.loc[~frame.index.duplicated(keep="last")].sort_index()
                    histories[ticker] = frame
                    errors.pop(ticker, None)
                except Exception as exc:
                    errors.setdefault(ticker, str(exc))
        pending = [t for t in requested if t not in histories]
        if not pending or deadline_reached:
            break
        if attempt < retries and retry_delay:
            time.sleep(retry_delay * (attempt + 1))
    return DownloadResult(histories, {
        "provider": provider.name, "requested_count": len(requested),
        "received_count": len(histories), "missing_tickers": pending,
        "attempts": attempts, "errors": errors,
        "deadline_reached": deadline_reached,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    })
