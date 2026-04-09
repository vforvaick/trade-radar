# tests/test_regime_detector.py
"""Tests for RegimeDetector — cached, multi-TF regime detection."""
import time
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import pytest

from bot.research.types import RegimeType


def _make_btc_df(n=200, trend="up"):
    """Create synthetic BTC OHLCV data."""
    dates = pd.date_range("2025-01-01", periods=n, freq="4h")
    base = 80000.0
    if trend == "up":
        close = base + np.linspace(0, 15000, n) + np.random.normal(0, 200, n)
    elif trend == "down":
        close = base - np.linspace(0, 15000, n) + np.random.normal(0, 200, n)
    else:
        close = base + np.random.normal(0, 500, n)
    close = np.maximum(close, 1000)
    return pd.DataFrame({
        "timestamp": dates,
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.uniform(1000, 5000, n),
    })


class TestRegimeDetectorCache:
    """Cache TTL and invalidation tests."""

    def test_cache_returns_same_result_within_ttl(self):
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            r1 = detector.get_current_regime()

        # Second call should use cache (no fetch needed)
        r2 = detector.get_current_regime()
        assert r1 == r2

    def test_cache_invalidate_forces_refetch(self):
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]) as mock_fetch:
            detector.get_current_regime()
            assert mock_fetch.call_count == 2

        detector.invalidate_cache()

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]) as mock_fetch:
            detector.get_current_regime()
            assert mock_fetch.call_count == 2

    def test_cache_expires_after_ttl(self):
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()
        detector.CACHE_TTL = 0.1  # 100ms for test

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            detector.get_current_regime()

        time.sleep(0.15)

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]) as mock_fetch:
            detector.get_current_regime()
            assert mock_fetch.call_count == 2


class TestRegimeDetectorConfirmation:
    """1H confirmation downgrade logic."""

    def test_trend_up_confirmed_when_ema9_above_ema21(self):
        """4H=TREND_UP + 1H EMA9 > EMA21 → TREND_UP (confirmed)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                regime = detector.get_current_regime()
                assert regime == "TREND_UP"

    def test_trend_up_downgraded_when_ema9_below_ema21(self):
        """4H=TREND_UP + 1H EMA9 < EMA21 → HIGH_VOL_CHOP (downgraded)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "down")  # 1H contradicts

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                regime = detector.get_current_regime()
                assert regime == "HIGH_VOL_CHOP"

    def test_trend_down_confirmed(self):
        """4H=TREND_DOWN + 1H EMA9 < EMA21 → TREND_DOWN (confirmed)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "down")
        btc_1h = _make_btc_df(200, "down")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_DOWN):
                regime = detector.get_current_regime()
                assert regime == "TREND_DOWN"

    def test_trend_down_downgraded_when_1h_bouncing(self):
        """4H=TREND_DOWN + 1H EMA9 > EMA21 → HIGH_VOL_CHOP (downgraded)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "down")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_DOWN):
                regime = detector.get_current_regime()
                assert regime == "HIGH_VOL_CHOP"

    def test_high_vol_chop_never_upgraded(self):
        """4H=HIGH_VOL_CHOP → stays HIGH_VOL_CHOP regardless of 1H."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "flat")
        btc_1h = _make_btc_df(200, "up")  # bullish 1H should NOT upgrade

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.HIGH_VOL_CHOP):
                regime = detector.get_current_regime()
                assert regime == "HIGH_VOL_CHOP"

    def test_low_vol_compression_never_upgraded(self):
        """4H=LOW_VOL_COMPRESSION → stays LOW_VOL_COMPRESSION regardless of 1H."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "flat")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.LOW_VOL_COMPRESSION):
                regime = detector.get_current_regime()
                assert regime == "LOW_VOL_COMPRESSION"


class TestRegimeDetectorApiFailure:
    """Error handling and safe defaults."""

    def test_api_failure_returns_cached(self):
        """On API failure, return last cached regime."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                detector.get_current_regime()

        detector.invalidate_cache()

        with patch("bot.regime_detector.fetch_klines_range", side_effect=Exception("timeout")):
            regime = detector.get_current_regime()
            assert regime == "TREND_UP"

    def test_no_cache_api_failure_returns_safe_default(self):
        """No cache + API failure → HIGH_VOL_CHOP safe default."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        with patch("bot.regime_detector.fetch_klines_range", side_effect=Exception("timeout")):
            regime = detector.get_current_regime()
            assert regime == "HIGH_VOL_CHOP"

    def test_get_regime_metadata_returns_dict(self):
        """get_regime_metadata() returns structured dict with expected keys."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                detector.get_current_regime()
                meta = detector.get_regime_metadata()

        assert "regime" in meta
        assert "btc_price" in meta
        assert "adx" in meta
        assert "ema9_1h" in meta
        assert "ema21_1h" in meta
        assert "confirmation_matched" in meta
        assert "timestamp" in meta
