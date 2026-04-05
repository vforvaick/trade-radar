"""Tests for market regime classification."""
import numpy as np
import pandas as pd
import pytest
from bot.research.types import RegimeType
from bot.research.regime import classify_regime, classify_regime_series


def _make_btc_df(closes: list[float], n_bars: int = 60) -> pd.DataFrame:
    """Helper: create BTC 4H DataFrame with given close prices."""
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n_bars, freq="4h"),
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000.0] * n_bars,
    })
    return df


class TestClassifyRegime:
    def test_trend_up(self):
        closes = np.linspace(40000, 46000, 60).tolist()
        df = _make_btc_df(closes, 60)
        regime = classify_regime(df)
        assert regime == RegimeType.TREND_UP

    def test_trend_down(self):
        closes = np.linspace(46000, 39000, 60).tolist()
        df = _make_btc_df(closes, 60)
        regime = classify_regime(df)
        assert regime == RegimeType.TREND_DOWN

    def test_low_vol_compression(self):
        base = 42000
        np.random.seed(42)
        noise = np.random.normal(0, 50, 60)
        closes = (base + noise).tolist()
        df = _make_btc_df(closes, 60)
        regime = classify_regime(df)
        assert regime in (RegimeType.LOW_VOL_COMPRESSION, RegimeType.HIGH_VOL_CHOP)

    def test_requires_minimum_bars(self):
        closes = [42000.0] * 10
        df = _make_btc_df(closes, 10)
        with pytest.raises(ValueError, match="minimum"):
            classify_regime(df)


class TestClassifyRegimeSeries:
    def test_returns_series_of_regimes(self):
        closes = np.linspace(40000, 46000, 120).tolist()
        df = _make_btc_df(closes, 120)
        regimes = classify_regime_series(df, window=180)
        assert len(regimes) == len(df)
        assert regimes.iloc[-1] == RegimeType.TREND_UP.value
