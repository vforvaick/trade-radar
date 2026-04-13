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
