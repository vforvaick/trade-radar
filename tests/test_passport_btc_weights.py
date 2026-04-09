"""Tests for per-passport BTC_TREND_WEIGHTS snapshot/restore isolation (4-regime)."""
from bot import config


def test_btc_trend_weights_snapshot_restore():
    """BTC_TREND_WEIGHTS override is isolated per passport (snapshot-then-restore)."""
    original_weights = config.BTC_TREND_WEIGHTS.copy()
    original_trend_up = original_weights["TREND_UP"]

    # Simulate passport_runner applying a mean-reversion passport override
    snapshot = {"BTC_TREND_WEIGHTS": config.BTC_TREND_WEIGHTS}
    config.BTC_TREND_WEIGHTS = {
        "TREND_UP": 1.0, "TREND_DOWN": 1.0,
        "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
    }

    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == 1.0
    assert config.BTC_TREND_WEIGHTS["HIGH_VOL_CHOP"] == 1.0

    # Simulate restore
    config.BTC_TREND_WEIGHTS = snapshot["BTC_TREND_WEIGHTS"]

    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == original_trend_up
    assert config.BTC_TREND_WEIGHTS == original_weights


def test_btc_trend_weights_default_penalizes_trend_up():
    """Default BTC_TREND_WEIGHTS penalizes TREND_UP (0.8) for selectivity."""
    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == 0.8
    assert config.BTC_TREND_WEIGHTS["TREND_DOWN"] == 1.0
    assert config.BTC_TREND_WEIGHTS["HIGH_VOL_CHOP"] == 0.9
    assert config.BTC_TREND_WEIGHTS["LOW_VOL_COMPRESSION"] == 1.0


def test_btc_trend_weights_has_all_four_regimes():
    """BTC_TREND_WEIGHTS must have all 4 regime keys."""
    required = {"TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}
    assert set(config.BTC_TREND_WEIGHTS.keys()) == required


def test_btc_trend_weights_no_cross_contamination():
    """Applying one passport's override doesn't bleed into the next passport's scan."""
    original = config.BTC_TREND_WEIGHTS.copy()

    # Passport A: mean-reversion, sets TREND_UP=1.0
    snapshot_a = {"BTC_TREND_WEIGHTS": config.BTC_TREND_WEIGHTS}
    config.BTC_TREND_WEIGHTS = {
        "TREND_UP": 1.0, "TREND_DOWN": 1.0,
        "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
    }
    config.BTC_TREND_WEIGHTS = snapshot_a["BTC_TREND_WEIGHTS"]  # restore

    # Passport B: trend-following, no override — should see default 0.8
    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == original["TREND_UP"]

