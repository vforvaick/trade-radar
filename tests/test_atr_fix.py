import numpy as np
import pandas as pd
import pytest

from bot.scorer import score_confluence


def _ohlcv(rows: int = 60) -> pd.DataFrame:
    """Synthetic OHLCV with enough variation for ATR to be non-zero."""
    rng = np.random.default_rng(42)
    close = 100.0 + rng.normal(0, 1, rows).cumsum()
    high = close + abs(rng.normal(0, 0.5, rows))
    low = close - abs(rng.normal(0, 0.5, rows))
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1000, 5000, rows),
    })


def test_score_confluence_returns_atr_value():
    """score_confluence must return a non-None, positive atr in the result."""
    df = _ohlcv(60)
    result = score_confluence(df)
    assert "atr" in result, "atr key missing from score_confluence result"
    assert result["atr"] is not None, "atr is None — add_atr() is not being called"
    assert result["atr"] > 0.0, f"atr must be positive, got {result['atr']}"


def test_atr_populated_in_signal_when_atr_exits_enabled(monkeypatch):
    """When USE_ATR_EXITS=True, sig.atr_at_entry must use real ATR not None."""
    from bot import config
    from bot.signals import generate_signal

    monkeypatch.setattr(config, "USE_ATR_EXITS", True, raising=False)

    df = _ohlcv(60)
    result = score_confluence(df)
    result["go"] = True
    result["direction"] = "LONG"
    result["confidence"] = 70.0
    result["leverage"] = 5

    signal = generate_signal("TESTUSDT", df["close"].iloc[-1], result)
    assert signal is not None
    assert signal.atr_at_entry is not None, "atr_at_entry must be populated when USE_ATR_EXITS=True"
    assert signal.atr_at_entry > 0.0
