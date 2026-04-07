"""Tests for L1/L2/L3 bug fixes in bot/indicators.py."""
import numpy as np
import pandas as pd
import pytest

from bot.indicators import calc_rsi, calc_macd, calc_obv_signal


def _make_df(closes, volumes=None):
    """Build a minimal DataFrame with 'close' and 'volume' columns."""
    closes = list(closes)
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    return pd.DataFrame({"close": closes, "volume": volumes})


# ---------------------------------------------------------------------------
# L1 — RSI ffill before fillna(50)
# ---------------------------------------------------------------------------

class TestRSIFfill:
    def test_no_spurious_50s_in_valid_range(self):
        """After the warmup period, a mixed-signal series must not contain spurious 50s."""
        import random
        rng = random.Random(42)
        closes = [100.0]
        for _ in range(200):
            closes.append(closes[-1] * (1 + rng.uniform(-0.02, 0.025)))
        df = _make_df(closes)
        rsi = calc_rsi(df)
        valid = rsi.iloc[14:]  # after default period=14 warmup
        assert not (valid == 50.0).any(), "No spurious 50s should appear in valid RSI range"

    def test_uptrend_gives_high_rsi(self):
        """Mixed-then-strong-uptrend series ends with RSI well above 50."""
        # 60 mixed candles (to seed valid avg_loss) then 40 all-up candles
        mixed = [100 + (-1)**i * (i % 5) for i in range(60)]
        uptrend = [mixed[-1] + i for i in range(1, 41)]
        df = _make_df(mixed + uptrend)
        rsi = calc_rsi(df)
        assert rsi.iloc[-1] > 65, f"Strong uptrend should give RSI > 65, got {rsi.iloc[-1]}"

    def test_downtrend_gives_low_rsi(self):
        """Mixed-then-strong-downtrend series ends with RSI well below 50."""
        mixed = [100 + (-1)**i * (i % 5) for i in range(60)]
        downtrend = [mixed[-1] - i for i in range(1, 41)]
        df = _make_df(mixed + downtrend)
        rsi = calc_rsi(df)
        assert rsi.iloc[-1] < 35, f"Strong downtrend should give RSI < 35, got {rsi.iloc[-1]}"

    def test_warmup_nans_filled_with_50(self):
        """NaN warmup values (before min_periods) fall back to 50."""
        # Purely increasing series: avg_loss=0 throughout → RS=nan the whole time
        # ffill has nothing to propagate, so fallback 50 is correct
        closes = list(range(100, 120))  # 20 values, period=14
        df = _make_df(closes)
        rsi = calc_rsi(df)
        # All RSI values should be 50 (no losses ever → avg_loss=0 → RS=nan, ffill does nothing)
        assert (rsi == 50.0).all(), f"All-gain series should yield all-50 RSI, got {rsi.tolist()}"

    def test_ffill_preserves_valid_rsi_through_flat_suffix(self):
        """After a valid RSI is computed, a sudden flat period doesn't reset RSI to 50.

        Because EWM avg_loss decays gradually (never instantly hits 0.0), RSI stays
        above 50 when the prior trend was upward.  This verifies ffill doesn't break
        the continuation of a valid computation.
        """
        mixed = [100 + (-1)**i * (i % 5) for i in range(60)]
        upward = [mixed[-1] + i * 0.5 for i in range(1, 41)]
        flat = [upward[-1]] * 20
        df = _make_df(mixed + upward + flat)
        rsi = calc_rsi(df)
        # After a strong uptrend, flat candles should keep RSI > 50 (EWM decays slowly)
        assert rsi.iloc[-1] > 50, (
            f"RSI after uptrend + flat period should remain > 50, got {rsi.iloc[-1]}"
        )


# ---------------------------------------------------------------------------
# L2 — MACD early-return guard for short DataFrames
# ---------------------------------------------------------------------------

class TestMACDLenGuard:
    def test_too_few_bars_returns_neutral(self):
        """DataFrame with < 35 bars (26 + 9) returns NEUTRAL, 0 without crashing."""
        df = _make_df(range(100, 130))  # 30 rows < 35
        direction, value = calc_macd(df)
        assert direction == "NEUTRAL"
        assert value == 0

    def test_exactly_at_boundary_returns_neutral(self):
        """DataFrame with exactly slow+signal-1 bars returns NEUTRAL."""
        df = _make_df(range(100, 134))  # 34 rows = 26+9-1
        direction, value = calc_macd(df)
        assert direction == "NEUTRAL"
        assert value == 0

    def test_sufficient_bars_does_not_crash(self):
        """DataFrame with enough bars runs normally and returns a valid direction."""
        closes = [100 + i * 0.5 for i in range(60)]
        df = _make_df(closes)
        direction, value = calc_macd(df)
        assert direction in ("LONG", "SHORT", "NEUTRAL")
        assert isinstance(value, (int, float))

    def test_empty_dataframe_returns_neutral(self):
        """Empty DataFrame does not crash."""
        df = _make_df([])
        direction, value = calc_macd(df)
        assert direction == "NEUTRAL"
        assert value == 0


# ---------------------------------------------------------------------------
# L3 — OBV gap_pct overflow cap
# ---------------------------------------------------------------------------

class TestOBVGapPctCap:
    def _make_obv_df(self, closes, volumes):
        return pd.DataFrame({"close": closes, "volume": volumes})

    def test_near_zero_ema_does_not_overflow(self):
        """Near-zero OBV EMA does not cause float overflow; gap_pct is capped."""
        # Alternating tiny volume so OBV EMA stays near zero
        # but last OBV is large (many high-volume up candles at the end)
        n = 50
        closes = [100.0] * n
        # Alternating +/- to keep OBV near zero for warmup, then spike
        volumes = [1] * (n - 2) + [1e15, 1e15]
        closes[-2] = 101.0
        closes[-1] = 102.0
        df = self._make_obv_df(closes, volumes)
        # Should not raise OverflowError or return inf/nan
        direction, strength = calc_obv_signal(df)
        assert np.isfinite(strength), f"strength should be finite, got {strength}"
        assert 0.0 <= strength <= 1.0, f"strength should be in [0,1], got {strength}"

    def test_strength_capped_at_one(self):
        """strength is always in [0.0, 1.0] regardless of OBV/EMA ratio."""
        closes = [float(i) for i in range(1, 52)]
        volumes = [1e12] * 51  # massive volume → huge OBV relative to EMA
        df = self._make_obv_df(closes, volumes)
        direction, strength = calc_obv_signal(df)
        assert strength <= 1.0, f"strength must be <= 1.0, got {strength}"
        assert np.isfinite(strength)

    def test_gap_pct_cap_prevents_extreme_values(self):
        """Directly verify gap_pct cap: simulate OBV >> EMA scenario."""
        # We can't inspect gap_pct directly, but strength capped at 1.0 proves it
        closes = [100.0 + i for i in range(51)]
        volumes = [1] * 25 + [1e20] * 26  # sudden enormous volume
        df = self._make_obv_df(closes, volumes)
        direction, strength = calc_obv_signal(df)
        assert np.isfinite(strength)
        assert strength <= 1.0
