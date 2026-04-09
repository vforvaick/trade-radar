"""Tests for PassportRunner 4-regime integration."""
import json
import os
import tempfile
from unittest.mock import patch
from bot import config


def _make_mock_state_store(MockStateStore, tmpdir=None):
    mock_ss = MockStateStore.return_value
    mock_ss.get_last_equity.return_value = None
    mock_ss.load_open_positions.return_value = []
    if tmpdir:
        import os
        mock_ss.db_path = os.path.join(tmpdir, "test_state.db")
    else:
        mock_ss.db_path = ":memory:"
    return mock_ss


def test_old_btc_weights_warning(capsys):
    """PassportRunner warns about old 3-key BTC_TREND_WEIGHTS format."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestOld",
        "emoji": "🧪",
        "config_overrides": {
            "BTC_TREND_WEIGHTS": {"Uptrend": 1.0, "Sideways": 1.0, "Downtrend": 1.0},
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_old.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore") as MockStateStore:
            _make_mock_state_store(MockStateStore)
            runner = PassportRunner(tmpdir)

    captured = capsys.readouterr()
    assert "old 3-regime" in captured.out.lower() or "migrate" in captured.out.lower()


def test_regime_guardrails_uses_4_regime_names():
    """_apply_regime_guardrails checks for HIGH_VOL_CHOP instead of old Sideways."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestReversal",
        "emoji": "🔄",
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 2.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0, "REVERSAL_MODE": True,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_reversal.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore") as MockStateStore:
            _make_mock_state_store(MockStateStore)
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    original_threshold = config.CONFIDENCE_THRESHOLD

    # Set btc_trend to HIGH_VOL_CHOP (new name for sideways-like)
    runner.scanner.btc_trend = "HIGH_VOL_CHOP"
    original_config = runner._save_config(passport.config_overrides.keys())
    runner._apply_overrides(passport.config_overrides)
    runner._apply_regime_guardrails(passport)

    assert config.CONFIDENCE_THRESHOLD >= config.REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD

    runner._restore_config(original_config)
    assert config.CONFIDENCE_THRESHOLD == original_threshold


def test_active_regimes_phase1_logs_hypothetical_skip(capsys):
    """Phase 1: active_regimes is parsed from JSON, logged but NOT enforced."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestActiveRegimes",
        "emoji": "🎯",
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_active.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore") as MockStateStore:
            _make_mock_state_store(MockStateStore)
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    assert passport.active_regimes == ["TREND_UP", "TREND_DOWN"]


def test_active_regimes_null_means_all(capsys):
    """active_regimes: null (or absent) means passport runs in all regimes."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestAllRegimes",
        "emoji": "🌍",
        "active_regimes": None,
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_all.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore") as MockStateStore:
            _make_mock_state_store(MockStateStore)
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    assert passport.active_regimes is None

