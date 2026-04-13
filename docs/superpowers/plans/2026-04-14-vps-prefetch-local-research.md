# VPS Prefetch + Local Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable running research pipeline locally using kline data prefetched on VPS, eliminating dependency on local Binance API access.

**Architecture:** VPS prefetches kline parquets via Binance API with robust retry logic. A sync script SCPs parquets to local. Research pipeline gains `--offline` flag to skip connectivity checks and prefetch, using local parquets only. Auto-cleanup removes stale parquets >7 days.

**Tech Stack:** Python 3 (pandas, pyarrow, requests), Bash (SSH, SCP), existing KlineCache infrastructure.

---

### Task 1: Add `cleanup()` method to KlineCache

**Files:**
- Modify: `bot/research/data_cache.py` (add method after `stats()`)
- Test: `tests/research/test_data_cache.py` (add TestCleanup class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/research/test_data_cache.py`:

```python
class TestCleanup:
    def test_cleanup_removes_old_files(self, cache, cache_dir):
        """Parquets older than max_age_days are deleted."""
        base_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)
        df = _make_klines(base_ms, 24)

        old_path = cache_dir / "OLDUSDT_1h.parquet"
        df.to_parquet(old_path, index=False)
        old_time = time.time() - 8 * 86400  # 8 days ago
        os.utime(old_path, (old_time, old_time))

        fresh_path = cache_dir / "FRESHUSDT_1h.parquet"
        df.to_parquet(fresh_path, index=False)
        # fresh_path mtime is now (just created)

        removed = cache.cleanup(max_age_days=7)

        assert not old_path.exists()
        assert fresh_path.exists()
        assert len(removed) == 1
        assert "OLDUSDT_1h.parquet" in removed[0]

    def test_cleanup_returns_empty_when_nothing_stale(self, cache, cache_dir):
        """No files removed if all are fresh."""
        base_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)
        df = _make_klines(base_ms, 24)
        (cache_dir / "ETHUSDT_1h.parquet").write_bytes(b"")
        df.to_parquet(cache_dir / "ETHUSDT_1h.parquet", index=False)

        removed = cache.cleanup(max_age_days=7)
        assert removed == []

    def test_cleanup_handles_empty_cache_dir(self, cache):
        """No error when cache dir has no parquets."""
        removed = cache.cleanup(max_age_days=7)
        assert removed == []

    def test_cleanup_clears_memory_for_removed(self, cache, cache_dir):
        """Memory cache entries for cleaned-up files are also purged."""
        base_ms = int(pd.Timestamp("2024-01-01").timestamp() * 1000)
        df = _make_klines(base_ms, 24)
        path = cache_dir / "STALEUSDT_1h.parquet"
        df.to_parquet(path, index=False)
        # Load into memory
        cache._memory[("STALEUSDT", "1h")] = df

        old_time = time.time() - 10 * 86400
        os.utime(path, (old_time, old_time))

        cache.cleanup(max_age_days=7)

        assert ("STALEUSDT", "1h") not in cache._memory
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/research/test_data_cache.py::TestCleanup -v`
Expected: FAIL — `AttributeError: 'KlineCache' object has no attribute 'cleanup'`

- [ ] **Step 3: Implement cleanup() method**

Add to `bot/research/data_cache.py` after the `stats()` method (after line 227):

```python
    def cleanup(self, max_age_days: int = 7) -> list[str]:
        """Remove parquet files older than max_age_days.

        Also clears memory cache entries for removed files.
        Returns list of removed file paths.
        """
        cutoff = time.time() - max_age_days * 86400
        removed: list[str] = []

        for path in self.cache_dir.glob("*.parquet"):
            if path.stat().st_mtime < cutoff:
                # Parse symbol and interval from filename (e.g. ETHUSDT_1h.parquet)
                stem = path.stem
                parts = stem.rsplit("_", 1)
                if len(parts) == 2:
                    self._memory.pop((parts[0], parts[1]), None)

                logger.info("Removing stale parquet: %s (age: %.0f days)",
                            path.name, (time.time() - path.stat().st_mtime) / 86400)
                path.unlink()
                removed.append(str(path))

        return removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/research/test_data_cache.py::TestCleanup -v`
Expected: 4 PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/research/test_data_cache.py -v`
Expected: All existing + new tests PASS

