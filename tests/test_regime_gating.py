"""Tests for regime hard-gate enforcement in PassportRunner."""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from bot import config


def _make_passport_dir(tmpdir, passports_data):
    """Write passport JSON files to tmpdir."""
    for i, data in enumerate(passports_data):
        fpath = os.path.join(tmpdir, f"passport_{i}.json")
        with open(fpath, "w") as f:
            json.dump(data, f)


def _base_indicators():
    return {
        "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
        "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
        "pressure": 0.0, "candle_direction": 0.0,
    }


def _make_runner(tmpdir):
    """Create PassportRunner with mocked StateStore."""
    from bot.passport_runner import PassportRunner
    with patch("bot.passport_runner.StateStore") as MockSS:
        mock_ss = MockSS.return_value
        mock_ss.get_last_equity.return_value = None
        mock_ss.load_open_positions.return_value = []
        mock_ss.db_path = ":memory:"
        runner = PassportRunner(tmpdir)
    runner.scanner.update_btc_trend = MagicMock()
    return runner


class TestHardGate:
    """Tests for active_regimes hard gate."""

    def test_passport_skipped_when_regime_not_in_active_regimes(self, capsys):
        """Passport with active_regimes skips scan when current regime doesn't match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "TrendOnly",
                "emoji": "📈",
                "active_regimes": ["TREND_UP", "TREND_DOWN"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "HIGH_VOL_CHOP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            results = runner.run_scan_cycle()

            runner.scanner.scan_all.assert_not_called()
            captured = capsys.readouterr()
            assert "regime gate" in captured.out.lower() or "skipped" in captured.out.lower()

    def test_passport_scans_when_regime_matches_active_regimes(self):
        """Passport scans normally when current regime is in active_regimes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "TrendOnly",
                "emoji": "📈",
                "active_regimes": ["TREND_UP", "TREND_DOWN"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            results = runner.run_scan_cycle()

            runner.scanner.scan_all.assert_called_once()

    def test_passport_without_active_regimes_always_scans(self):
        """Passport without active_regimes (None) scans in any regime."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "NoGate",
                "emoji": "🌍",
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            for regime in ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"]:
                runner.scanner.btc_trend = regime
                runner.scanner.scan_all = MagicMock(return_value=[])
                runner.run_scan_cycle()
                runner.scanner.scan_all.assert_called()

    def test_passport_with_empty_active_regimes_never_scans(self):
        """Passport with active_regimes=[] never scans (effectively disabled)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "NeverTrade",
                "emoji": "🚫",
                "active_regimes": [],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            runner.run_scan_cycle()
            runner.scanner.scan_all.assert_not_called()

    def test_hard_gate_does_not_affect_disabled_passports(self, capsys):
        """Disabled passports are skipped before regime gate check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "DisabledPassport",
                "emoji": "⏸️",
                "enabled": False,
                "active_regimes": ["TREND_UP"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            runner.run_scan_cycle()
            runner.scanner.scan_all.assert_not_called()
            captured = capsys.readouterr()
            assert "disabled" in captured.out.lower() or "restored positions" in captured.out.lower()


class TestRegimeParamsOverlay:
    """Tests for regime_params config overlay."""

    def test_regime_params_override_config_overrides(self):
        """regime_params[current_regime] overrides config_overrides values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "OverlayTest",
                "emoji": "🔧",
                "active_regimes": ["TREND_UP", "HIGH_VOL_CHOP"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 54,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "HIGH_VOL_CHOP": {"CONFIDENCE_THRESHOLD": 65}
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])
            original_threshold = config.CONFIDENCE_THRESHOLD

            runner.run_scan_cycle()

            assert config.CONFIDENCE_THRESHOLD == original_threshold

    def test_regime_params_applied_during_scan(self):
        """regime_params values are active during scan_all() call."""
        captured_threshold = {}

        def capture_scan():
            captured_threshold["value"] = config.CONFIDENCE_THRESHOLD
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "CaptureTest",
                "emoji": "📸",
                "active_regimes": ["HIGH_VOL_CHOP"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 54,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "HIGH_VOL_CHOP": {"CONFIDENCE_THRESHOLD": 65}
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "HIGH_VOL_CHOP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            assert captured_threshold["value"] == 65

    def test_regime_params_restored_after_scan(self):
        """Config is fully restored after scan cycle, including regime_params keys."""
        original_threshold = config.CONFIDENCE_THRESHOLD

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "RestoreTest",
                "emoji": "♻️",
                "active_regimes": ["TREND_UP"],
                "config_overrides": {
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "TREND_UP": {
                        "CONFIDENCE_THRESHOLD": 70,
                        "MAX_OPEN_POSITIONS_PER_PASSPORT": 3
                    }
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            runner.run_scan_cycle()

            assert config.CONFIDENCE_THRESHOLD == original_threshold
            assert config.MAX_OPEN_POSITIONS_PER_PASSPORT == 50

    def test_regime_params_empty_dict_uses_config_overrides_only(self):
        """Empty regime_params means only config_overrides apply."""
        captured_threshold = {}

        def capture_scan():
            captured_threshold["value"] = config.CONFIDENCE_THRESHOLD
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "EmptyRP",
                "emoji": "📦",
                "active_regimes": ["TREND_UP"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 58,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            assert captured_threshold["value"] == 58

    def test_regime_params_missing_regime_key_uses_config_overrides(self):
        """When current regime has no entry in regime_params, use config_overrides only."""
        captured_threshold = {}

        def capture_scan():
            captured_threshold["value"] = config.CONFIDENCE_THRESHOLD
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "MissingKey",
                "emoji": "🔑",
                "active_regimes": ["TREND_UP", "TREND_DOWN"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 56,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "TREND_DOWN": {"CONFIDENCE_THRESHOLD": 62}
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            assert captured_threshold["value"] == 56

    def test_all_supported_regime_params_keys_work(self):
        """All 6 supported keys can be set via regime_params."""
        captured_config = {}

        def capture_scan():
            captured_config["CONFIDENCE_THRESHOLD"] = config.CONFIDENCE_THRESHOLD
            captured_config["MAX_OPEN_POSITIONS_PER_PASSPORT"] = config.MAX_OPEN_POSITIONS_PER_PASSPORT
            captured_config["RISK_PER_TRADE_PCT"] = config.RISK_PER_TRADE_PCT
            captured_config["DIRECTION_BIAS"] = config.DIRECTION_BIAS
            captured_config["USE_TRAILING_STOP"] = config.USE_TRAILING_STOP
            captured_config["ATR_TRAIL_MULTIPLIER"] = config.ATR_TRAIL_MULTIPLIER
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "AllKeys",
                "emoji": "🔑",
                "active_regimes": ["TREND_UP"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()},
                "regime_params": {
                    "TREND_UP": {
                        "CONFIDENCE_THRESHOLD": 70,
                        "MAX_OPEN_POSITIONS_PER_PASSPORT": 3,
                        "RISK_PER_TRADE_PCT": 0.3,
                        "DIRECTION_BIAS": "LONG_ONLY",
                        "USE_TRAILING_STOP": True,
                        "ATR_TRAIL_MULTIPLIER": 3.0
                    }
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            assert captured_config["CONFIDENCE_THRESHOLD"] == 70
            assert captured_config["MAX_OPEN_POSITIONS_PER_PASSPORT"] == 3
            assert captured_config["RISK_PER_TRADE_PCT"] == 0.3
            assert captured_config["DIRECTION_BIAS"] == "LONG_ONLY"
            assert captured_config["USE_TRAILING_STOP"] is True
            assert captured_config["ATR_TRAIL_MULTIPLIER"] == 3.0
