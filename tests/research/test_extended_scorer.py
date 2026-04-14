"""Tests for the extended scorer (now delegates to production registry)."""
import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n=200, seed=42):
    rng = np.random.RandomState(seed)
    base = 100 + np.cumsum(rng.normal(0.2, 1.5, n))
    base = np.maximum(base, 10)
    return pd.DataFrame({
        "open": base + rng.uniform(-0.5, 0.5, n),
        "high": base + rng.uniform(0.5, 2.0, n),
        "low": base - rng.uniform(0.5, 2.0, n),
        "close": base,
        "volume": rng.uniform(1e6, 5e6, n),
    })


def test_score_extended_returns_signal():
    from bot.research.extended_scorer import score_extended
    result = score_extended(make_ohlcv(200), weights={"ema_trend": 1.0, "rsi_position": 1.0})
    assert "direction" in result and "confidence" in result and "go" in result


def test_new_indicator_weights():
    from bot.research.extended_scorer import score_extended
    result = score_extended(make_ohlcv(200), weights={"stochrsi": 2.0, "obv_trend": 1.5})
    assert isinstance(result["confidence"], (int, float))


def test_empty_weights_no_signal():
    from bot.research.extended_scorer import score_extended
    assert score_extended(make_ohlcv(200), weights={})["direction"] is None


def test_registry_contains_all_production_indicators():
    """Registry now comes from bot.scorer (23 indicators), superset of old 21."""
    from bot.research.extended_scorer import INDICATOR_REGISTRY
    from bot.scorer import INDICATOR_REGISTRY as PROD_REGISTRY
    # Extended registry IS the production registry — same object
    assert set(INDICATOR_REGISTRY.keys()) == set(PROD_REGISTRY.keys())
    assert len(INDICATOR_REGISTRY) >= 21  # at least as many as before
