# Research Kline Cache — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent kline data cache so the research pipeline downloads data once, then all backtesting reads from memory — eliminating 5,000+ redundant API calls per run.

**Architecture:** New `KlineCache` class stores parquet files per symbol+interval in `data/research_cache/`. `run_backtest()` gets an optional `kline_provider` callback (defaults to `fetch_klines_range` for backward compat). Pipeline pre-fetches all data upfront, then passes `cache.get` as the provider.

**Tech Stack:** Python, pandas, pyarrow (parquet), pytest, unittest.mock

---

## Task 1: Create KlineCache class with tests

**Files:**
- Create: `bot/research/data_cache.py`
- Create: `tests/research/test_data_cache.py`

- [ ] **Step 1: Write failing test — cache init creates directory**

```python
# tests/research/test_data_cache.py
import os
import tempfile
import shutil
import time
import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from bot.research.data_cache import KlineCache


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "test_cache"
    return str(d)


@pytest.fixture
def cache(cache_dir):
    return KlineCache(cache_dir=cache_dir)


def _make_klines(start_ms: int, hours: int, interval_ms: int = 3600000) -> pd.DataFrame:
    """Helper: create synthetic kline DataFrame."""
    n = hours
    timestamps = [pd.Timestamp(start_ms + i * interval_ms, unit="ms") for i in range(n)]
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": np.random.uniform(100, 200, n),
        "high": np.random.uniform(200, 300, n),
        "low": np.random.uniform(50, 100, n),
        "close": np.random.uniform(100, 200, n),
        "volume": np.random.uniform(1000, 5000, n),
    })


class TestKlineCacheInit:
    def test_creates_directory(self, cache_dir):
        assert not os.path.exists(cache_dir)
        KlineCache(cache_dir=cache_dir)
        assert os.path.isdir(cache_dir)

    def test_default_cache_dir(self):
        cache = KlineCache()
        assert os.path.isdir("data/research_cache")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_data_cache.py::TestKlineCacheInit -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.research.data_cache'`

- [ ] **Step 3: Write minimal KlineCache skeleton**

```python
# bot/research/data_cache.py
"""Persistent kline cache for research pipeline.

Stores one parquet file per symbol+interval in data/research_cache/.
Historical candles never expire; today's candles refresh hourly.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from bot.data_fetcher import fetch_klines_range

logger = logging.getLogger(__name__)


class KlineCache:
    """Persistent kline cache for research.

    Usage:
        cache = KlineCache()
        cache.prefetch(["BTCUSDT", "ETHUSDT"], "1h", days=180)
        df = cache.get("BTCUSDT", "1h", start_ms, end_ms)
    """

    def __init__(self, cache_dir: str = "data/research_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[tuple[str, str], pd.DataFrame] = {}

    def _parquet_path(self, symbol: str, interval: str) -> Path:
        return self.cache_dir / f"{symbol}_{interval}.parquet"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/research/test_data_cache.py::TestKlineCacheInit -v`
Expected: PASS

- [ ] **Step 5: Write failing tests — prefetch**

Add to `tests/research/test_data_cache.py`:

