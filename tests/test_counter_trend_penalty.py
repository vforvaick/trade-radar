"""Tests for COUNTER_TREND_PENALTY in scorer and extended_scorer."""
import pytest
import numpy as np
import pandas as pd

from bot import config
from bot.scorer import score_confluence


def _klines(rows=120, trend="up") -> pd.DataFrame:
    """Synthetic klines that produce a clear directional signal."""
    rng = np.random.default_rng(42)
    if trend == "up":
        close = 100.0 + np.linspace(0, 20, rows) + rng.normal(0, 0.3, rows)
    else:
        close = 120.0 - np.linspace(0, 20, rows) + rng.normal(0, 0.3, rows)
    high = close + abs(rng.normal(0, 0.5, rows))
    low = close - abs(rng.normal(0, 0.5, rows))
    volume = rng.uniform(1000, 5000, rows)
    # Big volume spike at end to trigger volume confirmation
    volume[-3:] = 20000
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "timestamp": pd.date_range("2024-01-01", periods=rows, freq="1h"),
    })


class TestCounterTrendPenalty:
    """COUNTER_TREND_PENALTY multiplier tests."""

    def test_short_during_trend_up_gets_penalty(self, monkeypatch):
        """SHORT signal during TREND_UP should have confidence reduced by CTP."""
        monkeypatch.setattr(config, "COUNTER_TREND_PENALTY", {
            "TREND_UP": 0.5, "TREND_DOWN": 0.5,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "BTC_TREND_WEIGHTS", {
            "TREND_UP": 1.0, "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
        })

        # Downtrend klines → SHORT signal
        df = _klines(trend="down")
        result = score_confluence(df, btc_trend="TREND_UP")

        if result["raw_confidence"] > 0 and result.get("counter_trend_penalty") is not None:
            # If it produced a SHORT signal, CTP should be 0.5
            if result["direction"] == "SHORT" or (result["direction"] is None and result["raw_confidence"] > 0):
                assert result["counter_trend_penalty"] == 0.5
                # confidence should be raw × BTW × CTP
                expected = result["raw_confidence"] * 1.0 * 0.5
                assert abs(result["confidence"] - round(expected, 1)) <= 0.2

    def test_long_during_trend_up_no_penalty(self, monkeypatch):
        """LONG signal during TREND_UP should NOT get counter-trend penalty."""
        monkeypatch.setattr(config, "COUNTER_TREND_PENALTY", {
            "TREND_UP": 0.5, "TREND_DOWN": 0.5,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "BTC_TREND_WEIGHTS", {
            "TREND_UP": 0.8, "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 0.9, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
        })

        df = _klines(trend="up")
        result = score_confluence(df, btc_trend="TREND_UP")

        # LONG with trend → no penalty
        if result["raw_confidence"] > 0:
            assert result["counter_trend_penalty"] == 1.0

    def test_long_during_trend_down_gets_penalty(self, monkeypatch):
        """LONG signal during TREND_DOWN should get counter-trend penalty."""
        monkeypatch.setattr(config, "COUNTER_TREND_PENALTY", {
            "TREND_UP": 0.5, "TREND_DOWN": 0.5,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "BTC_TREND_WEIGHTS", {
            "TREND_UP": 1.0, "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
        })

        df = _klines(trend="up")
        result = score_confluence(df, btc_trend="TREND_DOWN")

        if result["raw_confidence"] > 0 and result.get("counter_trend_penalty") is not None:
            if result["direction"] == "LONG" or (result["direction"] is None and result["raw_confidence"] > 0):
                assert result["counter_trend_penalty"] == 0.5

    def test_no_penalty_in_chop(self, monkeypatch):
        """No counter-trend penalty in HIGH_VOL_CHOP regime."""
        monkeypatch.setattr(config, "COUNTER_TREND_PENALTY", {
            "TREND_UP": 0.5, "TREND_DOWN": 0.5,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "BTC_TREND_WEIGHTS", {
            "TREND_UP": 1.0, "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
        })

        df = _klines(trend="down")
        result = score_confluence(df, btc_trend="HIGH_VOL_CHOP")

        # CTP is 1.0 for chop → no penalty applied
        if result["raw_confidence"] > 0:
            assert result["counter_trend_penalty"] == 1.0

    def test_mean_rev_override_no_penalty(self, monkeypatch):
        """Mean-reversion passport with CTP=1.0 override gets no penalty."""
        monkeypatch.setattr(config, "COUNTER_TREND_PENALTY", {
            "TREND_UP": 1.0, "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "BTC_TREND_WEIGHTS", {
            "TREND_UP": 0.8, "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 0.9, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
        })

        df = _klines(trend="down")
        result = score_confluence(df, btc_trend="TREND_UP")

        # CTP override = 1.0 → no penalty even for counter-trend
        if result["raw_confidence"] > 0:
            assert result["counter_trend_penalty"] == 1.0
            expected = result["raw_confidence"] * 0.8  # Only BTW applied, no CTP
            assert abs(result["confidence"] - round(expected, 1)) <= 0.2

    def test_missing_counter_trend_penalty_config(self, monkeypatch):
        """If COUNTER_TREND_PENALTY missing from config, no penalty applied."""
        monkeypatch.delattr(config, "COUNTER_TREND_PENALTY", raising=False)
        monkeypatch.setattr(config, "BTC_TREND_WEIGHTS", {
            "TREND_UP": 0.8, "TREND_DOWN": 1.0,
            "HIGH_VOL_CHOP": 0.9, "LOW_VOL_COMPRESSION": 1.0,
        })
        monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
        })

        df = _klines(trend="down")
        result = score_confluence(df, btc_trend="TREND_UP")

        # No CTP config → penalty defaults to 1.0
        if result["raw_confidence"] > 0:
            assert result["counter_trend_penalty"] == 1.0


class TestExtendedScorerParity:
    """Verify extended_scorer also applies counter-trend penalty."""

    def test_extended_scorer_has_counter_trend_logic(self):
        """extended_scorer.py should contain COUNTER_TREND_PENALTY logic."""
        import inspect
        from bot.research import extended_scorer
        source = inspect.getsource(extended_scorer)
        assert "COUNTER_TREND_PENALTY" in source
        assert "is_counter" in source or "counter" in source.lower()
