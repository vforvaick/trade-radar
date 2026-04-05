# tests/test_new_indicators.py
"""Tests for calc_donchian_channel and calc_obv_signal."""
import numpy as np
import pandas as pd
import pytest
from bot.indicators import calc_donchian_channel, calc_obv_signal


def _make_df(closes, highs=None, lows=None, volumes=None):
    """Build a minimal OHLCV DataFrame."""
    arr = np.array(closes, dtype=float)
    if highs is None:
        highs = arr + 1.0
    if lows is None:
        lows = arr - 1.0
    if volumes is None:
        volumes = np.ones(len(arr)) * 1000.0
    return pd.DataFrame({
        "open": arr - 0.5,
        "high": np.array(highs, dtype=float),
        "low": np.array(lows, dtype=float),
        "close": arr,
        "volume": np.array(volumes, dtype=float),
    })


# ── Donchian Channel ─────────────────────────────────────────────────

class TestCalcDonchianChannel:
    def test_upside_breakout_returns_long(self):
        # Price stays flat at 100 for 25 bars, then breaks to 115
        closes = [100.0] * 25 + [115.0]
        highs  = [101.0] * 25 + [116.0]
        lows   = [99.0]  * 25 + [114.0]
        df = _make_df(closes, highs=highs, lows=lows)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "LONG"
        assert 0.0 < strength <= 1.0

    def test_downside_breakout_returns_short(self):
        closes = [100.0] * 25 + [85.0]
        highs  = [101.0] * 25 + [86.0]
        lows   = [99.0]  * 25 + [84.0]
        df = _make_df(closes, highs=highs, lows=lows)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "SHORT"
        assert 0.0 < strength <= 1.0

    def test_inside_channel_returns_neutral(self):
        closes = [100.0] * 25 + [100.5]
        highs  = [101.0] * 25 + [101.5]
        lows   = [99.0]  * 25 + [99.5]
        df = _make_df(closes, highs=highs, lows=lows)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "NEUTRAL"

    def test_insufficient_data_returns_neutral(self):
        df = _make_df([100.0] * 10)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "NEUTRAL"
        assert strength == 0.0

    def test_strength_capped_at_1(self):
        # Massive breakout — strength should cap at 1.0
        closes = [100.0] * 25 + [1000.0]
        highs  = [101.0] * 25 + [1001.0]
        lows   = [99.0]  * 25 + [999.0]
        df = _make_df(closes, highs=highs, lows=lows)
        _, strength = calc_donchian_channel(df, period=20)
        assert strength <= 1.0


# ── OBV Signal ───────────────────────────────────────────────────────

class TestCalcObvSignal:
    def test_rising_price_volume_returns_long(self):
        n = 40
        closes = np.linspace(100, 110, n)
        volumes = np.ones(n) * 2000.0
        df = _make_df(closes, volumes=volumes)
        direction, strength = calc_obv_signal(df, period=10)
        assert direction == "LONG"
        assert 0.0 < strength <= 1.0

    def test_falling_price_volume_returns_short(self):
        n = 40
        closes = np.linspace(110, 100, n)
        volumes = np.ones(n) * 2000.0
        df = _make_df(closes, volumes=volumes)
        direction, strength = calc_obv_signal(df, period=10)
        assert direction == "SHORT"
        assert 0.0 < strength <= 1.0

    def test_flat_price_does_not_crash(self):
        n = 40
        closes = np.ones(n) * 100.0
        volumes = np.ones(n) * 1000.0
        df = _make_df(closes, volumes=volumes)
        direction, strength = calc_obv_signal(df, period=10)
        assert direction in ("LONG", "SHORT", "NEUTRAL")
        assert 0.0 <= strength <= 1.0

    def test_insufficient_data_returns_neutral(self):
        df = _make_df([100.0] * 5)
        direction, strength = calc_obv_signal(df, period=20)
        assert direction == "NEUTRAL"
        assert strength == 0.0

    def test_strength_bounded_0_to_1(self):
        n = 50
        closes = np.linspace(100, 200, n)
        volumes = np.ones(n) * 9999.0
        df = _make_df(closes, volumes=volumes)
        _, strength = calc_obv_signal(df, period=5)
        assert 0.0 <= strength <= 1.0