```python
class TestPrefetch:
    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_creates_parquet_files(self, mock_fetch, cache):
        start_ms = int(time.time() * 1000) - 7 * 86400000  # 7 days ago
        end_ms = int(time.time() * 1000)
        klines = _make_klines(start_ms, hours=168)  # 7 days hourly
        mock_fetch.return_value = klines

        result = cache.prefetch(["ETHUSDT"], "1h", days=7)

        # Should create parquet for ETHUSDT + BTCUSDT (always included)
        assert os.path.exists(cache._parquet_path("ETHUSDT", "1h"))
        assert os.path.exists(cache._parquet_path("BTCUSDT", "1h"))
        assert "ETHUSDT" in result
        assert "BTCUSDT" in result

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_includes_btcusdt(self, mock_fetch, cache):
        mock_fetch.return_value = _make_klines(0, hours=48)
        cache.prefetch(["SOLUSDT"], "1h", days=2)
        # BTCUSDT always added even if not in symbols list
        assert mock_fetch.call_count >= 2
        called_symbols = [call[0][0] for call in mock_fetch.call_args_list]
        assert "BTCUSDT" in called_symbols
        assert "SOLUSDT" in called_symbols

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_only_fetches_gaps(self, mock_fetch, cache):
        """If parquet already exists with data, only fetch missing ranges."""
        # Pre-populate cache with 3 days of data
        existing = _make_klines(1000000000000, hours=72)  # 3 days
        existing.to_parquet(cache._parquet_path("ETHUSDT", "1h"))

        new_data = _make_klines(1000000000000 + 72 * 3600000, hours=24)
        mock_fetch.return_value = new_data

        # Request 4 days — should only fetch the 1-day gap
        cache.prefetch(["ETHUSDT"], "1h", days=4)

        # Check that we didn't re-fetch the full 4 days
        for call in mock_fetch.call_args_list:
            args = call[0]
            if args[0] == "ETHUSDT":
                # The start_ms should be AFTER existing data ends
                fetch_start = args[2]
                existing_end = int(existing["timestamp"].iloc[-1].timestamp() * 1000)
                assert fetch_start >= existing_end - 3600000  # within 1 candle tolerance

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_prefetch_with_max_offset(self, mock_fetch, cache):
        """max_offset_days extends the prefetch range for walk-forward."""
        mock_fetch.return_value = _make_klines(0, hours=48)
        cache.prefetch(["ETHUSDT"], "1h", days=180, max_offset_days=90)
        # Total range should be 270 days
        for call in mock_fetch.call_args_list:
            args = call[0]
            start_ms = args[2]
            end_ms = args[3]
            range_days = (end_ms - start_ms) / 86400000
            assert range_days >= 269  # 270 days with rounding tolerance
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/research/test_data_cache.py::TestPrefetch -v`
Expected: FAIL with `AttributeError: 'KlineCache' object has no attribute 'prefetch'`

- [ ] **Step 7: Implement prefetch method**

Add to `bot/research/data_cache.py` inside `KlineCache`:

```python
    def prefetch(
        self,
        symbols: list[str],
        interval: str,
        days: int,
        max_offset_days: int = 0,
    ) -> dict[str, int]:
        """Download all needed kline data upfront. Only fetches gaps.

        Args:
            symbols: Trading pair symbols to cache.
            interval: Candle interval (e.g., "1h").
            days: Number of days of history needed.
            max_offset_days: Extra days for walk-forward folds.

        Returns:
            Dict mapping symbol → number of cached rows.
        """
        total_days = days + max_offset_days
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (total_days * 24 * 3600 * 1000)

        all_symbols = list(dict.fromkeys(["BTCUSDT"] + list(symbols)))
        result = {}

        for symbol in all_symbols:
            path = self._parquet_path(symbol, interval)
            logger.info("[Cache] Processing %s...", symbol)

            if path.exists():
                try:
                    existing = pd.read_parquet(path)
                    if existing.empty or "timestamp" not in existing.columns:
                        raise ValueError("Empty or malformed parquet")
                except Exception:
                    logger.warning("[Cache] Corrupted parquet for %s, re-fetching", symbol)
                    path.unlink()
                    existing = None
            else:
                existing = None

            if existing is not None:
                existing_start_ms = int(existing["timestamp"].min().timestamp() * 1000)
                existing_end_ms = int(existing["timestamp"].max().timestamp() * 1000)
                parts = [existing]

                # Fetch gap before existing data
                if start_ms < existing_start_ms - 3600000:
                    logger.info("[Cache]   Fetching pre-gap: %s → %s",
                                pd.Timestamp(start_ms, unit="ms"),
                                pd.Timestamp(existing_start_ms, unit="ms"))
                    pre = fetch_klines_range(symbol, interval, start_ms, existing_start_ms)
                    if not pre.empty:
                        parts.insert(0, pre)

                # Fetch gap after existing data (today's data or new days)
                today_start_ms = _today_start_ms()
                if existing_end_ms < end_ms:
                    # Only re-fetch if existing end is before today or parquet is stale
                    if existing_end_ms < today_start_ms or _is_stale(path):
                        fetch_from = max(existing_end_ms, today_start_ms)
                        logger.info("[Cache]   Fetching post-gap: %s → %s",
                                    pd.Timestamp(fetch_from, unit="ms"),
                                    pd.Timestamp(end_ms, unit="ms"))
                        post = fetch_klines_range(symbol, interval, fetch_from, end_ms)
                        if not post.empty:
                            parts.append(post)

                merged = pd.concat(parts, ignore_index=True)
                merged = merged.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
            else:
                logger.info("[Cache]   Full download: %s → %s",
                            pd.Timestamp(start_ms, unit="ms"),
                            pd.Timestamp(end_ms, unit="ms"))
                merged = fetch_klines_range(symbol, interval, start_ms, end_ms)

            if not merged.empty:
                merged.to_parquet(path)
                self._memory[(symbol, interval)] = merged
                result[symbol] = len(merged)
                logger.info("[Cache]   %s: %d candles cached", symbol, len(merged))
            else:
                logger.warning("[Cache]   %s: no data returned", symbol)
                result[symbol] = 0

        return result
```

