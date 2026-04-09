"""Integration tests for 4-regime system end-to-end."""
import json
import os
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock
from datetime import datetime

from bot import config


def _make_passport_json(tmpdir, name="IntTest", enabled=True):
    """Create a minimal passport JSON for testing."""
    data = {
        "name": name,
        "emoji": "🧪",
        "enabled": enabled,
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }
    fpath = os.path.join(tmpdir, f"{name.lower()}.json")
    with open(fpath, "w") as f:
        json.dump(data, f)
    return fpath


def test_passport_runner_has_regime_logger():
    """PassportRunner creates a RegimeLogger on init."""
    from bot.passport_runner import PassportRunner
    from bot.regime_logger import RegimeLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        _make_passport_json(tmpdir)
        db_path = os.path.join(tmpdir, "test_state.db")
        with patch("bot.passport_runner.StateStore") as MockStore:
            MockStore.return_value.load_open_positions.return_value = []
            MockStore.return_value.get_last_equity.return_value = None
            MockStore.return_value.db_path = db_path
            runner = PassportRunner(tmpdir)

    assert hasattr(runner, "regime_logger")
    assert isinstance(runner.regime_logger, RegimeLogger)


def test_scan_cycle_logs_regime_snapshot():
    """run_scan_cycle() calls regime_logger.log_scan() at end."""
    from bot.passport_runner import PassportRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        _make_passport_json(tmpdir)
        db_path = os.path.join(tmpdir, "test_state.db")
        with patch("bot.passport_runner.StateStore") as MockStore:
            MockStore.return_value.load_open_positions.return_value = []
            MockStore.return_value.get_last_equity.return_value = None
            MockStore.return_value.db_path = db_path
            runner = PassportRunner(tmpdir)

    runner.regime_logger = MagicMock()
    runner.scanner.symbols = []
    runner.scanner.btc_trend = "TREND_UP"
    runner.scanner.regime_metadata = {"regime": "TREND_UP", "adx": 30.0}

    with patch.object(runner.scanner, "update_btc_trend"):
        runner.run_scan_cycle()

    runner.regime_logger.log_scan.assert_called_once()