- [ ] **Step 6: Commit**

```bash
git add bot/research/data_cache.py tests/research/test_data_cache.py
git commit -m "feat: add KlineCache.cleanup() for stale parquet removal

Removes parquet files older than max_age_days (default 7).
Also clears memory cache entries for removed files.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Add rate-limit retry to `data_fetcher.fetch_klines()`

**Files:**
- Modify: `bot/data_fetcher.py` (add retry wrapper around HTTP call)
- Test: `tests/test_data_fetcher_retry.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_data_fetcher_retry.py`:

```python
"""Tests for rate-limit retry logic in data_fetcher."""
import pytest
from unittest.mock import patch, MagicMock
import requests

from bot.data_fetcher import fetch_klines


class TestRateLimitRetry:
    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_retries_on_429(self, mock_get, mock_sleep):
        """HTTP 429 triggers retry with backoff."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_429
        )

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = []
        resp_ok.raise_for_status = MagicMock()

        mock_get.side_effect = [resp_429, resp_ok]

        result = fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)
        assert result.empty  # empty because json returns []
        assert mock_get.call_count == 2
        mock_sleep.assert_called()  # backoff sleep was called

    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_retries_on_418(self, mock_get, mock_sleep):
        """HTTP 418 (IP ban) triggers retry with backoff."""
        resp_418 = MagicMock()
        resp_418.status_code = 418
        resp_418.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_418
        )

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = []
        resp_ok.raise_for_status = MagicMock()

        mock_get.side_effect = [resp_418, resp_ok]

        result = fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)
        assert mock_get.call_count == 2

    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_gives_up_after_max_retries(self, mock_get, mock_sleep):
        """After max retries, raises the error."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_429
        )

        mock_get.return_value = resp_429

        with pytest.raises(requests.exceptions.HTTPError):
            fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)

        assert mock_get.call_count == 6  # 1 initial + 5 retries

    @patch("bot.data_fetcher.requests.get")
    def test_no_retry_on_other_errors(self, mock_get):
        """Non-rate-limit errors propagate immediately."""
        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp_400
        )

        mock_get.return_value = resp_400

        with pytest.raises(requests.exceptions.HTTPError):
            fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)

        assert mock_get.call_count == 1  # no retry

    @patch("bot.data_fetcher.time.sleep")
    @patch("bot.data_fetcher.requests.get")
    def test_retries_on_connection_error(self, mock_get, mock_sleep):
        """ConnectionError triggers retry."""
        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = []
        resp_ok.raise_for_status = MagicMock()

        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection reset"),
            resp_ok,
        ]

        result = fetch_klines("ETHUSDT", "1h", limit=10, use_cache=False)
        assert mock_get.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_fetcher_retry.py -v`
Expected: FAIL — current `fetch_klines` doesn't retry

- [ ] **Step 3: Add retry logic to fetch_klines()**

Modify `bot/data_fetcher.py`. Replace the `fetch_klines` function (lines 29-77) with:

```python
_RATE_LIMIT_CODES = {429, 418}
_MAX_RETRIES = 5
_BASE_BACKOFF = 1.0  # seconds
_MAX_BACKOFF = 60.0


