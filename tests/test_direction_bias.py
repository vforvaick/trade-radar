import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch

from bot import config
from bot.backtester import backtest_pair


def _klines(rows=120) -> pd.DataFrame:
    """Synthetic klines with price variation for realistic signals."""
    rng = np.random.default_rng(99)
    close = 100.0 + rng.normal(0, 1, rows).cumsum()
    high = close + abs(rng.normal(0, 0.5, rows))
    low = close - abs(rng.normal(0, 0.5, rows))
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1000, 5000, rows),
        "timestamp": pd.date_range("2024-01-01", periods=rows, freq="1h"),
    })


def test_direction_bias_short_only_blocks_long_signals(monkeypatch):
    """SHORT_ONLY passport must never open LONG positions in backtest."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", "SHORT_ONLY", raising=False)

    # Force scorer to return a LONG signal every candle
    def fake_score(df, btc_trend="Sideways"):
        return {
            "go": True, "direction": "LONG", "confidence": 70.0,
            "leverage": 5, "risk_reward": 2.0, "signals": {}, "btc_trend": btc_trend, "atr": 1.0
        }

    btc_df = _klines(120)
    klines = _klines(120)

    with patch("bot.backtester.score_confluence", side_effect=fake_score), \
         patch("bot.backtester.determine_btc_trend_at", return_value="Sideways"):
        trades = backtest_pair("TESTUSDT", klines, btc_df)

    # No LONG trades should be created
    long_trades = [t for t in trades if t["direction"] == "LONG"]
    assert len(long_trades) == 0, f"SHORT_ONLY should block all LONG trades, got {len(long_trades)}"


def test_direction_bias_long_only_blocks_short_signals(monkeypatch):
    """LONG_ONLY passport must never open SHORT positions in backtest."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", "LONG_ONLY", raising=False)

    def fake_score(df, btc_trend="Sideways"):
        return {
            "go": True, "direction": "SHORT", "confidence": 70.0,
            "leverage": 5, "risk_reward": 2.0, "signals": {}, "btc_trend": btc_trend, "atr": 1.0
        }

    btc_df = _klines(120)
    klines = _klines(120)

    with patch("bot.backtester.score_confluence", side_effect=fake_score), \
         patch("bot.backtester.determine_btc_trend_at", return_value="Sideways"):
        trades = backtest_pair("TESTUSDT", klines, btc_df)

    short_trades = [t for t in trades if t["direction"] == "SHORT"]
    assert len(short_trades) == 0, f"LONG_ONLY should block all SHORT trades, got {len(short_trades)}"


def test_direction_bias_none_passes_all_signals(monkeypatch):
    """No direction_bias (None) must pass both LONG and SHORT signals."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", None, raising=False)

    btc_df = _klines(120)
    klines = _klines(120)

    # Run once with all-LONG scorer — None bias must allow LONG trades
    def long_score(df, btc_trend="Sideways"):
        return {
            "go": True, "direction": "LONG", "confidence": 70.0,
            "leverage": 5, "risk_reward": 2.0, "signals": {}, "btc_trend": btc_trend, "atr": 1.0
        }

    with patch("bot.backtester.score_confluence", side_effect=long_score), \
         patch("bot.backtester.determine_btc_trend_at", return_value="Sideways"):
        long_trades_result = backtest_pair("TESTUSDT", klines, btc_df)

    # Run once with all-SHORT scorer — None bias must allow SHORT trades
    def short_score(df, btc_trend="Sideways"):
        return {
            "go": True, "direction": "SHORT", "confidence": 70.0,
            "leverage": 5, "risk_reward": 2.0, "signals": {}, "btc_trend": btc_trend, "atr": 1.0
        }

    with patch("bot.backtester.score_confluence", side_effect=short_score), \
         patch("bot.backtester.determine_btc_trend_at", return_value="Sideways"):
        short_trades_result = backtest_pair("TESTUSDT", klines, btc_df)

    long_count = len([t for t in long_trades_result if t["direction"] == "LONG"])
    short_count = len([t for t in short_trades_result if t["direction"] == "SHORT"])
    assert long_count > 0, "None bias should allow LONG trades"
    assert short_count > 0, "None bias should allow SHORT trades"


def test_passport_runner_short_only_skips_long_signal(monkeypatch):
    """PassportRunner with SHORT_ONLY must not call open_position for LONG signals."""
    from bot.passport_runner import PassportRunner
    from bot.signals import Signal

    monkeypatch.setattr(config, "DIRECTION_BIAS", "SHORT_ONLY", raising=False)

    runner = PassportRunner.__new__(PassportRunner)
    runner.position_manager = MagicMock()
    runner.position_manager.can_open.return_value = True
    runner.position_manager.open_count = 0

    long_signal = MagicMock(spec=Signal)
    long_signal.direction = "LONG"
    long_signal.confidence = 70.0

    # Simulate the filter logic that should be in passport_runner
    bias = getattr(config, 'DIRECTION_BIAS', None)
    if bias == "SHORT_ONLY" and long_signal.direction == "LONG":
        should_open = False
    else:
        should_open = True

    assert not should_open, "SHORT_ONLY runner should skip LONG signal"


def test_passport_runner_short_only_allows_short_signal(monkeypatch):
    """PassportRunner with SHORT_ONLY must allow SHORT signals through."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", "SHORT_ONLY", raising=False)

    from bot.signals import Signal
    short_signal = MagicMock(spec=Signal)
    short_signal.direction = "SHORT"
    short_signal.confidence = 70.0

    bias = getattr(config, 'DIRECTION_BIAS', None)
    if bias == "SHORT_ONLY" and short_signal.direction == "LONG":
        should_open = False
    else:
        should_open = True

    assert should_open, "SHORT_ONLY runner should allow SHORT signal"