Also add these module-level helpers:

```python
def _today_start_ms() -> int:
    """Return millisecond timestamp for today 00:00 UTC."""
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return int(today.timestamp() * 1000)


def _is_stale(path: Path, max_age_seconds: int = 3600) -> bool:
    """Check if a file is older than max_age_seconds."""
    if not path.exists():
        return True
    return (time.time() - path.stat().st_mtime) > max_age_seconds
```

- [ ] **Step 8: Run prefetch tests**

Run: `uv run pytest tests/research/test_data_cache.py::TestPrefetch -v`
Expected: PASS

- [ ] **Step 9: Write failing tests — get method**

Add to `tests/research/test_data_cache.py`:

```python
class TestGet:
    @patch("bot.research.data_cache.fetch_klines_range")
    def test_get_returns_correct_range(self, mock_fetch, cache):
        """get() should slice from cached data, not call API."""
        full_data = _make_klines(1000000000000, hours=168)  # 7 days
        cache._memory[("ETHUSDT", "1h")] = full_data

        start_ms = 1000000000000 + 24 * 3600000  # day 2
        end_ms = 1000000000000 + 72 * 3600000    # day 3 end

        result = cache.get("ETHUSDT", "1h", start_ms, end_ms)

        assert len(result) > 0
        assert len(result) <= 48 + 1  # ~48 hours of data
        mock_fetch.assert_not_called()  # Should NOT call API

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_get_fallback_on_miss(self, mock_fetch, cache):
        """get() falls back to API if symbol not in cache."""
        fallback_data = _make_klines(0, hours=24)
        mock_fetch.return_value = fallback_data

        result = cache.get("UNKNOWN", "1h", 0, 86400000)

        mock_fetch.assert_called_once()
        assert len(result) == 24

    def test_get_loads_from_parquet_on_first_access(self, cache):
        """get() loads parquet into memory if not already loaded."""
        data = _make_klines(1000000000000, hours=48)
        data.to_parquet(cache._parquet_path("BNBUSDT", "1h"))

        result = cache.get("BNBUSDT", "1h", 1000000000000, 1000000000000 + 48 * 3600000)
        assert len(result) > 0
        assert ("BNBUSDT", "1h") in cache._memory

    @patch("bot.research.data_cache.fetch_klines_range")
    def test_get_empty_slice_falls_back(self, mock_fetch, cache):
        """If cache slice returns empty, fall back to API."""
        cache._memory[("ETHUSDT", "1h")] = _make_klines(1000000000000, hours=24)
        mock_fetch.return_value = _make_klines(9999999999999, hours=24)

        # Request range far outside cached data
        result = cache.get("ETHUSDT", "1h", 9999999999999, 9999999999999 + 86400000)
        mock_fetch.assert_called_once()
```

- [ ] **Step 10: Run get tests to verify failure**

Run: `uv run pytest tests/research/test_data_cache.py::TestGet -v`
Expected: FAIL with `AttributeError: 'KlineCache' object has no attribute 'get'`

- [ ] **Step 11: Implement get method**

Add to `bot/research/data_cache.py` inside `KlineCache`:

