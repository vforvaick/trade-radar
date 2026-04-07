"""Tests for stage3.py INDICATOR_WEIGHTS perturbation (M1 fix)."""
import numpy as np
import pytest

from bot.research.stage3 import perturb_config


def test_stage3_indicator_weights_zero_stays_zero():
    """Disabled indicators (weight=0.0) must never be perturbed."""
    rng = np.random.RandomState(42)
    result = perturb_config(
        {"INDICATOR_WEIGHTS": {"ema_trend": 1.0, "bb": 0.0}},
        rng=rng,
    )
    weights = result["INDICATOR_WEIGHTS"]
    assert weights["bb"] == 0.0, "zero weight must stay zero (indicator off switch)"
    assert weights["ema_trend"] != 1.0, "non-zero weight must be perturbed"


def test_stage3_indicator_weights_nonzero_is_positive():
    """Perturbed non-zero weights must stay positive (min 0.01)."""
    rng = np.random.RandomState(99)
    result = perturb_config(
        {"INDICATOR_WEIGHTS": {"ema_trend": 1.0, "volume_spike": 2.0}},
        rng=rng,
    )
    weights = result["INDICATOR_WEIGHTS"]
    assert weights["ema_trend"] >= 0.01
    assert weights["volume_spike"] >= 0.01


def test_stage3_indicator_weights_reproducible():
    """Same rng seed produces same perturbation results."""
    config = {"INDICATOR_WEIGHTS": {"ema_trend": 1.0, "bb_position": 1.5}}
    rng1 = np.random.RandomState(7)
    rng2 = np.random.RandomState(7)
    result1 = perturb_config(config, rng=rng1)
    result2 = perturb_config(config, rng=rng2)
    assert result1["INDICATOR_WEIGHTS"] == result2["INDICATOR_WEIGHTS"]


def test_stage3_indicator_weights_within_20pct():
    """Perturbed weights should stay within ±20% of original."""
    rng = np.random.RandomState(123)
    original = 1.0
    results = []
    for _ in range(100):
        r = perturb_config({"INDICATOR_WEIGHTS": {"ema_trend": original}}, rng=rng)
        results.append(r["INDICATOR_WEIGHTS"]["ema_trend"])
    for val in results:
        assert 0.79 <= val <= 1.21, f"weight {val} outside ±20% band"


def test_stage3_indicator_weights_all_zeros_preserved():
    """All-zero weights dict stays all-zero after perturbation."""
    rng = np.random.RandomState(0)
    weights = {k: 0.0 for k in ["ema_trend", "macd_signal", "rsi_position",
                                  "rsi_divergence", "bb_position", "volume_spike",
                                  "pressure", "candle_direction"]}
    result = perturb_config({"INDICATOR_WEIGHTS": weights}, rng=rng)
    for k, v in result["INDICATOR_WEIGHTS"].items():
        assert v == 0.0, f"{k} should remain 0.0"
