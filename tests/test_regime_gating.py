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
