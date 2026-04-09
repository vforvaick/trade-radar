"""Tests for backtester 4-regime parity."""
import pandas as pd
import numpy as np
from bot.backtester import determine_btc_trend_at


def _make_btc_df(n=200, trend="up"):
    """Create synthetic BTC OHLCV data."""
    dates = pd.date_range("2025-01-01", periods=n, freq="4h")
    base = 80000.0
    if trend == "up":
        close = base + np.linspace(0, 15000, n) + np.random.normal(0, 100, n)
    elif trend == "down":
        close = base - np.linspace(0, 15000, n) + np.random.normal(0, 100, n)
    else:
        close = base + np.random.normal(0, 200, n)
    close = np.maximum(close, 1000)
    return pd.DataFrame({
        "timestamp": dates,
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.uniform(1000, 5000, n),
    })


def test_determine_btc_trend_returns_4_regime_value():
    """determine_btc_trend_at() returns 4-regime string, not old 3-regime."""
    btc_df = _make_btc_df(200, "up")
    ts = btc_df["timestamp"].iloc[-1]
    result = determine_btc_trend_at(btc_df, ts)
    valid_regimes = {"TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}
    assert result in valid_regimes, f"Got '{result}', expected one of {valid_regimes}"


def test_determine_btc_trend_insufficient_data_returns_safe_default():
    """With too few bars, return HIGH_VOL_CHOP (safe default)."""
    btc_df = _make_btc_df(10, "up")
    ts = btc_df["timestamp"].iloc[-1]
    result = determine_btc_trend_at(btc_df, ts)
    assert result == "HIGH_VOL_CHOP"


def test_determine_btc_trend_uses_classify_regime():
    """Verify it calls classify_regime() from bot.research.regime."""
    from unittest.mock import patch
    from bot.research.types import RegimeType

    btc_df = _make_btc_df(200, "up")
    ts = btc_df["timestamp"].iloc[-1]

    with patch("bot.backtester.classify_regime", return_value=RegimeType.TREND_DOWN) as mock:
        result = determine_btc_trend_at(btc_df, ts)
        assert mock.called
        assert result == "TREND_DOWN"
