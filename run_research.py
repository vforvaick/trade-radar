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
    parser.add_argument("--offline", action="store_true",
                        help="Skip connectivity check and prefetch; use local cache only")
    parser.add_argument("--full-4stage", action="store_true",
                        help="Run full 4-stage pipeline (S1→S2→S3→S4) instead of 2-stage")
    args = parser.parse_args()

    families = None
    if args.families:
        families = [f.strip() for f in args.families.split(",")]
    elif not args.all:
        logger.error("Specify --families or --all")
        sys.exit(1)

    if args.offline:
        from bot.research.data_cache import KlineCache
        cache = KlineCache()
        stats = cache.stats()
        if args.quality_pairs:
            symbols = QUALITY_PAIRS
        else:
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

    pipeline = ResearchPipeline(
        symbols=symbols,
        interval=args.interval,
        days=args.days,
        db_path=args.db_path,
    )

    start = time.time()
    if args.full_4stage:
        logger.info("Running full 4-stage pipeline (S1→S2→S3→S4)...")
        result = pipeline.run_full_4stage(
            families=families,
            max_per_family=args.max_per_family,
            mc_iterations=50,
            offline=args.offline,
        )
        survivors = []
        if result:
            logger.info("Stage 4 result: %d selected, portfolio Sharpe=%.2f",
                         len(result.selected_passport_ids), result.portfolio_sharpe)
    else:
        survivors = pipeline.run_full(
            families=families,
            max_per_family=args.max_per_family,
            offline=args.offline,
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