```python
    def get(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Return cached klines for the given range.

        Signature matches fetch_klines_range() for drop-in replacement.
        Falls back to live API if symbol not cached.
        """
        key = (symbol, interval)

        if key not in self._memory:
            path = self._parquet_path(symbol, interval)
            if path.exists():
                try:
                    self._memory[key] = pd.read_parquet(path)
                except Exception:
                    logger.warning("[Cache] Failed to read %s, falling back to API", path)
                    return fetch_klines_range(symbol, interval, start_ms, end_ms)
            else:
                logger.warning("[Cache] %s not cached, falling back to API", symbol)
                return fetch_klines_range(symbol, interval, start_ms, end_ms)

        df = self._memory[key]
        start_ts = pd.Timestamp(start_ms, unit="ms")
        end_ts = pd.Timestamp(end_ms, unit="ms")
        mask = (df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)
        result = df[mask].copy().reset_index(drop=True)

        if result.empty:
            logger.warning("[Cache] Empty slice for %s [%s, %s], falling back to API",
                           symbol, start_ts, end_ts)
            return fetch_klines_range(symbol, interval, start_ms, end_ms)

        return result

    def stats(self) -> dict:
        """Return cache statistics."""
        total_rows = sum(len(df) for df in self._memory.values())
        disk_bytes = sum(
            f.stat().st_size for f in self.cache_dir.iterdir() if f.suffix == ".parquet"
        )
        return {
            "symbols": len(self._memory),
            "total_rows": total_rows,
            "disk_mb": round(disk_bytes / 1024 / 1024, 2),
            "cached_pairs": list(self._memory.keys()),
        }
```

- [ ] **Step 12: Run all cache tests**

Run: `uv run pytest tests/research/test_data_cache.py -v`
Expected: ALL PASS

- [ ] **Step 13: Write failing test — corrupted parquet recovery**

Add to `tests/research/test_data_cache.py`:

```python
class TestErrorHandling:
    def test_corrupted_parquet_recovery_in_prefetch(self, cache):
        """Corrupted parquet should be deleted and re-fetched."""
        path = cache._parquet_path("XRPUSDT", "1h")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("this is not a valid parquet file")

        with patch("bot.research.data_cache.fetch_klines_range") as mock_fetch:
            mock_fetch.return_value = _make_klines(0, hours=48)
            cache.prefetch(["XRPUSDT"], "1h", days=2)

        # Should have re-fetched
        assert ("XRPUSDT", "1h") in cache._memory
        assert len(cache._memory[("XRPUSDT", "1h")]) == 48

    def test_corrupted_parquet_recovery_in_get(self, cache):
        """Corrupted parquet in get() falls back to API."""
        path = cache._parquet_path("ADAUSDT", "1h")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("corrupt data")

        with patch("bot.research.data_cache.fetch_klines_range") as mock_fetch:
            mock_fetch.return_value = _make_klines(0, hours=24)
            result = cache.get("ADAUSDT", "1h", 0, 86400000)

        mock_fetch.assert_called_once()
        assert len(result) == 24
```

- [ ] **Step 14: Run error handling tests**

Run: `uv run pytest tests/research/test_data_cache.py::TestErrorHandling -v`
Expected: PASS (implementation already handles this)

- [ ] **Step 15: Commit Task 1**

