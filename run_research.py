#!/usr/bin/env python3
"""Strategy Research Engine CLI.

Usage:
    python run_research.py --families ema_crossover,rsi_momentum --max-per-family 10
    python run_research.py --all --pairs 10
    python run_research.py --all --max-per-family 5 --days 240
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from bot.data_fetcher import get_all_futures_symbols
from bot.research.pipeline import ResearchPipeline

# Tier-1 futures pairs for reliable, reproducible backtests.
# Use with --quality-pairs to avoid meme coin results.
QUALITY_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"logs/research_{int(time.time())}.log"),
    ],
)
logger = logging.getLogger("research")


def main():
    parser = argparse.ArgumentParser(description="Strategy Research Engine")
    parser.add_argument("--families", type=str, default=None,
                        help="Comma-separated family names (default: all)")
    parser.add_argument("--all", action="store_true",
                        help="Run all families")
    parser.add_argument("--max-per-family", type=int, default=None,
                        help="Max passports per family (default: no limit)")
    parser.add_argument("--pairs", type=int, default=15,
                        help="Number of trading pairs (default: 15)")
    parser.add_argument("--quality-pairs", action="store_true",
                        help="Use hardcoded tier-1 pairs instead of top-volume Binance scan")
    parser.add_argument("--interval", type=str, default="1h",
                        help="Timeframe (default: 1h)")
    parser.add_argument("--days", type=int, default=270,
                        help="History days (default: 270)")
    parser.add_argument("--db-path", type=str, default="research_experiments.db",
                        help="Experiment database path")
    args = parser.parse_args()

    families = None
    if args.families:
        families = [f.strip() for f in args.families.split(",")]
    elif not args.all:
        logger.error("Specify --families or --all")
        sys.exit(1)

    if args.quality_pairs:
        symbols = QUALITY_PAIRS
        logger.info("Using quality pairs (%d): %s", len(symbols), symbols)
    else:
        logger.info("Fetching top %d symbols by volume...", args.pairs)
        symbols = get_all_futures_symbols()[:args.pairs]
    logger.info("Trading pairs: %s", symbols)

    pipeline = ResearchPipeline(
        symbols=symbols,
        interval=args.interval,
        days=args.days,
        db_path=args.db_path,
    )

    start = time.time()
    survivors = pipeline.run_full(
        families=families,
        max_per_family=args.max_per_family,
    )
    elapsed = time.time() - start

    logger.info("=" * 60)
    logger.info("RESEARCH COMPLETE in %.1f minutes", elapsed / 60)
    logger.info("=" * 60)
    logger.info("Survivors (%d):", len(survivors))
    for s in survivors:
        logger.info("  %s [%s] — %s", s.slug, s.family, s.param_summary)

    if not survivors:
        logger.warning("No survivors! Consider relaxing thresholds or adding more families.")

    pipeline.tracker.close()


if __name__ == "__main__":
    main()