def fetch_klines(symbol: str, interval: str = "1h",
                 limit: int = 500, start_time: int = None,
                 end_time: int = None, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch OHLCV klines from Binance Futures.

    Retries on rate limits (429/418) and connection errors with
    exponential backoff: 1s, 2s, 4s, 8s, 16s (capped at 60s).

    Returns DataFrame with columns:
        timestamp, open, high, low, close, volume
    """
    cache_key = f"{symbol}_{interval}_{limit}_{start_time}_{end_time}"
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    url = f"{config.BINANCE_FUTURES_BASE}/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time

    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, verify=_verify_tls(), timeout=15)
            if resp.status_code in _RATE_LIMIT_CODES:
                delay = min(_BASE_BACKOFF * (2 ** attempt), _MAX_BACKOFF)
                logger.warning(
                    "Rate limited (%d) fetching %s — retry %d/%d in %.0fs",
                    resp.status_code, symbol, attempt + 1, _MAX_RETRIES, delay,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(delay)
                    continue
                resp.raise_for_status()  # final attempt, raise
            resp.raise_for_status()
            break
        except requests.exceptions.HTTPError:
            raise  # non-rate-limit HTTP errors propagate immediately
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                ConnectionError, OSError) as e:
            last_exc = e
            if attempt < _MAX_RETRIES:
                delay = min(_BASE_BACKOFF * (2 ** attempt), _MAX_BACKOFF)
                logger.warning(
                    "Connection error fetching %s: %s — retry %d/%d in %.0fs",
                    symbol, e, attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                continue
            raise
    else:
        if last_exc:
            raise last_exc

    data = resp.json()

    if isinstance(data, dict) and "error" in data:
        raise Exception(f"Binance API error for {symbol}: {data}")

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    if use_cache:
        _write_cache(cache_key, df)

    return df
```

- [ ] **Step 4: Run retry tests**

Run: `uv run pytest tests/test_data_fetcher_retry.py -v`
Expected: 5 PASS

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `uv run pytest tests/ -v --tb=short -q`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add bot/data_fetcher.py tests/test_data_fetcher_retry.py
git commit -m "feat: add rate-limit retry to fetch_klines()

Retries on HTTP 429/418 and connection errors with exponential
backoff (1s-60s cap, max 5 retries). Non-rate-limit HTTP errors
propagate immediately.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Add `--offline` flag to research pipeline

**Files:**
- Modify: `run_research.py` (add `--offline` argparse flag)
- Modify: `bot/research/pipeline.py` (add `offline` parameter to `run_full()` and `run_full_4stage()`)
- Test: `tests/research/test_pipeline_offline.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_pipeline_offline.py`:

```python
"""Tests for offline mode in research pipeline."""
import pytest
from unittest.mock import patch, MagicMock

from bot.research.pipeline import ResearchPipeline


class TestOfflineMode:
    @patch("bot.research.pipeline.KlineCache")
    @patch("bot.research.pipeline.wait_for_connectivity")
    def test_offline_skips_connectivity_check(self, mock_wait, mock_cache_cls):
        """In offline mode, wait_for_connectivity is not called."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 10, "total_rows": 5000, "disk_size_bytes": 1024 * 1024,
            "symbols_cached": ["BTCUSDT_1h", "ETHUSDT_1h"],
            "staleness_seconds": 100, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90,
        )

        with patch.object(pipeline, "generate_candidates", return_value=[]):
            pipeline.run_full(families=["rsi_momentum"], offline=True)

        mock_wait.assert_not_called()
        mock_cache.prefetch.assert_not_called()

    @patch("bot.research.pipeline.KlineCache")
    @patch("bot.research.pipeline.wait_for_connectivity")
    def test_offline_uses_existing_cache(self, mock_wait, mock_cache_cls):
        """In offline mode, cache.stats() is called to verify data exists."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 16, "total_rows": 10000, "disk_size_bytes": 5 * 1024 * 1024,
            "symbols_cached": ["BTCUSDT_1h", "ETHUSDT_1h"],
            "staleness_seconds": 3600, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90,
        )

        with patch.object(pipeline, "generate_candidates", return_value=[]):
            pipeline.run_full(families=["rsi_momentum"], offline=True)

        mock_cache.stats.assert_called_once()

    @patch("bot.research.pipeline.KlineCache")
    def test_offline_fails_fast_without_btcusdt(self, mock_cache_cls):
        """Offline mode raises if BTCUSDT parquet is missing from cache."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 3, "total_rows": 1000, "disk_size_bytes": 1024,
            "symbols_cached": ["ETHUSDT_1h", "SOLUSDT_1h"],
            "staleness_seconds": 100, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90,
        )

        with pytest.raises(RuntimeError, match="BTCUSDT"):
            pipeline.run_full(families=["rsi_momentum"], offline=True)

    @patch("bot.research.pipeline.KlineCache")
    def test_offline_fails_fast_with_too_few_files(self, mock_cache_cls):
        """Offline mode raises if fewer than 5 symbol parquets in cache."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "files": 2, "total_rows": 500, "disk_size_bytes": 512,
            "symbols_cached": ["BTCUSDT_1h", "ETHUSDT_1h"],
            "staleness_seconds": 100, "memory_loaded": [],
        }
        mock_cache_cls.return_value = mock_cache

        pipeline = ResearchPipeline(
            symbols=["ETHUSDT"], interval="1h", days=90,
        )

        with pytest.raises(RuntimeError, match="too few"):
            pipeline.run_full(families=["rsi_momentum"], offline=True)

    @patch("bot.research.pipeline.KlineCache")
    @patch("bot.research.pipeline.wait_for_connectivity")
    def test_online_mode_still_prefetches(self, mock_wait, mock_cache_cls):
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
            symbols=["ETHUSDT"], interval="1h", days=90,
        )

        with patch.object(pipeline, "generate_candidates", return_value=[]):
            pipeline.run_full(families=["rsi_momentum"], offline=False)

        mock_wait.assert_called_once()
        mock_cache.prefetch.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/research/test_pipeline_offline.py -v`
Expected: FAIL — `run_full()` doesn't accept `offline` parameter

- [ ] **Step 3: Modify pipeline.py to support offline mode**

In `bot/research/pipeline.py`, modify the `run_full()` method (starting at line 293):

Replace the `run_full` method with:

```python
    def run_full(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
        offline: bool = False,
    ) -> list[PassportCandidate]:
        """Run the 2-stage pipeline: generate → Stage 1 → Stage 2.

        When ``offline=True``, skip connectivity check and prefetch.
        Uses existing local parquets only.
        """
        cache = KlineCache()

        if offline:
            stats = cache.stats()
            logger.info(
                "OFFLINE mode: %d cached files, %d rows, %.1f MB",
                stats["files"], stats["total_rows"],
                stats["disk_size_bytes"] / 1_048_576,
            )
            cached_symbols = [s.split("_")[0] for s in stats["symbols_cached"]]
            if "BTCUSDT" not in cached_symbols:
                raise RuntimeError(
                    "Offline mode requires BTCUSDT parquet in cache. "
                    "Run sync_research_data.sh first."
                )
            if stats["files"] < 5:
                raise RuntimeError(
                    f"Offline mode: too few cached files ({stats['files']}). "
                    "Need at least 5. Run sync_research_data.sh first."
                )
        else:
            logger.info("Checking Binance API connectivity before starting pipeline...")
            wait_for_connectivity(check_interval=30.0, max_wait=7200.0)

            logger.info(
                "Pre-fetching kline data for %d symbols, %d days...",
                len(self.symbols), self.days,
            )
            max_offset = self._calc_max_walk_forward_offset()
            cache.prefetch(self.symbols, self.interval, self.days, max_offset_days=max_offset)
            stats = cache.stats()
            logger.info(
                "Cache ready: %d files, %d rows, %.1f MB",
                stats["files"], stats["total_rows"],
                stats["disk_size_bytes"] / 1_048_576,
            )

        candidates = self.generate_candidates(families, max_per_family)
        stage1_survivors = self.run_stage1(candidates, kline_provider=cache.get)
        stage2_survivors = self.run_stage2(stage1_survivors, kline_provider=cache.get)

        self.tracker.finish_experiment(
            self.run_id,
            stage1_survivors=len(stage1_survivors),
            stage2_survivors=len(stage2_survivors),
        )

        logger.info(
            "Pipeline complete: %d generated → %d stage1 → %d stage2",
            len(candidates), len(stage1_survivors), len(stage2_survivors),
        )
        return stage2_survivors
```

Also update `run_full_4stage()` similarly — add `offline: bool = False` parameter and apply the same if/else pattern for the connectivity/prefetch block (lines 333-375). Same logic: if offline, validate cache stats; if online, do connectivity check + prefetch.

- [ ] **Step 4: Add --offline flag to run_research.py**

In `run_research.py`, add after the `--db-path` argument (after line 57):

```python
    parser.add_argument("--offline", action="store_true",
                        help="Skip connectivity check and prefetch; use local cache only")
```

Then update the symbol discovery block (lines 67-73) to handle offline mode:

```python
    if args.offline:
        # In offline mode, we need symbols from cache, not API
        from bot.research.data_cache import KlineCache
        cache = KlineCache()
        stats = cache.stats()
        if args.quality_pairs:
            symbols = QUALITY_PAIRS
        else:
            # Extract symbols from cached parquet filenames
            symbols = []
            for name in stats["symbols_cached"]:
                sym = name.split("_")[0]
                if sym != "BTCUSDT" and sym not in symbols:
                    symbols.append(sym)
            symbols = symbols[:args.pairs]
        logger.info("OFFLINE mode — using %d cached symbols", len(symbols))
    elif args.quality_pairs:
        symbols = QUALITY_PAIRS
        logger.info("Using quality pairs (%d): %s", len(symbols), symbols)
    else:
        logger.info("Fetching top %d symbols by volume...", args.pairs)
        symbols = get_all_futures_symbols()[:args.pairs]
    logger.info("Trading pairs: %s", symbols)
```

And pass `offline` to `run_full`:

```python
    survivors = pipeline.run_full(
        families=families,
        max_per_family=args.max_per_family,
        offline=args.offline,
    )
```

- [ ] **Step 5: Run offline tests**

Run: `uv run pytest tests/research/test_pipeline_offline.py -v`
Expected: 5 PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short -q`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add bot/research/pipeline.py run_research.py tests/research/test_pipeline_offline.py
git commit -m "feat: add --offline flag to research pipeline

Skip connectivity check and prefetch when running with local cache.
Validates BTCUSDT exists and minimum 5 parquet files.
Discovers symbols from cache filenames in offline mode.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Create VPS prefetch script

**Files:**
- Create: `scripts/prefetch_klines_vps.py`
- Test: manual (runs on VPS only)

- [ ] **Step 1: Create the prefetch script**

Create `scripts/prefetch_klines_vps.py`:

```python
#!/usr/bin/env python3
"""Prefetch kline data from Binance into the research cache.