```bash
git add bot/research/data_cache.py tests/research/test_data_cache.py
git commit -m "feat: add KlineCache for persistent research data caching

New bot/research/data_cache.py with:
- KlineCache.prefetch() — downloads all data upfront, only fetches gaps
- KlineCache.get() — drop-in replacement for fetch_klines_range()
- Smart gap detection, corrupted parquet recovery, today's data refresh
- 10+ tests in tests/research/test_data_cache.py

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Wire kline_provider into backtester

**Files:**
- Modify: `bot/backtester.py` (lines 167-204)
- Modify: `tests/test_backtester_summary.py` (add backward compat test)

- [ ] **Step 1: Write failing test — kline_provider param**

Add to `tests/test_backtester_summary.py`:

```python
class TestKlineProvider:
    """Test that run_backtest accepts and uses kline_provider callback."""

    @patch("bot.backtester.fetch_klines_range")
    def test_kline_provider_none_uses_default(self, mock_fetch):
        """kline_provider=None should use fetch_klines_range (backward compat)."""
        mock_fetch.return_value = pd.DataFrame()
        try:
            run_backtest(["ETHUSDT"], "1h", days=7, kline_provider=None)
        except Exception:
            pass
        # Should have called fetch_klines_range for BTC at minimum
        assert mock_fetch.called

    @patch("bot.backtester.fetch_klines_range")
    def test_kline_provider_custom_is_used(self, mock_fetch):
        """Custom kline_provider should be called instead of fetch_klines_range."""
        custom_provider = MagicMock()
        # Return enough data for BTC and one symbol
        btc_data = _make_klines(1000000000000, hours=168)  # 7 days
        sym_data = _make_klines(1000000000000, hours=168)
        custom_provider.side_effect = [btc_data, sym_data]

        result = run_backtest(
            ["ETHUSDT"], "1h", days=7,
            kline_provider=custom_provider,
        )

        # Custom provider should be called, NOT fetch_klines_range
        assert custom_provider.call_count >= 2
        mock_fetch.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_backtester_summary.py::TestKlineProvider -v`
Expected: FAIL with `TypeError: run_backtest() got an unexpected keyword argument 'kline_provider'`

- [ ] **Step 3: Add kline_provider parameter to run_backtest**

In `bot/backtester.py`, modify `run_backtest` signature and body:

```python
def run_backtest(symbols: list[str], interval: str = "1h",
                 days: int = 90, cfg_override: dict = None,
                 end_offset_days: int = 0,
                 kline_provider=None) -> dict:
    """
    Run backtest across multiple pairs.

    Args:
        kline_provider: Optional callable matching fetch_klines_range() signature.
                       If None, uses fetch_klines_range (backward compatible).
    """
    if kline_provider is None:
        kline_provider = fetch_klines_range

    end_ms = int(time.time() * 1000) - (end_offset_days * 24 * 3600 * 1000)
    start_ms = end_ms - (days * 24 * 3600 * 1000)

    print(f"[Backtest] Fetching BTC data...", flush=True)
    btc_df = kline_provider("BTCUSDT", interval, start_ms, end_ms)

    print(f"[Backtest] Pre-computing BTC regime series...", flush=True)
    btc_regime_map = _precompute_btc_regimes(btc_df)

    all_trades = []
    sym_summaries = []
    for i, sym in enumerate(symbols):
        print(f"[Backtest] ({i+1}/{len(symbols)}) {sym}...", flush=True)
        try:
            klines = kline_provider(sym, interval, start_ms, end_ms)
            if len(klines) < 100:
                print(f"  Skipping {sym}: only {len(klines)} candles", flush=True)
                continue
            trades = backtest_pair(sym, klines, btc_df, cfg_override,
                                   btc_regime_map=btc_regime_map)
            all_trades.extend(trades)
            sym_summaries.append(_summarize(trades))
            print(f"  → {len(trades)} trades", flush=True)
        except Exception as e:
            print(f"  Error {sym}: {e}", flush=True)
            continue

    if not sym_summaries:
        return _summarize([])

    combined = _summarize(all_trades)
    active = [s for s in sym_summaries if s["trades"] > 0]
    if active:
        combined["return_pct"] = sum(s["return_pct"] for s in active) / len(active)
        combined["max_dd"] = sum(s["max_dd"] for s in active) / len(active)
    return combined
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_backtester_summary.py::TestKlineProvider -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All 359+ tests pass

- [ ] **Step 6: Commit Task 2**

