"""Tests for calc audit bug fixes in stage4.py and extended_scorer.py."""
import pytest
from unittest.mock import patch

from bot.research.stage4 import calc_trade_overlap, calc_composite_utility
from bot.research import extended_scorer
from bot import config


def test_stage4_trade_overlap_overlapping():
    trades_a = [{"symbol": "BTCUSDT", "direction": "long", "entry_time": "2024-01-15T08:00:00", "exit_time": "2024-01-15T12:00:00"}]
    trades_b = [{"symbol": "BTCUSDT", "direction": "long", "entry_time": "2024-01-15T10:00:00", "exit_time": "2024-01-15T14:00:00"}]
    assert calc_trade_overlap(trades_a, trades_b) > 0


def test_stage4_trade_overlap_non_overlapping():
    trades_a = [{"symbol": "BTCUSDT", "direction": "long", "entry_time": "2024-01-15T08:00:00", "exit_time": "2024-01-15T10:00:00"}]
    trades_b = [{"symbol": "BTCUSDT", "direction": "long", "entry_time": "2024-01-15T12:00:00", "exit_time": "2024-01-15T14:00:00"}]
    assert calc_trade_overlap(trades_a, trades_b) == 0.0


def test_stage4_composite_utility_zero_dd_beats_nonzero():
    utility_zero_dd = calc_composite_utility(sharpe=1.0, calmar=1.0, max_dd=0)
    utility_with_dd = calc_composite_utility(sharpe=1.0, calmar=1.0, max_dd=5)
    assert utility_zero_dd > utility_with_dd


# --- H1: extended_scorer uses live config.BTC_TREND_WEIGHTS, not old hardcoded values ---

def _make_fake_df(rows=60):
    """Return a minimal DataFrame-like object that passes the length check."""
    import pandas as pd
    import numpy as np
    rng = np.random.default_rng(42)
    close = 100 + rng.normal(0, 1, rows).cumsum()
    high = close + abs(rng.normal(0, 0.5, rows))
    low = close - abs(rng.normal(0, 0.5, rows))
    volume = rng.uniform(1000, 5000, rows)
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": volume})


def _all_long_registry():
    """Return a patched INDICATOR_REGISTRY where every indicator returns LONG."""
    return {k: (lambda df: ("LONG", 50.0)) for k in extended_scorer.INDICATOR_REGISTRY}


