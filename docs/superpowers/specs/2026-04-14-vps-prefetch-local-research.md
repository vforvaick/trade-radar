# VPS Prefetch + Local Research Pipeline

**Date:** 2026-04-14
**Problem:** MacBook can't hit Binance API without VPN. VPS always can. Research needs local compute.
**Solution:** Prefetch kline data on VPS, sync to local, run research offline.

---

## Architecture

```
┌─────────────┐    SSH + run      ┌─────────────┐    Binance API    ┌──────────┐
│   MacBook    │ ───────────────→ │     VPS      │ ──────────────→  │ Binance  │
│  (compute)   │                  │ (fight-tres) │                  │  fAPI    │
│              │ ← SCP parquets ← │              │ ← klines data ← │          │
└─────────────┘                   └─────────────┘                   └──────────┘
       │
       ▼
  run_research.py --offline
  (uses local parquets, no API)
```

## Components

### 1. `scripts/prefetch_klines_vps.py` — Runs ON VPS

**Purpose:** Download kline data from Binance into `data/research_cache/` parquets.

**Interface:**
```bash
python scripts/prefetch_klines_vps.py --days 180 --pairs 15 --interval 1h
python scripts/prefetch_klines_vps.py --quality-pairs --days 270
```

**Behavior:**
- Uses existing `KlineCache.prefetch()` as core engine
- Discovers top-N symbols via `get_all_futures_symbols()` (or uses `--quality-pairs` hardcoded list)
- Always includes BTCUSDT (needed for regime detection)
- Outputs summary: symbols fetched, total rows, cache size, elapsed time

**Rate limit handling (new):**
- Wraps `data_fetcher.fetch_klines_range()` with retry decorator
- On HTTP 429 or 418: exponential backoff (1s → 2s → 4s → 8s → 16s → 32s → 60s cap)
- Max 5 retries per request before marking symbol as failed
- 200ms delay between symbols (up from 150ms, safe margin)
- On connection error: retry up to 3 times with 5s delay
- Summary at end: N succeeded, M failed, list of failed symbols

**Error resilience:**
- Each symbol fetched independently — one failure doesn't stop others
- Partial data saved (if 80/100 candle batches succeed, save what we have)
- Corrupt parquet detection and auto-recovery (existing KlineCache behavior)

### 2. `KlineCache.cleanup()` — Stale parquet removal

**Purpose:** Remove parquets older than N days to prevent stale data pollution.

**Interface:**
```python
cache = KlineCache()
removed = cache.cleanup(max_age_days=7)  # returns list of removed files
```

**Behavior:**
- Scans `data/research_cache/*.parquet`
- Checks file modification time (`os.path.getmtime`)
- Removes files where `now - mtime > max_age_days`
- Returns list of removed file paths
- Logs each removal

**Integration:** Called at start of sync script, before prefetch.

### 3. `scripts/sync_research_data.sh` — Runs on MacBook

**Purpose:** One command to sync fresh kline data from VPS to local.

**Interface:**
```bash
./scripts/sync_research_data.sh                    # defaults: 180 days, 15 pairs
./scripts/sync_research_data.sh --days 270 --pairs 20
./scripts/sync_research_data.sh --quality-pairs --days 180
./scripts/sync_research_data.sh --sync-only        # skip prefetch, just SCP
```

**Steps:**
1. **Cleanup local stale parquets** — remove parquets >7 days old from local `data/research_cache/`
2. **SSH to VPS** → run `prefetch_klines_vps.py` with passed args
3. **SCP download** — `scp -r fight-tres:/home/vforvaick/pumpradar-bot/data/research_cache/ ./data/research_cache/`
4. **Verify** — count parquet files, print total size, check BTCUSDT exists
5. **Summary** — print stats and "Ready for offline research" message

**VPS paths:**
- Remote repo: `/home/vforvaick/pumpradar-bot`
- Remote cache: `/home/vforvaick/pumpradar-bot/data/research_cache/`
- SSH alias: `fight-tres`
- Python: `.venv/bin/python` (system python3 lacks pandas/pyarrow — must use .venv)

**Error handling:**
- SSH connection failure → clear error message, suggest checking VPN/SSH config
- Prefetch failure on VPS → show VPS stderr, still attempt SCP of existing data
- SCP failure → clear error message with retry suggestion
- Missing BTCUSDT parquet → warning (research will fail without it)

### 4. `run_research.py --offline` flag

**Purpose:** Run research pipeline using only local cached parquets, no API calls.

**Changes to existing code:**
- Add `--offline` flag to argparse
- When `--offline`:
  - Skip `wait_for_connectivity()` call
  - Skip `cache.prefetch()` call in pipeline
  - Load from existing `data/research_cache/` parquets only
  - Fail fast with clear message if required parquets missing
  - Print cache stats at startup (files, total rows, freshness)

**Pipeline changes (`bot/research/pipeline.py`):**
- `run_full()` accepts `offline: bool = False` parameter
- When offline, skip prefetch, call `cache.stats()` to verify data exists
- Minimum check: BTCUSDT parquet must exist, at least 5 symbol parquets

### 5. `scripts/research_local.sh` — Convenience wrapper

**Purpose:** Single command for the full workflow: sync + research.

**Interface:**
```bash
./scripts/research_local.sh                          # sync + research defaults
./scripts/research_local.sh --days 180 --families rsi_momentum,hidden_gem_variant
./scripts/research_local.sh --skip-sync              # use existing local data
```

**Steps:**
1. Run `sync_research_data.sh` (unless `--skip-sync`)
2. Run `uv run python run_research.py --offline --all --max-per-family 5 --days 180`
3. Print final summary

**Process management:**
- Uses `nohup` for the research step (survives terminal close)
- Outputs PID for monitoring
- Logs to `logs/research_local_YYYYMMDD_HHMMSS.log`

---

## File Changes Summary

| File | Action | Description |
|---|---|---|
| `scripts/prefetch_klines_vps.py` | **CREATE** | VPS-side kline prefetcher with retry logic |
| `bot/research/data_cache.py` | **MODIFY** | Add `cleanup(max_age_days)` method |
| `bot/data_fetcher.py` | **MODIFY** | Add retry decorator for rate limits (429/418) |
| `scripts/sync_research_data.sh` | **CREATE** | MacBook-side sync orchestrator |
| `run_research.py` | **MODIFY** | Add `--offline` flag |
| `bot/research/pipeline.py` | **MODIFY** | Support `offline=True` in `run_full()` |
| `scripts/research_local.sh` | **CREATE** | Convenience wrapper (sync + offline research) |

## Testing

- Unit test for `KlineCache.cleanup()` (mock filesystem, verify removal logic)
- Unit test for retry decorator (mock 429 responses, verify backoff)
- Unit test for `--offline` pipeline path (verify no API calls made)
- Integration: run `sync_research_data.sh --sync-only` against VPS (manual)

## Non-Goals

- No cron jobs or auto-scheduling
- No S3/cloud storage — SCP is sufficient
- No VPN management — user handles VPN for SSH access
- No changes to live trading data flow (only research pipeline)
