"""Tests for kline_provider parameter in run_backtest()."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from bot.backtester import run_backtest


def _make_klines(n=200):
    """Generate a minimal OHLCV DataFrame for backtesting."""
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 1, n))
    opens = closes * (1 + rng.normal(0, 0.001, n))
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.01, n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.01, n))
    volumes = rng.uniform(1000, 5000, n)
    times = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "timestamp": times,
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


def test_kline_provider_backward_compat():
    """run_backtest(kline_provider=None) falls back to fetch_klines_range."""
    df = _make_klines(200)

    with patch("bot.backtester.fetch_klines_range", return_value=df) as mock_fetch:
        run_backtest(["ETHUSDT"], days=7, kline_provider=None)

    assert mock_fetch.called, "fetch_klines_range should be called when kline_provider=None"


def test_kline_provider_custom():
    """run_backtest(kline_provider=fn) uses fn, not fetch_klines_range."""
    df = _make_klines(200)
    custom_provider = MagicMock(return_value=df)

    with patch("bot.backtester.fetch_klines_range") as mock_fetch:
        run_backtest(["ETHUSDT"], days=7, kline_provider=custom_provider)

    assert custom_provider.called, "custom kline_provider should be called"
    assert not mock_fetch.called, "fetch_klines_range must NOT be called when kline_provider is supplied"


def test_kline_provider_receives_correct_args():
    """kline_provider is called with (symbol, interval, start_ms, end_ms)."""
    df = _make_klines(200)
    calls = []

    def recording_provider(symbol, interval, start_ms, end_ms):
        calls.append((symbol, interval, start_ms, end_ms))
        return df

    run_backtest(["ETHUSDT"], interval="1h", days=7, kline_provider=recording_provider)

    # Should have one call for BTC + one for ETHUSDT
    symbols_called = [c[0] for c in calls]
    assert "BTCUSDT" in symbols_called
    assert "ETHUSDT" in symbols_called
    for _, interval, start_ms, end_ms in calls:
        assert interval == "1h"
        assert start_ms < end_ms
