"""Tests for Scanner using RegimeDetector."""
from unittest.mock import patch, MagicMock
from bot.scanner import Scanner


def test_scanner_update_btc_trend_uses_regime_detector():
    """Scanner.update_btc_trend() delegates to RegimeDetector."""
    scanner = Scanner()

    with patch.object(scanner.regime_detector, 'get_current_regime', return_value="TREND_UP"):
        scanner.update_btc_trend()

    assert scanner.btc_trend == "TREND_UP"


def test_scanner_update_btc_trend_safe_default_on_error():
    """Scanner falls back to HIGH_VOL_CHOP on exception."""
    scanner = Scanner()

    with patch.object(scanner.regime_detector, 'get_current_regime', side_effect=Exception("boom")):
        scanner.update_btc_trend()

    assert scanner.btc_trend == "HIGH_VOL_CHOP"


def test_scanner_has_regime_detector_attribute():
    """Scanner creates a RegimeDetector on init."""
    scanner = Scanner()
    from bot.regime_detector import RegimeDetector
    assert isinstance(scanner.regime_detector, RegimeDetector)


def test_scanner_exposes_regime_metadata():
    """Scanner exposes regime metadata from detector."""
    scanner = Scanner()
    meta = {"regime": "TREND_UP", "adx": 30.5, "btc_price": 87000.0}

    with patch.object(scanner.regime_detector, 'get_current_regime', return_value="TREND_UP"):
        with patch.object(scanner.regime_detector, 'get_regime_metadata', return_value=meta):
            scanner.update_btc_trend()

    assert scanner.regime_metadata == meta
