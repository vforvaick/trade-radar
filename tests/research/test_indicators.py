"""Tests for the 13 new indicator functions."""
import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n=100, trend="up", seed=42):
    rng = np.random.RandomState(seed)
    if trend == "up":
        base = 100 + np.cumsum(rng.normal(0.3, 1.5, n))
    elif trend == "down":
        base = 100 + np.cumsum(rng.normal(-0.3, 1.5, n))
    else:
        base = 100 + np.cumsum(rng.normal(0, 1.0, n))
    base = np.maximum(base, 10)
    return pd.DataFrame({
        "open": base + rng.uniform(-0.5, 0.5, n),
        "high": base + rng.uniform(0.5, 2.0, n),
        "low": base - rng.uniform(0.5, 2.0, n),
        "close": base,
        "volume": rng.uniform(1e6, 5e6, n),
    })


ALL_INDICATORS = [
    "calc_stochrsi", "calc_obv_trend", "calc_ichimoku",
    "calc_vwap_deviation", "calc_keltner", "calc_donchian",
    "calc_heikin_ashi", "calc_williams_r", "calc_cci",
    "calc_mfi", "calc_hull_ma", "calc_supertrend", "calc_pivot_points",
]


@pytest.mark.parametrize("func_name", ALL_INDICATORS)
def test_indicator_returns_tuple(func_name):
    from bot.research import indicators as ind
    fn = getattr(ind, func_name)
    df = make_ohlcv(100)
    result = fn(df)
    assert isinstance(result, tuple) and len(result) == 2
    direction, value = result
    assert direction in ("LONG", "SHORT", None)


@pytest.mark.parametrize("func_name", ALL_INDICATORS)
def test_indicator_handles_insufficient_data(func_name):
    from bot.research import indicators as ind
    fn = getattr(ind, func_name)
    df = make_ohlcv(3)
    direction, value = fn(df)
    assert direction is None
