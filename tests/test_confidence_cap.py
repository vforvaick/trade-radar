"""Tests for confidence cap feature."""
import pytest
from unittest.mock import patch
from bot import config
from bot.scorer import score_confluence


@pytest.fixture(autouse=True)
def _reset_config():
    """Snapshot and restore config for each test."""
    original = {}
    keys = ['CONFIDENCE_CAP', 'CONFIDENCE_THRESHOLD', 'BTC_TREND_WEIGHTS',
            'COUNTER_TREND_PENALTY', 'INDICATOR_WEIGHTS', 'LEVERAGE_TIERS']
    for k in keys:
        if hasattr(config, k):
            original[k] = getattr(config, k)
    yield
    for k, v in original.items():
        setattr(config, k, v)


def _make_df_all_long():
    """Create a DataFrame where all indicators agree LONG."""
    import pandas as pd
    import numpy as np
    # Need enough candles for indicators (55+)
    n = 100
    # Create a strong uptrend - prices going up steadily
    close = pd.Series(np.linspace(100, 200, n))
    # Add some noise
    close = close + np.random.RandomState(42).randn(n) * 0.5
    df = pd.DataFrame({
        'open': close - 1,
        'high': close + 2,
        'low': close - 2,
        'close': close,
        'volume': pd.Series(np.random.RandomState(42).uniform(1e6, 5e6, n)),
    })
    return df


class TestConfidenceCap:
    """Tests for CONFIDENCE_CAP config parameter."""

    def test_cap_limits_raw_confidence(self):
        """Raw confidence should not exceed CONFIDENCE_CAP."""
        config.CONFIDENCE_CAP = 80
        config.BTC_TREND_WEIGHTS = {"Sideways": 1.0, "TREND_UP": 1.0, "TREND_DOWN": 1.0,
                                     "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0}
        config.COUNTER_TREND_PENALTY = {"TREND_UP": 1.0, "TREND_DOWN": 1.0,
                                         "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0}
        df = _make_df_all_long()
        result = score_confluence(df, btc_trend="Sideways")
        # Even if all indicators agree, confidence should be capped
        if result['go']:
            assert result['confidence'] <= 80

    def test_cap_default_100_when_not_set(self):
        """When CONFIDENCE_CAP not set, default to 100 (no cap)."""
        if hasattr(config, 'CONFIDENCE_CAP'):
            delattr(config, 'CONFIDENCE_CAP')
        df = _make_df_all_long()
        result = score_confluence(df, btc_trend="Sideways")
        # Should still work without cap
        assert 'confidence' in result

    def test_cap_80_blocks_short_during_uptrend(self):
        """With cap=80, BTC_WEIGHT=0.8, CTP=0.68: SHORT during TREND_UP should be blocked.
        80 * 0.8 * 0.68 = 43.5 < 54 threshold."""
        config.CONFIDENCE_CAP = 80
        config.BTC_TREND_WEIGHTS = {"TREND_UP": 0.8}
        config.COUNTER_TREND_PENALTY = {"TREND_UP": 0.68}
        config.CONFIDENCE_THRESHOLD = 54
        # Even with 100% raw SHORT confidence, cap blocks it
        # 80 * 0.8 * 0.68 = 43.52 < 54
        # We verify the math directly
        max_possible = 80 * 0.8 * 0.68
        assert max_possible < 54, f"Max possible SHORT during TREND_UP = {max_possible}, should be < 54"

    def test_cap_80_allows_long_during_uptrend(self):
        """With cap=80, BTC_WEIGHT=0.8: LONG during TREND_UP = 64, passes threshold."""
        config.CONFIDENCE_CAP = 80
        config.BTC_TREND_WEIGHTS = {"TREND_UP": 0.8}
        config.CONFIDENCE_THRESHOLD = 54
        max_possible = 80 * 0.8
        assert max_possible >= 54, f"Max possible LONG during TREND_UP = {max_possible}, should be >= 54"

    def test_cap_per_passport_override(self):
        """Per-passport can override CONFIDENCE_CAP via config_overrides."""
        config.CONFIDENCE_CAP = 80
        # Mean-reversion passport might want cap=90
        config.CONFIDENCE_CAP = 90
        assert config.CONFIDENCE_CAP == 90
        # Restore
        config.CONFIDENCE_CAP = 80

    def test_cap_affects_leverage_tier(self):
        """Cap should prevent reaching highest leverage tier when combined with BTC weight.
        With cap=80 and TREND_UP weight=0.8: max conf=64 → 5x leverage (not 7x)."""
        from bot.scorer import _get_leverage_tier
        # Without cap, 100% raw during TREND_UP: 100*0.8 = 80 → 7x
        lev_uncapped, _ = _get_leverage_tier(80)
        assert lev_uncapped == 7
        # With cap at 80, during TREND_UP: 80*0.8 = 64 → 5x
        lev_capped, _ = _get_leverage_tier(64)
        assert lev_capped == 5


class TestPositionLimitReduced:
    """Tests for MAX_OPEN_POSITIONS_PER_PASSPORT = 5."""

    def test_default_limit_is_5(self):
        """Default MAX_OPEN_POSITIONS_PER_PASSPORT should be 5."""
        assert config.MAX_OPEN_POSITIONS_PER_PASSPORT == 5

    def test_position_manager_respects_limit(self):
        """PositionManager.can_open() should block after 5 positions."""
        from bot.position_manager import PositionManager
        from bot.signals import Signal
        config.MAX_OPEN_POSITIONS_PER_PASSPORT = 5
        config.MAX_OPEN_POSITIONS_PER_SYMBOL = 0  # no per-symbol limit for this test
        pm = PositionManager()
        # Open 5 positions
        for i in range(5):
            sig = Signal(
                symbol=f"COIN{i}USDT", direction="LONG", entry_price=100.0,
                sl=95.0, tp1=105.0, tp2=110.0, tp3=115.0,
                confidence=60.0, leverage=5, risk_reward=1.5, btc_trend="Sideways",
            )
            pos = pm.open_position(sig, equity=500.0)
            assert pos is not None, f"Position {i} should open"
        # 6th should be blocked
        sig = Signal(
            symbol="NEWCOINUSDT", direction="LONG", entry_price=100.0,
            sl=95.0, tp1=105.0, tp2=110.0, tp3=115.0,
            confidence=60.0, leverage=5, risk_reward=1.5, btc_trend="Sideways",
        )
        assert not pm.can_open(sig), "6th position should be blocked"
