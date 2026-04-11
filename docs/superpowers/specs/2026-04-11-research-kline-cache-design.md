# Research Kline Cache — Design Spec

**Date:** 2026-04-11
**Status:** Approved
**Scope:** Research pipeline only (live trading untouched)

## Problem

The research pipeline makes 5,000+ Binance API calls per full run (107 candidates × ~50 calls each). The existing `.cache/` has a 1-hour TTL and keys are too specific (exact start/end timestamps), causing 100% cache misses across candidates and walk-forward folds. This makes every run take 10-22 hours and 5 of 9 runs have died from Binance API connectivity issues.

Historical kline data is immutable — yesterday's candles never change. There's no reason to re-fetch them.

## Solution

A persistent kline cache layer that sits between the research pipeline and Binance API. Data is stored as parquet files (one per symbol+interval). The pipeline pre-downloads all needed data upfront in a single pass, then all backtesting reads from memory — zero API calls during the actual research.

### Approach: Provider Callback

`run_backtest()` gets an optional `kline_provider` parameter that defaults to `fetch_klines_range` (backward compatible). The research pipeline passes `cache.get` as the provider.

## Architecture

### New: `bot/research/data_cache.py`

```python
class KlineCache:
    """Persistent kline cache for research.
    One parquet per symbol+interval in data/research_cache/.
    Historical candles never expire; today's candles refresh hourly."""
    
    def __init__(self, cache_dir: str = "data/research_cache"):
        """Initialize cache with directory path."""
    
    def prefetch(self, symbols: list[str], interval: str, 
                 days: int, max_offset_days: int = 0) -> dict:
        """Download all needed data upfront.
        
        - Computes total range: days + max_offset_days
        - Always includes BTCUSDT for regime detection
        - For each symbol: loads existing parquet, identifies gaps, 
          fetches only missing ranges from API
        - Loads all data into memory for fast access
        - Returns: {symbol: row_count} summary
        
        Raises if API unreachable (don't start pipeline with incomplete data).
        """
    
    def get(self, symbol: str, interval: str, 
            start_ms: int, end_ms: int, use_cache: bool = True) -> pd.DataFrame:
        """Drop-in replacement for fetch_klines_range().
        
        - Slices requested range from in-memory cache
        - Falls back to fetch_klines_range() if symbol not cached
        - Signature matches fetch_klines_range() exactly
        """
    
    def stats(self) -> dict:
        """Return cache statistics: symbols, rows, disk size, staleness."""
```

### Modified: `bot/backtester.py`

```python
def run_backtest(
    symbols: list[str],
    interval: str = "1h",
    days: int = 90,
    cfg_override: dict = None,
    end_offset_days: int = 0,
    kline_provider: Callable = None,  # NEW — default: fetch_klines_range
) -> dict:
```

All internal `fetch_klines_range()` calls replaced with `kline_provider()`.

### Modified: `bot/research/pipeline.py`

```python
class ResearchPipeline:
    def run_full(self, families=None, max_per_family=None):
        # Pre-fetch ALL data for ALL stages
        cache = KlineCache()
        max_offset = self._calc_max_walk_forward_offset()
        cache.prefetch(self.symbols, self.interval, self.days, max_offset)
        
        # All stages use cache.get as kline_provider
        stage1 = self.run_stage1(candidates, kline_provider=cache.get)
        stage2 = self.run_stage2(survivors, kline_provider=cache.get)
```

### Unchanged

- `bot/data_fetcher.py` — not modified
- `bot/main_multi.py` — live trading uses API directly
- `bot/scorer.py`, `bot/indicators.py` — no data fetching
- All existing tests — `kline_provider=None` preserves old behavior

## Cache Intelligence

### Gap Detection

When existing cache covers `[Jan 1, Mar 15]` and pipeline needs `[Dec 1, Apr 10]`:
- Only fetch `Dec 1→Jan 1` and `Mar 15→Apr 10`
- Append to existing parquet, deduplicate by timestamp

### TTL Strategy

- Candles before today 00:00 UTC: **never expire** (immutable historical data)
- Today's candles: **refresh if parquet mtime > 1 hour old** (still forming)
- Re-running research next week only fetches ~24 new candles per symbol

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Corrupted parquet | Delete file, re-fetch entirely |
| API down during prefetch | Raise immediately — don't start pipeline with gaps |
| Symbol not in cache during `get()` | Fallback to `fetch_klines_range()` + log warning |
| Empty result from cache slice | Fallback to API (safety net) |

## Storage

- Location: `data/research_cache/`
- Format: Parquet (one file per `{symbol}_{interval}.parquet`)
- Schema: `timestamp (int64), open, high, low, close, volume (float64)`
- Size: ~3MB total for 15 symbols × 180 days of hourly data
- Add `data/research_cache/` to `.gitignore`

## Testing

### Unit tests (`tests/test_data_cache.py`)

1. `test_prefetch_creates_parquet_files` — files created with correct schema
2. `test_get_returns_correct_range` — time-slice accuracy
3. `test_get_fallback_on_miss` — API fallback for uncached symbols
4. `test_prefetch_only_fetches_gaps` — mock API verifies only gaps requested
5. `test_prefetch_includes_btcusdt` — BTC always included
6. `test_corrupted_parquet_recovery` — corrupt → delete → re-fetch
7. `test_today_candles_refresh` — mtime-based refresh for today's data
8. `test_kline_provider_backward_compat` — `run_backtest(kline_provider=None)` unchanged
9. `test_pipeline_uses_cache` — mock pipeline, zero API calls during backtest
10. `test_full_prefetch_and_backtest` — end-to-end with real (small) data

## Performance Expectations

| Metric | Before (no cache) | After (cached) |
|--------|-------------------|----------------|
| First run, 15 symbols × 180d | ~50 API calls/candidate × 107 = 5,350 calls | ~50 calls total (one-time prefetch) |
| Subsequent runs, same symbols | Same 5,350 calls | ~15 calls (today's candles only) |
| Stage 1 time per candidate | 3-5 min (API-bound) | <10 sec (memory-bound) |
| Full pipeline (107 candidates) | 10-22 hours | ~30-60 min (estimated) |
| Binance API failure impact | Pipeline dies | Only prefetch affected; retry prefetch alone |

## Walk-Forward Coverage

Stage 2 default: train=120d, test=60d, slide=30d → ~4 folds → max offset ≈ 90 days.
Prefetch range: `days + max_offset_days = 180 + 90 = 270 days` from now.
This ensures all walk-forward folds hit cache.
