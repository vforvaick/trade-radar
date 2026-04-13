"""Tests for offline mode in research pipeline."""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from bot.research.pipeline import ResearchPipeline


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


class TestOfflineMode:
    @patch("bot.research.pipeline.KlineCache")
    @patch("bot.research.pipeline.wait_for_connectivity")
    def test_offline_skips_connectivity_check(self, mock_wait, mock_cache_cls, db_path):
        """In offline mode, wait_for_connectivity is not called."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 10, "total_rows": 5000, "disk_size_bytes": 1024 * 1024,
            "symbols_cached": ["BTCUSDT_1h", "ETHUSDT_1h"],
            "staleness_seconds": 100, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90, db_path=db_path,
        )

        with patch.object(pipeline, "generate_candidates", return_value=[]), \
             patch.object(pipeline.tracker, "finish_experiment"):
            pipeline.run_full(families=["rsi_momentum"], offline=True)

        mock_wait.assert_not_called()
        mock_cache.prefetch.assert_not_called()
        pipeline.tracker.close()

    @patch("bot.research.pipeline.KlineCache")
    @patch("bot.research.pipeline.wait_for_connectivity")
    def test_offline_uses_existing_cache(self, mock_wait, mock_cache_cls, db_path):
        """In offline mode, cache.stats() is called to verify data exists."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 16, "total_rows": 10000, "disk_size_bytes": 5 * 1024 * 1024,
            "symbols_cached": ["BTCUSDT_1h", "ETHUSDT_1h"],
            "staleness_seconds": 3600, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90, db_path=db_path,
        )

        with patch.object(pipeline, "generate_candidates", return_value=[]), \
             patch.object(pipeline.tracker, "finish_experiment"):
            pipeline.run_full(families=["rsi_momentum"], offline=True)

        mock_cache.stats.assert_called_once()
        pipeline.tracker.close()

    @patch("bot.research.pipeline.KlineCache")
    def test_offline_fails_fast_without_btcusdt(self, mock_cache_cls, db_path):
        """Offline mode raises if BTCUSDT parquet is missing from cache."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 3, "total_rows": 1000, "disk_size_bytes": 1024,
            "symbols_cached": ["ETHUSDT_1h", "SOLUSDT_1h"],
            "staleness_seconds": 100, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90, db_path=db_path,
        )

        with pytest.raises(RuntimeError, match="BTCUSDT"):
            pipeline.run_full(families=["rsi_momentum"], offline=True)
        pipeline.tracker.close()

    @patch("bot.research.pipeline.KlineCache")
    def test_offline_fails_fast_with_too_few_files(self, mock_cache_cls, db_path):
        """Offline mode raises if fewer than 5 symbol parquets in cache."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 2, "total_rows": 500, "disk_size_bytes": 512,
            "symbols_cached": ["BTCUSDT_1h", "ETHUSDT_1h"],
            "staleness_seconds": 100, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90, db_path=db_path,
        )

        with pytest.raises(RuntimeError, match="too few"):
            pipeline.run_full(families=["rsi_momentum"], offline=True)
        pipeline.tracker.close()

    @patch("bot.research.pipeline.KlineCache")
    @patch("bot.research.pipeline.wait_for_connectivity")
    def test_online_mode_still_prefetches(self, mock_wait, mock_cache_cls, db_path):
        """Default (online) mode still calls connectivity check and prefetch."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 10, "total_rows": 5000, "disk_size_bytes": 1024 * 1024,
            "symbols_cached": ["BTCUSDT_1h"], "staleness_seconds": 100,
            "memory_loaded": [],
        }
        mock_cache.prefetch.return_value = {"BTCUSDT": 100}
        mock_cache_cls.return_value = mock_cache
        mock_wait.return_value = True

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90, db_path=db_path,
        )

        with patch.object(pipeline, "generate_candidates", return_value=[]), \
             patch.object(pipeline.tracker, "finish_experiment"):
            pipeline.run_full(families=["rsi_momentum"], offline=False)

        mock_wait.assert_called_once()
        mock_cache.prefetch.assert_called_once()
        pipeline.tracker.close()
