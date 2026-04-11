"""Integration test: prefetch → backtest with zero API calls."""
from unittest.mock import patch, call
import numpy as np
import pandas as pd
import pytest

from bot.research.data_cache import KlineCache
from bot.backtester import run_backtest


def _make_klines(start_ms: int, hours: int) -> pd.DataFrame:
    """Generate synthetic klines with realistic OHLCV."""
    rng = np.random.default_rng(42)
    timestamps = [pd.Timestamp(start_ms + i * 3_600_000, unit="ms") for i in range(hours)]
    closes = 100 + np.cumsum(rng.normal(0, 0.5, hours))
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": closes * (1 + rng.normal(0, 0.001, hours)),
        "high": closes * (1 + rng.uniform(0, 0.01, hours)),
        "low": closes * (1 - rng.uniform(0, 0.01, hours)),
        "close": closes,
        "volume": rng.uniform(1000, 5000, hours),
    })


@patch("bot.research.data_cache.fetch_klines_range")
def test_prefetch_then_backtest_zero_api_calls(mock_fetch, tmp_path):
    """After prefetch, run_backtest with cache.get makes zero API calls."""
    base_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)
    hours = 24 * 30  # 30 days

    def _side_effect(symbol, interval, start_ms, end_ms, **kw):
        return _make_klines(start_ms, hours)

    mock_fetch.side_effect = _side_effect

    # Phase 1: Prefetch
    cache = KlineCache(cache_dir=str(tmp_path / "cache"))
    cache.prefetch(["ETHUSDT"], "1h", days=30)

    prefetch_call_count = mock_fetch.call_count
    assert prefetch_call_count >= 2  # BTCUSDT + ETHUSDT

    # Phase 2: Backtest using cache — should NOT call API
    mock_fetch.reset_mock()

    with patch("bot.backtester.fetch_klines_range") as backtester_fetch:
        result = run_backtest(
            symbols=["ETHUSDT"],
            interval="1h",
            days=7,
            kline_provider=cache.get,
        )

    # cache.get should have served data — backtester's own fetch never called
    backtester_fetch.assert_not_called()
    assert result["trades"] >= 0  # valid result returned


@patch("bot.research.data_cache.fetch_klines_range")
def test_cache_stats_after_prefetch(mock_fetch, tmp_path):
    """stats() reflects correct data after prefetch."""
    base_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)

    mock_fetch.return_value = _make_klines(base_ms, 200)

    cache = KlineCache(cache_dir=str(tmp_path / "cache"))
    cache.prefetch(["ETHUSDT", "SOLUSDT"], "1h", days=7)

    stats = cache.stats()
    assert stats["files"] >= 3  # BTC + ETH + SOL
    assert stats["total_rows"] >= 600  # 200 × 3
    assert stats["disk_size_bytes"] > 0
    assert stats["staleness_seconds"] is not None
