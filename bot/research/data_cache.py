"""
Persistent kline data cache for the Cryptopass research pipeline.

Stores one parquet file per (symbol, interval). Historical candles never
expire; today's candles refresh if the file is older than 1 hour.
"""
import logging
import os
import time
from pathlib import Path

import pandas as pd

from bot.data_fetcher import fetch_klines_range

logger = logging.getLogger(__name__)

_MS_PER_HOUR = 3_600_000
_MS_PER_DAY = 86_400_000


def _today_start_ms() -> int:
    """Return midnight UTC today as unix-ms."""
    now = pd.Timestamp.now("UTC").normalize()
    return int(now.timestamp() * 1000)


class KlineCache:
    """
    Persistent parquet cache for kline data.

    Usage::

        cache = KlineCache()
        cache.prefetch(["ETHUSDT", "SOLUSDT"], "1h", days=90)
        df = cache.get("ETHUSDT", "1h", start_ms, end_ms)
    """

    def __init__(self, cache_dir: str = "data/research_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # (symbol, interval) -> DataFrame loaded from parquet
        self._memory: dict[tuple[str, str], pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parquet_path(self, symbol: str, interval: str) -> Path:
        return self.cache_dir / f"{symbol}_{interval}.parquet"

    def _load_parquet(self, symbol: str, interval: str) -> pd.DataFrame | None:
        """Read parquet from disk; return None if missing or corrupt."""
        path = self._parquet_path(symbol, interval)
        if not path.exists():
            return None
        try:
            return pd.read_parquet(path)
        except Exception:
            logger.warning("Corrupt parquet for %s %s — deleting", symbol, interval)
            path.unlink(missing_ok=True)
            return None

    def _save_parquet(self, symbol: str, interval: str, df: pd.DataFrame):
        df.to_parquet(self._parquet_path(symbol, interval), index=False)

    def _df_to_ms(self, df: pd.DataFrame) -> tuple[int, int]:
        """Return (min_ms, max_ms) of the timestamp column."""
        ts = df["timestamp"]
        return (
            int(ts.min().timestamp() * 1000),
            int(ts.max().timestamp() * 1000),
        )

    def _today_candles_stale(self, symbol: str, interval: str) -> bool:
        path = self._parquet_path(symbol, interval)
        if not path.exists():
            return True
        age = time.time() - path.stat().st_mtime
        return age > 3600  # older than 1 hour

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prefetch(
        self,
        symbols: list[str],
        interval: str,
        days: int,
        max_offset_days: int = 0,
    ) -> dict[str, int]:
        """
        Download kline data for all symbols (+ BTCUSDT) upfront.

        Only fetches gaps if a parquet file already exists.
        Returns ``{symbol: row_count}``.
        """
        all_symbols = list(dict.fromkeys(["BTCUSDT"] + list(symbols)))

        total_days = days + max_offset_days
        end_ms = _today_start_ms() + _MS_PER_DAY  # include today
        start_ms = end_ms - total_days * _MS_PER_DAY

        result: dict[str, int] = {}

        for symbol in all_symbols:
            try:
                existing = self._load_parquet(symbol, interval)

                if existing is None:
                    # Full fetch
                    df = fetch_klines_range(symbol, interval, start_ms, end_ms)
                    if not df.empty:
                        self._save_parquet(symbol, interval, df)
                    result[symbol] = len(df)
                    continue

                ex_min_ms, ex_max_ms = self._df_to_ms(existing)
                parts = [existing]

                # Gap before existing data
                if start_ms < ex_min_ms:
                    early = fetch_klines_range(symbol, interval, start_ms, ex_min_ms)
                    if not early.empty:
                        parts.insert(0, early)

                # Gap after existing data (or stale today candles)
                today_ms = _today_start_ms()
                need_tail = ex_max_ms < end_ms - _MS_PER_HOUR  # more than 1h gap
                if need_tail and (ex_max_ms < today_ms or self._today_candles_stale(symbol, interval)):
                    tail = fetch_klines_range(symbol, interval, ex_max_ms, end_ms)
                    if not tail.empty:
                        parts.append(tail)

                if len(parts) > 1:
                    combined = (
                        pd.concat(parts, ignore_index=True)
                        .drop_duplicates(subset=["timestamp"])
                        .sort_values("timestamp")
                        .reset_index(drop=True)
                    )
                    self._save_parquet(symbol, interval, combined)
                    self._memory.pop((symbol, interval), None)
                    result[symbol] = len(combined)
                else:
                    result[symbol] = len(existing)
            except Exception as e:
                logger.warning("Prefetch failed for %s: %s — will fall back to API", symbol, e)
                result[symbol] = 0

        return result

    def get(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        Return klines for the requested range from the in-memory cache.

        Falls back to ``fetch_klines_range()`` if:
        - ``use_cache`` is False
        - the symbol is not cached
        - the resulting slice is empty
        - the parquet file is corrupt
        """
        if not use_cache:
            return fetch_klines_range(symbol, interval, start_ms, end_ms, use_cache=False)

        # Load into memory on first access
        key = (symbol, interval)
        if key not in self._memory:
            df_disk = self._load_parquet(symbol, interval)
            if df_disk is None:
                logger.warning("Cache miss for %s %s — falling back to API", symbol, interval)
                return fetch_klines_range(symbol, interval, start_ms, end_ms)
            self._memory[key] = df_disk

        df = self._memory[key]
        start_ts = pd.Timestamp(start_ms, unit="ms")
        end_ts = pd.Timestamp(end_ms, unit="ms")
        sliced = df[(df["timestamp"] >= start_ts) & (df["timestamp"] < end_ts)].copy()

        if sliced.empty:
            logger.debug("Cache miss (empty slice) for %s — falling back to API", symbol)
            return fetch_klines_range(symbol, interval, start_ms, end_ms)

        return sliced.reset_index(drop=True)

    def stats(self) -> dict:
        """Return cache statistics: symbols, rows, disk size, staleness."""
        parquet_files = list(self.cache_dir.glob("*.parquet"))
        total_rows = 0
        total_bytes = 0
        symbols_cached = []
        oldest_mtime = float("inf")
        newest_mtime = 0.0

        now = time.time()
        for f in parquet_files:
            try:
                df = pd.read_parquet(f)
                total_rows += len(df)
                total_bytes += f.stat().st_size
                mtime = f.stat().st_mtime
                oldest_mtime = min(oldest_mtime, mtime)
                newest_mtime = max(newest_mtime, mtime)
                name = f.stem  # e.g. ETHUSDT_1h
                symbols_cached.append(name)
            except Exception:
                pass

        staleness_seconds = (now - newest_mtime) if newest_mtime > 0 else None

        return {
            "cache_dir": str(self.cache_dir),
            "files": len(parquet_files),
            "symbols_cached": symbols_cached,
            "total_rows": total_rows,
            "disk_size_bytes": total_bytes,
            "staleness_seconds": staleness_seconds,
            "memory_loaded": [f"{s}_{i}" for s, i in self._memory.keys()],
        }

    def cleanup(self, max_age_days: int = 7) -> list[str]:
        """Remove parquet files older than max_age_days.

        Also clears memory cache entries for removed files.
        Returns list of removed file paths.
        """
        cutoff = time.time() - max_age_days * 86400
        removed: list[str] = []

        for path in self.cache_dir.glob("*.parquet"):
            if path.stat().st_mtime < cutoff:
                stem = path.stem
                parts = stem.rsplit("_", 1)
                if len(parts) == 2:
                    self._memory.pop((parts[0], parts[1]), None)

                logger.info("Removing stale parquet: %s (age: %.0f days)",
                            path.name, (time.time() - path.stat().st_mtime) / 86400)
                path.unlink()
                removed.append(str(path))

        return removed