```bash
git add bot/backtester.py tests/test_backtester_summary.py
git commit -m "feat: add kline_provider param to run_backtest()

Backward compatible: kline_provider=None uses fetch_klines_range.
Allows research pipeline to inject cache.get for zero-API backtesting.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Wire KlineCache into research pipeline

**Files:**
- Modify: `bot/research/pipeline.py` (lines 57-101 run_stage1, 104-178 run_stage2, 180-243 run_stage3, 245-280 run_stage4, 282-306 run_full, 308-336 run_full_4stage)
- Modify: `tests/research/test_pipeline.py` (add cache integration test)

- [ ] **Step 1: Write failing test — pipeline uses cache**

Add to `tests/research/test_pipeline.py`:

```python
class TestPipelineCache:
    """Test that pipeline uses KlineCache when available."""

    @patch("bot.research.pipeline.KlineCache")
    @patch("bot.research.pipeline.run_backtest")
    @patch("bot.research.pipeline.wait_for_connectivity")
    def test_run_full_prefetches_and_passes_provider(self, mock_wait, mock_bt, mock_cache_cls, pipeline):
        """run_full should prefetch data and pass cache.get as kline_provider."""
        mock_cache = MagicMock()
        mock_cache.prefetch.return_value = {"BTCUSDT": 4320, "ETHUSDT": 4320}
        mock_cache_cls.return_value = mock_cache

        mock_bt.return_value = {
            "trades": 50, "win_rate": 55, "return_pct": 10.0, "max_dd": 20.0,
            "sharpe": 0.8, "calmar": 0.5, "profit_factor": 1.3,
            "final_equity": 1100, "wins": 28, "losses": 22,
            "sortino": 1.0, "trade_details": [],
        }

        pipeline.run_full(families=["ema_crossover"], max_per_family=1)

        # Verify cache was created and prefetch called
        mock_cache_cls.assert_called_once()
        mock_cache.prefetch.assert_called_once()

        # Verify run_backtest was called with kline_provider=cache.get
        for call in mock_bt.call_args_list:
            assert "kline_provider" in call.kwargs
            assert call.kwargs["kline_provider"] == mock_cache.get
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/research/test_pipeline.py::TestPipelineCache -v`
Expected: FAIL (pipeline doesn't import or use KlineCache yet)

- [ ] **Step 3: Wire KlineCache into pipeline**

Modify `bot/research/pipeline.py`:

At the top, add import:
```python
from bot.research.data_cache import KlineCache
```

Modify `run_stage1` to accept `kline_provider`:
```python
    def run_stage1(
        self,
        candidates: list[PassportCandidate],
        kline_provider=None,
    ) -> list[PassportCandidate]:
        """Run Stage 1 viability on all candidates via backtesting."""
        survivors = []
        for i, candidate in enumerate(candidates):
            logger.info(
                "[Stage 1] %d/%d — %s", i + 1, len(candidates), candidate.slug,
            )
            try:
                kwargs = dict(
                    symbols=self.symbols,
                    interval=self.interval,
                    days=self.days,
                    cfg_override=candidate.config_overrides,
                )
                if kline_provider is not None:
                    kwargs["kline_provider"] = kline_provider
                summary = resilient_call(run_backtest, **kwargs)
                metrics = BacktestMetrics.from_summary(summary)
            except Exception as e:
                logger.warning("Backtest failed for %s: %s", candidate.slug, e)
                result = EvalResult(
                    passport_id=candidate.passport_id, stage=1, passed=False,
                    reject_reason=f"Backtest error: {e}",
                )
                self.tracker.log_eval(self.run_id, result)
                continue

            min_trades = SCORING_FAMILIES.get(
                candidate.family, {}
            ).get("min_trades", 30)
            result = self.stage1.evaluate(
                candidate.passport_id, metrics, min_trades=min_trades,
            )
            self.tracker.log_eval(self.run_id, result)

            if result.passed:
                candidate.status = "stage1_passed"
                survivors.append(candidate)
                logger.info("  PASS — return=%.1f%% dd=%.1f%% sharpe=%.2f",
                            metrics.return_pct, metrics.max_dd, metrics.sharpe)
            else:
                logger.info("  FAIL — %s", result.reject_reason)

        logger.info("Stage 1: %d/%d survived", len(survivors), len(candidates))
        return survivors