Designed to run on VPS (fight-tres) where Binance API is always accessible.
Uses KlineCache.prefetch() with retry logic from data_fetcher.

Usage:
    python scripts/prefetch_klines_vps.py --days 180 --pairs 15
    python scripts/prefetch_klines_vps.py --quality-pairs --days 270
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

# Ensure project root is in path
sys.path.insert(0, ".")

from bot.data_fetcher import get_all_futures_symbols
from bot.research.data_cache import KlineCache

QUALITY_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("prefetch")


def main():
    parser = argparse.ArgumentParser(description="Prefetch kline data for research")
    parser.add_argument("--days", type=int, default=180, help="History days (default: 180)")
    parser.add_argument("--pairs", type=int, default=15, help="Number of pairs (default: 15)")
    parser.add_argument("--quality-pairs", action="store_true",
                        help="Use hardcoded tier-1 pairs")
    parser.add_argument("--interval", type=str, default="1h", help="Timeframe (default: 1h)")
    args = parser.parse_args()

    if args.quality_pairs:
        symbols = QUALITY_PAIRS
        logger.info("Using quality pairs (%d): %s", len(symbols), symbols)
    else:
        logger.info("Fetching top %d symbols by volume...", args.pairs)
        symbols = get_all_futures_symbols()[:args.pairs]

    logger.info("Symbols: %s", symbols)

    cache = KlineCache()

    # Cleanup stale data first
    removed = cache.cleanup(max_age_days=7)
    if removed:
        logger.info("Cleaned up %d stale parquets", len(removed))

    logger.info("Prefetching %d symbols × %d days (%s)...", len(symbols), args.days, args.interval)
    start = time.time()

    # max_offset_days = days (for walk-forward coverage)
    result = cache.prefetch(symbols, args.interval, args.days, max_offset_days=args.days)

    elapsed = time.time() - start
    stats = cache.stats()

    succeeded = sum(1 for v in result.values() if v > 0)
    failed = sum(1 for v in result.values() if v == 0)
    total_rows = sum(result.values())

    logger.info("=" * 60)
    logger.info("PREFETCH COMPLETE in %.1f minutes", elapsed / 60)
    logger.info("Symbols: %d succeeded, %d failed", succeeded, failed)
    logger.info("Total rows: %d", total_rows)
    logger.info("Cache: %d files, %.1f MB",
                stats["files"], stats["disk_size_bytes"] / 1_048_576)
    logger.info("=" * 60)

    if failed > 0:
        failed_symbols = [s for s, v in result.items() if v == 0]
        logger.warning("Failed symbols: %s", failed_symbols)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make script executable**

