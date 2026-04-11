"""Tests for bot.research.data_cache.KlineCache."""
import os
import time
from pathlib import Path
from unittest.mock import patch, call
import pytest
import pandas as pd

from bot.research.data_cache import KlineCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MS_PER_HOUR = 3_600_000


def _make_klines(start_ms: int, hours: int) -> pd.DataFrame:
    """Generate a synthetic klines DataFrame matching the expected schema."""
    timestamps = [
        pd.Timestamp(start_ms + i * _MS_PER_HOUR, unit="ms")
        for i in range(hours)
    ]
    return pd.DataFrame({
        "timestamp": timestamps,
        "open":   [100.0 + i for i in range(hours)],
        "high":   [101.0 + i for i in range(hours)],
        "low":    [99.0  + i for i in range(hours)],
        "close":  [100.5 + i for i in range(hours)],
        "volume": [1000.0 + i for i in range(hours)],
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "research_cache"


@pytest.fixture
def cache(cache_dir):
    return KlineCache(cache_dir=str(cache_dir))


# ---------------------------------------------------------------------------
# Init tests
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_directory(self, cache_dir):
        assert not cache_dir.exists()
        KlineCache(cache_dir=str(cache_dir))
        assert cache_dir.exists()

    def test_default_cache_dir(self):
        kc = KlineCache()
        assert str(kc.cache_dir) == "data/research_cache"


# ---------------------------------------------------------------------------
# Prefetch tests
# ---------------------------------------------------------------------------

class TestPrefetch:
    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_creates_parquet_files(self, mock_fetch, cache, cache_dir):
        """prefetch() saves a parquet per symbol including BTCUSDT."""
        start_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)

        def _side_effect(symbol, interval, s, e, **kw):
            return _make_klines(s, 48)

        mock_fetch.side_effect = _side_effect

        result = cache.prefetch(["ETHUSDT", "SOLUSDT"], "1h", days=2)

        assert (cache_dir / "BTCUSDT_1h.parquet").exists()
        assert (cache_dir / "ETHUSDT_1h.parquet").exists()
        assert (cache_dir / "SOLUSDT_1h.parquet").exists()
        assert set(result.keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_includes_btcusdt(self, mock_fetch, cache, cache_dir):
        """BTCUSDT is always fetched even if not in the symbols list."""
        mock_fetch.return_value = _make_klines(0, 10)

        cache.prefetch(["ETHUSDT"], "1h", days=1)

        called_symbols = [c.args[0] for c in mock_fetch.call_args_list]
        assert "BTCUSDT" in called_symbols

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_only_fetches_gaps(self, mock_fetch, cache, cache_dir):
        """When parquet already covers part of the range, only gaps are fetched."""
        # Write a parquet covering a middle window
        mid_start = int(pd.Timestamp("2024-02-01").timestamp() * 1000)
        existing = _make_klines(mid_start, 720)  # 30 days
        path = cache_dir / "ETHUSDT_1h.parquet"
        existing.to_parquet(path, index=False)

        mock_fetch.return_value = _make_klines(mid_start, 24)

        # Request a range that extends before and after the existing data
        cache.prefetch(["ETHUSDT"], "1h", days=60)

        called_symbols = [c.args[0] for c in mock_fetch.call_args_list]
        eth_calls = [c for c in mock_fetch.call_args_list if c.args[0] == "ETHUSDT"]
        # Should have fetched gap(s) but not a single full re-fetch from scratch
        # (i.e. at most 2 calls: early gap + tail gap)
        assert len(eth_calls) <= 2

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_with_max_offset(self, mock_fetch, cache):
        """max_offset_days extends the total range fetched."""
        mock_fetch.return_value = _make_klines(0, 10)

        cache.prefetch(["ETHUSDT"], "1h", days=30, max_offset_days=10)

        # 40 days worth of candles requested
        eth_calls = [c for c in mock_fetch.call_args_list if c.args[0] == "ETHUSDT"]
        assert len(eth_calls) >= 1
        # Verify range is at least 40 days
        first_call = eth_calls[0]
        s, e = first_call.args[2], first_call.args[3]
        assert (e - s) >= 40 * 86_400_000

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_corrupted_parquet_recovery_in_prefetch(self, mock_fetch, cache, cache_dir):
        """Corrupt parquet is deleted and data is re-fetched."""
        path = cache_dir / "ETHUSDT_1h.parquet"
        path.write_bytes(b"this is not valid parquet")

        mock_fetch.return_value = _make_klines(0, 48)

        result = cache.prefetch(["ETHUSDT"], "1h", days=2)

        # File should be recreated
        assert path.exists()
        assert result["ETHUSDT"] == 48

        eth_calls = [c for c in mock_fetch.call_args_list if c.args[0] == "ETHUSDT"]
        assert len(eth_calls) == 1  # full re-fetch


# ---------------------------------------------------------------------------
# Get tests
# ---------------------------------------------------------------------------

class TestGet:
    @patch("bot.research.data_cache.fetch_klines_range")
    def test_get_returns_correct_range(self, mock_fetch, cache, cache_dir):
        """get() slices from memory without calling the API."""
        base_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)
        df_full = _make_klines(base_ms, 100)
        df_full.to_parquet(cache_dir / "ETHUSDT_1h.parquet", index=False)

        start_ms = base_ms + 10 * _MS_PER_HOUR
        end_ms   = base_ms + 20 * _MS_PER_HOUR

        result = cache.get("ETHUSDT", "1h", start_ms, end_ms)

        mock_fetch.assert_not_called()
        assert len(result) == 10
        assert result["timestamp"].iloc[0] == pd.Timestamp(start_ms, unit="ms")

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_get_fallback_on_miss(self, mock_fetch, cache):
        """Uncached symbol triggers API fallback."""
        fallback_df = _make_klines(0, 5)
        mock_fetch.return_value = fallback_df

        result = cache.get("XYZUSDT", "1h", 0, 5 * _MS_PER_HOUR)

        mock_fetch.assert_called_once()
        assert len(result) == 5

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_get_loads_from_parquet_on_first_access(self, mock_fetch, cache, cache_dir):
        """First get() loads from parquet; second reuses memory."""
        base_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)
        df = _make_klines(base_ms, 50)
        df.to_parquet(cache_dir / "ETHUSDT_1h.parquet", index=False)

        start_ms = base_ms
        end_ms   = base_ms + 10 * _MS_PER_HOUR

        cache.get("ETHUSDT", "1h", start_ms, end_ms)
        assert "ETHUSDT" in cache._memory

        # Second call should not touch disk or API
        cache.get("ETHUSDT", "1h", start_ms, end_ms)
        mock_fetch.assert_not_called()

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_get_empty_slice_falls_back(self, mock_fetch, cache, cache_dir):
        """If slice is empty (range outside cached data), fall back to API."""
        base_ms = int(pd.Timestamp("2024-06-01").timestamp() * 1000)
        df = _make_klines(base_ms, 24)
        df.to_parquet(cache_dir / "ETHUSDT_1h.parquet", index=False)

        # Request a range entirely before the cached data
        start_ms = base_ms - 100 * _MS_PER_HOUR
        end_ms   = base_ms - 50  * _MS_PER_HOUR

        mock_fetch.return_value = _make_klines(start_ms, 50)
        result = cache.get("ETHUSDT", "1h", start_ms, end_ms)

        mock_fetch.assert_called_once()
        assert len(result) == 50

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_corrupted_parquet_recovery_in_get(self, mock_fetch, cache, cache_dir):
        """Corrupt parquet on disk causes get() to fall back to API."""
        path = cache_dir / "ETHUSDT_1h.parquet"
        path.write_bytes(b"garbage data")

        mock_fetch.return_value = _make_klines(0, 24)
        result = cache.get("ETHUSDT", "1h", 0, 24 * _MS_PER_HOUR)

        mock_fetch.assert_called_once()
        assert len(result) == 24


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------

class TestStats:
    @patch("bot.research.data_cache.fetch_klines_range")
    def test_stats(self, mock_fetch, cache, cache_dir):
        """stats() returns correct file count and total rows."""
        mock_fetch.return_value = _make_klines(0, 30)

        cache.prefetch(["ETHUSDT"], "1h", days=1)

        s = cache.stats()
        assert s["cache_dir"] == str(cache_dir)
        assert s["files"] >= 2  # BTCUSDT + ETHUSDT
        assert s["total_rows"] >= 60  # at least 30 rows × 2 symbols
        assert isinstance(s["symbols_cached"], list)
        assert isinstance(s["memory_loaded"], list)
