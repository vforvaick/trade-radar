"""Test that ResearchPipeline wires KlineCache correctly."""
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd


def _make_klines(n=200):
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="1h"),
        "open": closes, "high": closes + 1, "low": closes - 1,
        "close": closes, "volume": [1000] * n,
    })


@patch("bot.research.pipeline.KlineCache")
@patch("bot.research.pipeline.wait_for_connectivity")
@patch("bot.research.pipeline.generate_passports", return_value=[])
def test_run_full_creates_cache_and_prefetches(mock_gen, mock_conn, mock_cache_cls):
    """run_full() creates KlineCache, calls prefetch, and passes cache.get to stages."""
    from bot.research.pipeline import ResearchPipeline

    mock_cache = MagicMock()
    mock_cache.prefetch.return_value = {"BTCUSDT": 100}
    mock_cache.stats.return_value = {"files": 1, "total_rows": 100, "disk_size_bytes": 1000}
    mock_cache_cls.return_value = mock_cache

    pipeline = ResearchPipeline(symbols=["ETHUSDT"], days=90, db_path=":memory:")
    pipeline.run_full()

    mock_cache_cls.assert_called_once()
    mock_cache.prefetch.assert_called_once()
    call_args = mock_cache.prefetch.call_args
    assert "ETHUSDT" in call_args[0][0]  # symbols positional arg
    mock_cache.stats.assert_called_once()


@patch("bot.research.pipeline.KlineCache")
@patch("bot.research.pipeline.wait_for_connectivity")
@patch("bot.research.pipeline.generate_passports", return_value=[])
def test_run_full_4stage_creates_cache_and_prefetches(mock_gen, mock_conn, mock_cache_cls):
    """run_full_4stage() also creates KlineCache, calls prefetch, and logs stats."""
    from bot.research.pipeline import ResearchPipeline

    mock_cache = MagicMock()
    mock_cache.prefetch.return_value = {}
    mock_cache.stats.return_value = {"files": 0, "total_rows": 0, "disk_size_bytes": 0}
    mock_cache_cls.return_value = mock_cache

    pipeline = ResearchPipeline(symbols=["BTCUSDT", "ETHUSDT"], days=60, db_path=":memory:")
    pipeline.run_full_4stage()

    mock_cache_cls.assert_called_once()
    mock_cache.prefetch.assert_called_once()
    mock_cache.stats.assert_called_once()


def test_calc_max_walk_forward_offset_equals_days():
    """_calc_max_walk_forward_offset returns self.days."""
    from bot.research.pipeline import ResearchPipeline

    pipeline = ResearchPipeline(symbols=["BTCUSDT"], days=180)
    assert pipeline._calc_max_walk_forward_offset() == 180

    pipeline2 = ResearchPipeline(symbols=["BTCUSDT"], days=90)
    assert pipeline2._calc_max_walk_forward_offset() == 90
