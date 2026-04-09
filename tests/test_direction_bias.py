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


def _make_runner_with_signals(signals, config_overrides):
    """Build a PassportRunner-like object with mocked internals for testing."""
    from bot.passport_runner import PassportRunner
    from bot.signals import Signal

    # Build a mock passport with the given config_overrides
    passport = MagicMock()
    passport.enabled = True
    passport.emoji = "🧪"
    passport.name = "TestPassport"
    passport.config_overrides = config_overrides
    passport.position_manager = MagicMock()
    passport.position_manager.can_open.return_value = True
    passport.position_manager.open_count = 0
    passport.equity = 500.0
    passport.signal_count = 0

    # Build runner with mocked scanner and state_store
    runner = PassportRunner.__new__(PassportRunner)
    runner.passports = [passport]
    runner.scan_cycle_error_count = 0
    runner.scanner = MagicMock()
    runner.scanner.scan_all.return_value = signals
    runner.state_store = MagicMock()
    runner.state_store.save_position.return_value = 1
    runner.regime_logger = MagicMock()
    runner._last_digest_date = None
    return runner, passport


def test_passport_runner_short_only_skips_long_signal():
    """PassportRunner.run_scan_cycle with SHORT_ONLY must not call open_position for LONG signals."""
    from bot.signals import Signal

    long_sig = MagicMock(spec=Signal)
    long_sig.direction = "LONG"
    long_sig.confidence = 75.0

    runner, passport = _make_runner_with_signals(
        signals=[long_sig],
        config_overrides={"DIRECTION_BIAS": "SHORT_ONLY"},
    )
    runner.run_scan_cycle()

    passport.position_manager.open_position.assert_not_called()


def test_passport_runner_short_only_allows_short_signal():
    """PassportRunner.run_scan_cycle with SHORT_ONLY must call open_position for SHORT signals."""
    from bot.signals import Signal

    short_sig = MagicMock(spec=Signal)
    short_sig.direction = "SHORT"
    short_sig.confidence = 75.0

    runner, passport = _make_runner_with_signals(
        signals=[short_sig],
        config_overrides={"DIRECTION_BIAS": "SHORT_ONLY"},
    )
    runner.run_scan_cycle()

    passport.position_manager.open_position.assert_called_once()