```bash
chmod +x scripts/prefetch_klines_vps.py
```

- [ ] **Step 3: Commit**

```bash
git add scripts/prefetch_klines_vps.py
git commit -m "feat: add VPS prefetch script for research kline data

Standalone script to run on VPS for prefetching kline parquets.
Includes stale cleanup (>7 days) and summary reporting.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Create sync and convenience scripts

**Files:**
- Create: `scripts/sync_research_data.sh`
- Create: `scripts/research_local.sh`

- [ ] **Step 1: Create the sync script**

Create `scripts/sync_research_data.sh`:

```bash
#!/usr/bin/env bash
# Sync research kline data from VPS to local machine.
#
# Usage:
#   ./scripts/sync_research_data.sh                     # default: 180 days, 15 pairs
#   ./scripts/sync_research_data.sh --days 270 --pairs 20
#   ./scripts/sync_research_data.sh --quality-pairs
#   ./scripts/sync_research_data.sh --sync-only          # skip VPS prefetch, just SCP
set -euo pipefail

VPS_HOST="fight-tres"
VPS_REPO="/home/vforvaick/pumpradar-bot"
VPS_PYTHON="${VPS_REPO}/.venv/bin/python"
VPS_CACHE="${VPS_REPO}/data/research_cache/"
LOCAL_CACHE="data/research_cache/"
PREFETCH_ARGS=""
SYNC_ONLY=false

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --sync-only) SYNC_ONLY=true ;;
        *) PREFETCH_ARGS="$PREFETCH_ARGS $arg" ;;
    esac
