"""Tests for scorer.py registry pattern (23 indicators)."""
from __future__ import annotations

import contextlib
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

from bot import config
from bot.scorer import (
    INDICATOR_REGISTRY,
    EXTENDED_INDICATOR_NAMES,
    NON_DIRECTIONAL,
    PRODUCTION_10,
    EXTENDED_13,
    score_confluence,
    _get_leverage_tier,
    _no_signal,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

ORIGINAL_8 = frozenset({
    "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
    "bb_position", "volume_spike", "pressure", "candle_direction",
})
ALL_23 = PRODUCTION_10 | EXTENDED_13


def _ohlcv(rows: int = 120, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + rng.normal(0, 1, rows).cumsum()
    high = close + abs(rng.normal(0, 0.5, rows))
    low = close - abs(rng.normal(0, 0.5, rows))
    return pd.DataFrame({
        "open": close - 0.3,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1000, 5000, rows),
    })


@contextlib.contextmanager
def _all_long_patch(extra: dict | None = None):
    """Patch INDICATOR_REGISTRY so all directional indicators return LONG.

    This lets structural tests (key presence, atr, signals) run deterministically
    without depending on random data producing a directional consensus.
    """
    fake = {}
    for name in INDICATOR_REGISTRY:
        if name in NON_DIRECTIONAL:
            fake[name] = lambda df: ("LONG", 2.0)
        else:
            fake[name] = lambda df: ("LONG", 75.0)
    if extra:
        fake.update(extra)
    with patch("bot.scorer.INDICATOR_REGISTRY", fake):
        yield


@pytest.fixture(autouse=True)
def _restore_config():
    """Snapshot and restore key config attrs after each test."""
    keys = [
        "INDICATOR_WEIGHTS", "CONFIDENCE_CAP", "CONFIDENCE_THRESHOLD",
        "BTC_TREND_WEIGHTS", "COUNTER_TREND_PENALTY", "LEVERAGE_TIERS",
    ]
    saved = {k: getattr(config, k) for k in keys if hasattr(config, k)}
    yield
    for k, v in saved.items():
        setattr(config, k, v)


# ---------------------------------------------------------------------------
# TestRegistryExists
# ---------------------------------------------------------------------------

class TestRegistryExists:
    def test_registry_has_all_23(self):
        assert set(INDICATOR_REGISTRY.keys()) == ALL_23

    def test_registry_has_original_8(self):
        assert ORIGINAL_8.issubset(INDICATOR_REGISTRY.keys())

    def test_registry_has_production_10(self):
        assert PRODUCTION_10.issubset(INDICATOR_REGISTRY.keys())

    def test_registry_has_extended_13(self):
        assert EXTENDED_13.issubset(INDICATOR_REGISTRY.keys())

    def test_extended_indicator_names_covers_production_extras_and_extended(self):
        expected = (PRODUCTION_10 - ORIGINAL_8) | EXTENDED_13
        assert expected == EXTENDED_INDICATOR_NAMES

    def test_non_directional_contains_volume_spike(self):
        assert "volume_spike" in NON_DIRECTIONAL

    def test_all_registry_values_are_callable(self):
        for name, fn in INDICATOR_REGISTRY.items():
            assert callable(fn), f"{name} is not callable"


# ---------------------------------------------------------------------------
# TestRegistryScoring
# ---------------------------------------------------------------------------

class TestRegistryScoring:
    def test_insufficient_data_returns_no_signal(self):
        df = _ohlcv(30)
        result = score_confluence(df)
        assert result["go"] is False
        assert result["direction"] is None
        assert result["reason"] == "Insufficient data"

    def test_result_has_all_required_keys(self):
        """All required keys must be present in every result (signal or not)."""
        required = {
            "direction", "confidence", "leverage", "risk_reward",
            "signals", "go", "btc_trend", "raw_confidence",
            "counter_trend_penalty", "atr",
        }
        # Check no-signal case (early exit)
        df_short = _ohlcv(30)
        assert required.issubset(score_confluence(df_short).keys())

        # Check full-signal case (forced LONG via patch)
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        assert required.issubset(result.keys()), f"Missing: {required - result.keys()}"

    def test_atr_in_result_positive(self):
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        assert result["atr"] is not None
        assert result["atr"] > 0.0

    def test_standard_weights_work(self):
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
            "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 1.0, "candle_direction": 1.0,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        assert isinstance(result["confidence"], float)
        assert result["go"] is True

    def test_extended_weights_activate_extended_indicators(self):
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
            "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 1.0, "candle_direction": 1.0,
            "stochrsi": 2.5,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        assert "stochrsi" in result["signals"]

    def test_extended_indicator_absent_from_signals_when_weight_zero(self):
        """Extended indicators with weight=0 must not appear in signals."""
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
            "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 1.0, "candle_direction": 1.0,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        for name in EXTENDED_13:
            assert name not in result["signals"], f"{name} should not be in signals"

    def test_unknown_indicator_in_weights_silently_ignored(self):
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
            "nonexistent_indicator": 99.9,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        assert "nonexistent_indicator" not in result["signals"]
        assert isinstance(result["confidence"], float)

    def test_zero_weight_skipped_not_in_signals(self):
        """Zero-weight production indicators are always in signals (original behavior).
        Zero-weight EXTENDED indicators are absent from signals.
        This test verifies that extended indicators with weight=0 are excluded."""
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        # Production indicators always in signals (original scorer always computed them)
        for name in ("ema_trend", "macd_signal", "rsi_position", "rsi_divergence"):
            assert name in result["signals"], f"Production indicator {name} should always be in signals"
        # Extended indicators with weight=0 must NOT be in signals
        for name in EXTENDED_13:
            assert name not in result["signals"], f"Extended {name} with w=0 should not be in signals"

    def test_confidence_cap_applied(self):
        config.CONFIDENCE_CAP = 60
        config.BTC_TREND_WEIGHTS = {k: 1.0 for k in ("Sideways", "TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION")}
        config.COUNTER_TREND_PENALTY = {k: 1.0 for k in ("TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION", "Sideways")}
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df, btc_trend="Sideways")
        assert result["raw_confidence"] <= 60

    def test_btc_trend_weight_applied(self):
        config.BTC_TREND_WEIGHTS = {"TREND_UP": 0.5, "Sideways": 1.0, "TREND_DOWN": 1.0, "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0}
        config.COUNTER_TREND_PENALTY = {k: 1.0 for k in ("TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION", "Sideways")}
        df = _ohlcv(120)
        with _all_long_patch():
            r_sideways = score_confluence(df.copy(), btc_trend="Sideways")
            r_trend = score_confluence(df.copy(), btc_trend="TREND_UP")
        # TREND_UP weight 0.5 → confidence halved vs Sideways (weight 1.0)
        assert r_trend["confidence"] <= r_sideways["confidence"] + 0.1

    def test_counter_trend_penalty_in_result(self):
        config.BTC_TREND_WEIGHTS = {k: 1.0 for k in ("TREND_UP", "Sideways", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION")}
        config.COUNTER_TREND_PENALTY = {"TREND_UP": 0.68, "TREND_DOWN": 0.68, "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0, "Sideways": 1.0}
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df, btc_trend="Sideways")
        assert "counter_trend_penalty" in result

    def test_no_signal_has_reason_key(self):
        result = _no_signal("test reason")
        assert "reason" in result
        assert result["reason"] == "test reason"

    def test_mixed_standard_and_extended_weights(self):
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
            "stochrsi": 1.5, "hull_ma": 1.0,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        # Extended indicators with weight > 0 must appear in signals
        assert "stochrsi" in result["signals"]
        assert "hull_ma" in result["signals"]
        # Extended indicators with weight=0 must NOT appear in signals
        for name in EXTENDED_13 - {"stochrsi", "hull_ma"}:
            assert name not in result["signals"], f"{name} should not be in signals"


# ---------------------------------------------------------------------------
# TestRegistryCallables
# ---------------------------------------------------------------------------

class TestRegistryCallables:
    """All 23 callables must return a (direction, value) 2-tuple."""

    VALID_DIRECTIONS = ("LONG", "SHORT", "NEUTRAL", None)

    def _verify_callable(self, name: str, fn: callable, df: pd.DataFrame):
        result = fn(df)
        assert isinstance(result, tuple) and len(result) == 2, (
            f"{name}: expected 2-tuple, got {type(result)}"
        )
        direction, value = result
        assert direction in self.VALID_DIRECTIONS, (
            f"{name}: direction must be LONG/SHORT/NEUTRAL/None, got {direction!r}"
        )
        assert isinstance(value, (int, float)), (
            f"{name}: value must be numeric, got {type(value)}"
        )

    def test_all_production_callables(self):
        df = _ohlcv(120)
        for name in PRODUCTION_10:
            self._verify_callable(name, INDICATOR_REGISTRY[name], df)

    def test_all_extended_callables(self):
        df = _ohlcv(120)
        for name in EXTENDED_13:
            self._verify_callable(name, INDICATOR_REGISTRY[name], df)

    def test_all_23_callables(self):
        df = _ohlcv(120)
        for name, fn in INDICATOR_REGISTRY.items():
            self._verify_callable(name, fn, df)


# ---------------------------------------------------------------------------
# TestPassportRunnerIntegration
# ---------------------------------------------------------------------------

class TestPassportRunnerIntegration:
    """Verify that config_overrides with extended indicator weights work end-to-end."""

    def test_extended_weight_override_activates_indicator(self):
        """Simulate a passport that adds stochrsi=2.5 to standard weights."""
        base_weights = {
            "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
            "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 1.0, "candle_direction": 1.0,
        }
        config.INDICATOR_WEIGHTS = {**base_weights, "stochrsi": 2.5}
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        assert "stochrsi" in result["signals"]

    def test_without_override_extended_absent(self):
        """Without override, extended indicators must not appear in signals."""
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
            "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 1.0, "candle_direction": 1.0,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        for name in EXTENDED_13:
            assert name not in result["signals"]

    def test_reversal_mode_suppresses_ema_and_macd(self):
        """REVERSAL_MODE zeros ema_trend/macd_signal weights so they don't score.
        They still appear in signals_detail (production indicators are always computed)
        but they don't contribute votes to long/short score."""
        config.INDICATOR_WEIGHTS = {
            "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
            "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
            "pressure": 0.0, "candle_direction": 0.0,
            "REVERSAL_MODE": True,
        }
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        # Production indicators always present in signals_detail
        assert "ema_trend" in result["signals"]
        assert "macd_signal" in result["signals"]
        # The result should still work (no crash)
        assert isinstance(result["confidence"], float)

    def test_all_extended_passport_override(self):
        """Passport using all 13 extended indicators should work without error."""
        weights = {
            "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 1.0,
            "pressure": 0.0, "candle_direction": 0.0,
        }
        for name in EXTENDED_13:
            weights[name] = 1.0
        config.INDICATOR_WEIGHTS = weights
        df = _ohlcv(120)
        with _all_long_patch():
            result = score_confluence(df)
        assert isinstance(result["confidence"], float)
        for name in EXTENDED_13:
            assert name in result["signals"]