def test_h1_uptrend_uses_config_weight_not_hardcoded():
    """TREND_UP multiplier must come from config (0.8), not old hardcoded 1.15."""
    df = _make_fake_df()
    weights = {"ema_trend": 1.0}

    # Disable CTP to isolate BTC_TREND_WEIGHTS test
    no_penalty = {"TREND_UP": 1.0, "TREND_DOWN": 1.0, "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0}
    with patch.dict(extended_scorer.INDICATOR_REGISTRY, _all_long_registry(), clear=True), \
         patch.object(config, "COUNTER_TREND_PENALTY", no_penalty):
        result = extended_scorer.score_extended(df, weights, btc_trend="TREND_UP", confidence_threshold=0.0)

    # raw_confidence = 100.0 when all votes LONG on a single-indicator weight
    # with config.BTC_TREND_WEIGHTS["TREND_UP"] = 0.8 → confidence = 80.0
    assert result["go"] is True
    assert abs(result["confidence"] - 100.0 * config.BTC_TREND_WEIGHTS["TREND_UP"]) < 0.1
    assert result["confidence"] != pytest.approx(115.0, abs=0.1), "H1 bug: old hardcoded 1.15 weight still in use"


def test_h1_downtrend_uses_config_weight():
    """TREND_DOWN multiplier must come from config (1.0), not old hardcoded 0.85."""
    df = _make_fake_df()
    weights = {"ema_trend": 1.0}

    # Disable CTP to isolate BTC_TREND_WEIGHTS test
    no_penalty = {"TREND_UP": 1.0, "TREND_DOWN": 1.0, "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0}
    with patch.dict(extended_scorer.INDICATOR_REGISTRY, _all_long_registry(), clear=True), \
         patch.object(config, "COUNTER_TREND_PENALTY", no_penalty):
        result = extended_scorer.score_extended(df, weights, btc_trend="TREND_DOWN", confidence_threshold=0.0)

    expected = min(100.0, 100.0 * config.BTC_TREND_WEIGHTS["TREND_DOWN"])
    assert abs(result["confidence"] - expected) < 0.1


# --- H2: confidence is clamped to [0, 100] ---

def test_h2_confidence_clamped_to_100():
    """Even if BTC_TREND_WEIGHTS were >1.0, confidence must never exceed 100."""
    df = _make_fake_df()
    weights = {"ema_trend": 1.0}

    with patch.dict(extended_scorer.INDICATOR_REGISTRY, _all_long_registry(), clear=True):
        # Temporarily set a weight >1 to provoke the overflow
        original_weights = config.BTC_TREND_WEIGHTS.copy()
        config.BTC_TREND_WEIGHTS["TREND_UP"] = 1.5
        try:
            result = extended_scorer.score_extended(df, weights, btc_trend="TREND_UP", confidence_threshold=0.0)
        finally:
            config.BTC_TREND_WEIGHTS["TREND_UP"] = original_weights["TREND_UP"]

    assert result["confidence"] <= 100.0, f"H2 bug: confidence={result['confidence']} exceeds 100"


def test_h2_confidence_not_negative():
    """Confidence must never be negative."""
    df = _make_fake_df()
    weights = {"ema_trend": 1.0}

    with patch.dict(extended_scorer.INDICATOR_REGISTRY, _all_long_registry(), clear=True):
        original_weights = config.BTC_TREND_WEIGHTS.copy()
        config.BTC_TREND_WEIGHTS["TREND_UP"] = -0.5
        try:
            result = extended_scorer.score_extended(df, weights, btc_trend="TREND_UP", confidence_threshold=0.0)
        finally:
            config.BTC_TREND_WEIGHTS["TREND_UP"] = original_weights["TREND_UP"]

    assert result["confidence"] >= 0.0, f"H2 bug: confidence={result['confidence']} is negative"


# --- H4: regime mapping to live names, M4: 1H annualization ---

from bot.research.regime import map_to_live_regime, map_regime_value_to_live
from bot.research.types import RegimeType


def test_regime_map_to_live_trend_up():
    assert map_to_live_regime(RegimeType.TREND_UP) == "TREND_UP"


def test_regime_map_to_live_trend_down():
    assert map_to_live_regime(RegimeType.TREND_DOWN) == "TREND_DOWN"


def test_regime_map_to_live_high_vol_chop():
    assert map_to_live_regime(RegimeType.HIGH_VOL_CHOP) == "HIGH_VOL_CHOP"


def test_regime_map_to_live_low_vol_compression():
    assert map_to_live_regime(RegimeType.LOW_VOL_COMPRESSION) == "LOW_VOL_COMPRESSION"


def test_regime_map_value_to_live_downtrend():
    assert map_regime_value_to_live("TREND_DOWN") == "TREND_DOWN"


def test_regime_map_value_to_live_uptrend():
    assert map_regime_value_to_live("TREND_UP") == "TREND_UP"


def test_regime_map_value_to_live_unknown_defaults_high_vol_chop():
    assert map_regime_value_to_live("UNKNOWN") == "HIGH_VOL_CHOP"


# --- M4: _calc_realized_vol candles_per_year param ---

def test_m4_calc_realized_vol_default_is_1h():
    """Default candles_per_year must be 365*24=8760, not the old 252*6=1512."""
    import inspect
    from bot.research.regime import _calc_realized_vol
    sig = inspect.signature(_calc_realized_vol)
    assert sig.parameters["candles_per_year"].default == 365 * 24, (
        f"Expected default 8760, got {sig.parameters['candles_per_year'].default}"
    )

def test_m4_calc_realized_vol_candles_per_year_affects_output():
    """Higher candles_per_year → higher annualized vol (same raw data)."""
    import pandas as pd
    import numpy as np
    from bot.research.regime import _calc_realized_vol

    np.random.seed(42)
    # 50 price points, random walk
    prices = pd.Series(100 + np.random.randn(50).cumsum())

    vol_1h = _calc_realized_vol(prices, window=20, candles_per_year=365 * 24).iloc[-1]
    vol_4h = _calc_realized_vol(prices, window=20, candles_per_year=252 * 6).iloc[-1]

    # 1H has more candles per year → scales up more → higher vol
    assert vol_1h > vol_4h, (
        f"1H vol ({vol_1h:.4f}) should exceed 4H vol ({vol_4h:.4f})"
    )