done

# Default args if none provided
if [ -z "$PREFETCH_ARGS" ] && [ "$SYNC_ONLY" = false ]; then
    PREFETCH_ARGS="--days 180 --pairs 15"
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║       Cryptopass Research Data Sync              ║"
echo "╚══════════════════════════════════════════════════╝"

# Step 1: Clean local stale parquets
echo ""
echo "→ Step 1: Cleaning local stale parquets (>7 days)..."
find "$LOCAL_CACHE" -name "*.parquet" -mtime +7 -delete 2>/dev/null && \
    echo "  Cleaned stale parquets" || echo "  No stale parquets found"

# Step 2: Prefetch on VPS (unless --sync-only)
if [ "$SYNC_ONLY" = false ]; then
    echo ""
    echo "→ Step 2: Prefetching kline data on VPS..."
    echo "  Command: ${VPS_PYTHON} scripts/prefetch_klines_vps.py ${PREFETCH_ARGS}"

    if ! ssh "$VPS_HOST" "cd ${VPS_REPO} && ${VPS_PYTHON} scripts/prefetch_klines_vps.py ${PREFETCH_ARGS}"; then
        echo "  ⚠️  VPS prefetch failed! Will try to sync existing data..."
    fi
else
    echo ""
    echo "→ Step 2: Skipped (--sync-only)"
fi

# Step 3: SCP parquets to local
echo ""
echo "→ Step 3: Syncing parquets from VPS to local..."
mkdir -p "$LOCAL_CACHE"

if ! scp -r "${VPS_HOST}:${VPS_CACHE}"*.parquet "$LOCAL_CACHE" 2>/dev/null; then
    echo "  ❌ SCP failed! Check SSH connection to ${VPS_HOST}"
    echo "  Try: ssh ${VPS_HOST} ls ${VPS_CACHE}"
    exit 1
fi

# Step 4: Verify
echo ""
echo "→ Step 4: Verifying local cache..."
FILE_COUNT=$(find "$LOCAL_CACHE" -name "*.parquet" | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "$LOCAL_CACHE" 2>/dev/null | cut -f1)
HAS_BTC=$(find "$LOCAL_CACHE" -name "BTCUSDT_*.parquet" | wc -l | tr -d ' ')

echo "  Files: ${FILE_COUNT}"
echo "  Size: ${TOTAL_SIZE}"