```

Apply the same `kline_provider` parameter pattern to `run_stage2`, `run_stage3`, and `run_stage4`. Each method passes `kline_provider` through to `resilient_call(run_backtest, ..., kline_provider=kline_provider)`.

For `run_stage2`, all `resilient_call(run_backtest, ...)` calls get the extra kwarg:
```python
    def run_stage2(
        self,
        candidates: list[PassportCandidate],
        train_days: int = 120,
        test_days: int = 60,
        kline_provider=None,
    ) -> list[PassportCandidate]:
        # ... existing code ...
        # In the fold loop, both train and test backtests:
                    bt_kwargs = dict(
                        symbols=self.symbols,
                        interval=self.interval,
                        days=train_days,
                        cfg_override=candidate.config_overrides,
                        end_offset_days=train_end_offset,
                    )
                    if kline_provider is not None:
                        bt_kwargs["kline_provider"] = kline_provider
                    train_summary = resilient_call(run_backtest, **bt_kwargs)

                    bt_kwargs = dict(
                        symbols=self.symbols,
                        interval=self.interval,
                        days=test_days,
                        cfg_override=candidate.config_overrides,
                        end_offset_days=test_end_offset,
                    )
                    if kline_provider is not None:
                        bt_kwargs["kline_provider"] = kline_provider
                    test_summary = resilient_call(run_backtest, **bt_kwargs)
```

For `run_stage3`:
```python
    def run_stage3(
        self,
        candidates: list[PassportCandidate],
        mc_iterations: int = 50,
        kline_provider=None,
    ) -> list[PassportCandidate]:
        # ... existing code ...
        # All resilient_call(run_backtest, ...) get kline_provider
```

For `run_stage4`:
```python
    def run_stage4(
        self,
        candidates: list[PassportCandidate],
        kline_provider=None,
    ) -> Stage4Result:
        # ... existing code ...
        # resilient_call(run_backtest, ...) gets kline_provider
```

Modify `run_full` to create cache and pass provider:
```python
    def run_full(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
    ) -> list[PassportCandidate]:
        """Run the 2-stage pipeline with persistent data caching."""
        logger.info("Checking Binance API connectivity before starting pipeline...")
        wait_for_connectivity(check_interval=30.0, max_wait=7200.0)

        # Pre-fetch all kline data upfront
        cache = KlineCache()
        folds = _calc_folds(self.days, 120, 60, slide=30)
        max_offset = max((f[0] for f in folds), default=0) + 60
        logger.info("Pre-fetching kline data (days=%d, max_offset=%d)...", self.days, max_offset)
        stats = cache.prefetch(self.symbols, self.interval, self.days, max_offset_days=max_offset)
        logger.info("Cache ready: %s", stats)

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

Modify `run_full_4stage` similarly:
```python
    def run_full_4stage(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
        mc_iterations: int = 50,
    ) -> Stage4Result:
        """Run the complete 4-stage pipeline with persistent data caching."""
        logger.info("Checking Binance API connectivity before starting pipeline...")
        wait_for_connectivity(check_interval=30.0, max_wait=7200.0)

        cache = KlineCache()
        folds = _calc_folds(self.days, 120, 60, slide=30)
        max_offset = max((f[0] for f in folds), default=0) + 60
        logger.info("Pre-fetching kline data (days=%d, max_offset=%d)...", self.days, max_offset)
        stats = cache.prefetch(self.symbols, self.interval, self.days, max_offset_days=max_offset)
        logger.info("Cache ready: %s", stats)

        candidates = self.generate_candidates(families, max_per_family)
        stage1_survivors = self.run_stage1(candidates, kline_provider=cache.get)
        stage2_survivors = self.run_stage2(stage1_survivors, kline_provider=cache.get)
        stage3_survivors = self.run_stage3(stage2_survivors, mc_iterations, kline_provider=cache.get)
        result = self.run_stage4(stage3_survivors, kline_provider=cache.get)

        self.tracker.finish_experiment(
            self.run_id,
            stage1_survivors=len(stage1_survivors),
            stage2_survivors=len(stage2_survivors),
        )

        logger.info(
            "4-stage pipeline: %d → %d S1 → %d S2 → %d S3 → %d selected",
            len(candidates), len(stage1_survivors), len(stage2_survivors),
            len(stage3_survivors), len(result.selected_passport_ids),
        )
        return result
```

- [ ] **Step 4: Run pipeline cache test**

Run: `uv run pytest tests/research/test_pipeline.py::TestPipelineCache -v`
Expected: PASS

- [ ] **Step 5: Run all pipeline tests**

