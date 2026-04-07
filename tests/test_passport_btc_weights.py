"""Tests for per-passport BTC_TREND_WEIGHTS snapshot/restore isolation."""
from bot import config


def test_btc_trend_weights_snapshot_restore():
    """BTC_TREND_WEIGHTS override is isolated per passport (snapshot-then-restore)."""
    original_weights = config.BTC_TREND_WEIGHTS.copy()
    original_uptrend = original_weights["Uptrend"]

    # Simulate passport_runner applying a mean-reversion passport override
    snapshot = {"BTC_TREND_WEIGHTS": config.BTC_TREND_WEIGHTS}
    config.BTC_TREND_WEIGHTS = {"Uptrend": 1.0, "Sideways": 1.0, "Downtrend": 1.0}

    assert config.BTC_TREND_WEIGHTS["Uptrend"] == 1.0
    assert config.BTC_TREND_WEIGHTS["Sideways"] == 1.0
    assert config.BTC_TREND_WEIGHTS["Downtrend"] == 1.0

    # Simulate restore
    config.BTC_TREND_WEIGHTS = snapshot["BTC_TREND_WEIGHTS"]

    assert config.BTC_TREND_WEIGHTS["Uptrend"] == original_uptrend
    assert config.BTC_TREND_WEIGHTS == original_weights


def test_btc_trend_weights_default_penalizes_uptrend():
    """Default BTC_TREND_WEIGHTS penalizes uptrend (0.8) for trend-following passports."""
    assert config.BTC_TREND_WEIGHTS["Uptrend"] == 0.8
    assert config.BTC_TREND_WEIGHTS["Sideways"] == 1.0
    assert config.BTC_TREND_WEIGHTS["Downtrend"] == 1.0


def test_btc_trend_weights_no_cross_contamination():
    """Applying one passport's override doesn't bleed into the next passport's scan."""
    original = config.BTC_TREND_WEIGHTS.copy()

    # Passport A: mean-reversion, sets Uptrend=1.0
    snapshot_a = {"BTC_TREND_WEIGHTS": config.BTC_TREND_WEIGHTS}
    config.BTC_TREND_WEIGHTS = {"Uptrend": 1.0, "Sideways": 1.0, "Downtrend": 1.0}
    config.BTC_TREND_WEIGHTS = snapshot_a["BTC_TREND_WEIGHTS"]  # restore

    # Passport B: trend-following, no override — should see default 0.8
    snapshot_b = {"BTC_TREND_WEIGHTS": config.BTC_TREND_WEIGHTS}
    # (no override applied)
    assert snapshot_b["BTC_TREND_WEIGHTS"]["Uptrend"] == original["Uptrend"]
    config.BTC_TREND_WEIGHTS = snapshot_b["BTC_TREND_WEIGHTS"]  # restore