if [ "$HAS_BTC" -eq 0 ]; then
    echo "  ⚠️  WARNING: BTCUSDT parquet missing! Research will fail."
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅ Sync complete! Ready for offline research.  ║"
echo "║                                                  ║"
echo "║  Run research:                                   ║"
echo "║  uv run python run_research.py --offline \\      ║"
echo "║    --all --max-per-family 5 --days 180           ║"
echo "╚══════════════════════════════════════════════════╝"
```

- [ ] **Step 2: Create the convenience wrapper**

Create `scripts/research_local.sh`:

```bash
#!/usr/bin/env bash
# End-to-end local research: sync data from VPS + run pipeline offline.
#
# Usage:
#   ./scripts/research_local.sh                          # sync + research
#   ./scripts/research_local.sh --skip-sync              # use existing local data
#   ./scripts/research_local.sh --days 270 --families rsi_momentum
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SKIP_SYNC=false
SYNC_ARGS=""
RESEARCH_ARGS="--all --max-per-family 5 --days 180"

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --skip-sync) SKIP_SYNC=true ;;
        --days|--pairs|--quality-pairs|--families|--max-per-family|--interval|--db-path)
            RESEARCH_ARGS="$RESEARCH_ARGS $arg" ;;
        *) RESEARCH_ARGS="$RESEARCH_ARGS $arg" ;;
    esac
done

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/research_local_${TIMESTAMP}.log"
mkdir -p logs

echo "╔══════════════════════════════════════════════════╗"
echo "║     Cryptopass Local Research Pipeline           ║"
echo "╚══════════════════════════════════════════════════╝"

# Step 1: Sync data from VPS
if [ "$SKIP_SYNC" = false ]; then
    echo ""
    echo "Phase 1: Syncing data from VPS..."
    ./scripts/sync_research_data.sh $SYNC_ARGS
else
    echo ""
    echo "Phase 1: Skipped (--skip-sync)"
fi

# Step 2: Run research offline
echo ""
echo "Phase 2: Starting offline research pipeline..."
echo "  Log: ${LOG_FILE}"
echo "  Args: --offline ${RESEARCH_ARGS}"
echo ""

nohup uv run python run_research.py --offline ${RESEARCH_ARGS} \
    > "$LOG_FILE" 2>&1 &

PID=$!
echo "╔══════════════════════════════════════════════════╗"
echo "║  🚀 Research running! PID: ${PID}               "
echo "║                                                  ║"
echo "║  Monitor: tail -f ${LOG_FILE}                    "
echo "║  Check:   ps -p ${PID}                           "
echo "║  Stop:    kill ${PID}                            ║"
echo "╚══════════════════════════════════════════════════╝"
```

- [ ] **Step 3: Make scripts executable**

```bash
chmod +x scripts/sync_research_data.sh scripts/research_local.sh
```

- [ ] **Step 4: Commit**

```bash
git add scripts/sync_research_data.sh scripts/research_local.sh
git commit -m "feat: add sync and convenience scripts for local research

sync_research_data.sh: SSH to VPS, prefetch klines, SCP to local.
research_local.sh: One-command sync + offline research with nohup.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Push to VPS and end-to-end test

**Files:**
- No new files — integration testing

- [ ] **Step 1: Push all changes to origin**

```bash
git push origin master
```

- [ ] **Step 2: Pull on VPS**

```bash
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull"
```

- [ ] **Step 3: Test prefetch on VPS**

```bash
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && .venv/bin/python scripts/prefetch_klines_vps.py --quality-pairs --days 180"
```

Expected: Prefetch completes, shows stats (10 symbols, ~4300+ rows each).

- [ ] **Step 4: Test sync from MacBook**

```bash
./scripts/sync_research_data.sh --sync-only
```

Expected: Parquets SCP'd to `data/research_cache/`, BTCUSDT present, file count matches VPS.

- [ ] **Step 5: Test offline research (dry run)**

```bash
uv run python run_research.py --offline --quality-pairs --families rsi_momentum --max-per-family 1 --days 90
```

Expected: Pipeline starts without API calls, uses cached data, generates candidates, runs Stage 1+2.

- [ ] **Step 6: Run full local research pipeline**

```bash
./scripts/research_local.sh --skip-sync
```

Expected: Research starts in background with nohup, PID shown, log file created.