Run: `uv run pytest tests/research/test_pipeline.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All 359+ tests pass

- [ ] **Step 7: Commit Task 3**

```bash
git add bot/research/pipeline.py tests/research/test_pipeline.py
git commit -m "feat: wire KlineCache into research pipeline

Pipeline now prefetches all kline data upfront via KlineCache,
then passes cache.get as kline_provider to all backtest calls.
Eliminates 5000+ redundant API calls per research run.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Add .gitignore entry and cache stats CLI

**Files:**
- Modify: `.gitignore`
- Modify: `run_research.py` (add cache stats logging)

- [ ] **Step 1: Add data/research_cache/ to .gitignore**

```bash
echo "" >> .gitignore
echo "# Research kline cache (persistent, per-machine)" >> .gitignore
echo "data/research_cache/" >> .gitignore
```

- [ ] **Step 2: Add cache stats logging to run_research.py**

After the pipeline finishes, add cache stats:

In `run_research.py`, after `pipeline.tracker.close()`:

```python
    # Log cache stats
    try:
        from bot.research.data_cache import KlineCache
        cache = KlineCache()
        stats = cache.stats()
        logger.info("Cache stats: %d symbols, %d rows, %.1f MB on disk",
                     stats["symbols"], stats["total_rows"], stats["disk_mb"])
    except Exception:
        pass
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit Task 4**

```bash
git add .gitignore run_research.py
git commit -m "chore: add research cache to gitignore + stats logging

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: End-to-end integration test

**Files:**
- Modify: `tests/research/test_data_cache.py` (add integration test)

- [ ] **Step 1: Write integration test**

Add to `tests/research/test_data_cache.py`:

```python
class TestIntegration:
    """End-to-end: prefetch → backtest with cache → verify results."""

    @patch("bot.research.data_cache.fetch_klines_range")
    @patch("bot.backtester.fetch_klines_range")
    def test_full_prefetch_then_backtest(self, mock_bt_fetch, mock_cache_fetch, cache):
        """Prefetch data, then run_backtest with cache.get — no API calls during backtest."""
        from bot.backtester import run_backtest

        now_ms = int(time.time() * 1000)
        start_ms = now_ms - 7 * 86400000

        # Create realistic 7-day data for BTC and ETH
        btc_data = _make_klines(start_ms, hours=168)
        eth_data = _make_klines(start_ms, hours=168)

        # Mock only the cache's fetch (for prefetch)
        call_count = [0]
        def side_effect(symbol, interval, s, e, **kw):
            call_count[0] += 1
            if symbol == "BTCUSDT":
                return btc_data
            return eth_data
        mock_cache_fetch.side_effect = side_effect

        # Prefetch populates cache
        cache.prefetch(["ETHUSDT"], "1h", days=7)
        prefetch_calls = call_count[0]
        assert prefetch_calls >= 2  # BTC + ETH

        # Now run backtest with cache.get — should NOT call backtester's fetch
        try:
            run_backtest(
                ["ETHUSDT"], "1h", days=7,
                kline_provider=cache.get,
            )
        except Exception:
            pass  # Backtest may fail on synthetic data, that's OK

        # The backtester's fetch_klines_range should NOT have been called
        mock_bt_fetch.assert_not_called()
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/research/test_data_cache.py::TestIntegration -v`
Expected: PASS

- [ ] **Step 3: Run full test suite — final verification**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit Task 5**

```bash
git add tests/research/test_data_cache.py
git commit -m "test: add end-to-end integration test for kline cache

Verifies prefetch → backtest with cache.get produces zero API calls
during the actual backtesting phase.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | KlineCache class + tests | `bot/research/data_cache.py`, `tests/research/test_data_cache.py` |
| 2 | `kline_provider` param in backtester | `bot/backtester.py`, `tests/test_backtester_summary.py` |
| 3 | Wire cache into pipeline | `bot/research/pipeline.py`, `tests/research/test_pipeline.py` |
| 4 | Gitignore + stats logging | `.gitignore`, `run_research.py` |
| 5 | End-to-end integration test | `tests/research/test_data_cache.py` |

**Total: 5 tasks, ~15 tests, 4 production files modified/created**
