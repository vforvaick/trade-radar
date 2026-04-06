"""
New Passports Backtest Script
==============================
Runs 90-day backtests for all 10 new passport candidates + validates
the 3 profitable v0.3 rollbacks (HiddenGem, Sniper, VolumeKing).

Usage:
    cd /path/to/crypto-signal
    python scripts/run_new_passport_backtest.py [--days 90] [--pairs 15]

Output:
    logs/new_passports_YYYYMMDD_HHMMSS.log
    Ranked table sorted by return_pct descending.
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from bot.backtester import run_backtest
from bot.data_fetcher import get_all_futures_symbols
from bot import config as _cfg

PASSPORTS_ROOT = os.path.join(REPO_ROOT, "passports")


def _find_passport_file(filename: str) -> str:
    """Locate a passport JSON by filename in any subdirectory of passports/."""
    for subdir in os.listdir(PASSPORTS_ROOT):
        candidate = os.path.join(PASSPORTS_ROOT, subdir, filename)
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(f"Passport file not found: {filename} under {PASSPORTS_ROOT}")

# Passports to test — new candidates + v0.3 rollbacks for reference
NEW_PASSPORT_FILES = [
    "pure_trend.json",
    "trend_momentum.json",
    "bb_mean_rev.json",
    "breakout_vol.json",
    "rsi_contrarian.json",
    "minimal_edge.json",
    "pressure_reader.json",
    "trend_confirm.json",
    "macd_divergence.json",
    "balanced_selective.json",
]

REFERENCE_PASSPORT_FILES = [
    "hidden_gem.json",    # v0.3 rollback, expected +25.9%
    "sniper.json",        # v0.3 rollback, expected +26.0%
    "volume_king.json",   # v0.3 rollback, expected +9.1%
    "og_original.json",   # baseline, expected -13.1%
]


def load_passport_cfg_override(filepath: str) -> dict:
    """Load config_overrides from a passport JSON, expanding nested INDICATOR_WEIGHTS."""
    with open(filepath) as f:
        passport = json.load(f)
    overrides = passport.get("config_overrides", {})
    # Flatten — backtester expects flat key:value pairs
    flat = {}
    for k, v in overrides.items():
        if k == "INDICATOR_WEIGHTS":
            flat["INDICATOR_WEIGHTS"] = v
        elif k not in ("USE_ATR_EXITS", "USE_TRAILING_STOP",
                       "MAX_OPEN_POSITIONS_PER_PASSPORT", "MAX_OPEN_POSITIONS_PER_SYMBOL"):
            flat[k] = v
    # Also pass boolean flags
    flat["USE_ATR_EXITS"] = overrides.get("USE_ATR_EXITS", False)
    flat["USE_TRAILING_STOP"] = overrides.get("USE_TRAILING_STOP", False)
    flat["CONFIDENCE_THRESHOLD"] = overrides.get(
        "CONFIDENCE_THRESHOLD", _cfg.CONFIDENCE_THRESHOLD)
    return flat


def run_all(days: int, pairs: int, symbols: list = None) -> list[dict]:
    """Run backtests for all passports and return ranked results."""
    os.makedirs(os.path.join(REPO_ROOT, "logs"), exist_ok=True)

    # Fetch top pairs once or use provided symbols
    if symbols:
        print(f"Using {len(symbols)} provided symbols...", flush=True)
    else:
        print(f"Fetching top {pairs} pairs by volume...", flush=True)
        all_syms = get_all_futures_symbols()
        symbols = [s for s in all_syms if s.endswith("USDT")][:pairs]
    print(f"Pairs: {symbols}\n", flush=True)

    all_files = [
        (f, _find_passport_file(f), "NEW")
        for f in NEW_PASSPORT_FILES
    ] + [
        (f, _find_passport_file(f), "REF")
        for f in REFERENCE_PASSPORT_FILES
    ]

    results = []
    for filename, filepath, tag in all_files:
        with open(filepath) as fh:
            meta = json.load(fh)
        name = meta.get("name", filename)
        emoji = meta.get("emoji", "📋")
        version = meta.get("version", "?")
        enabled = meta.get("enabled", True)

        if not enabled:
            print(f"⏭️  {emoji} {name} v{version} — SKIPPED (disabled)", flush=True)
            continue

        print(f"\n{'='*60}", flush=True)
        print(f"{emoji} {name} v{version} [{tag}] ({days}d, {pairs} pairs)", flush=True)
        print(f"{'='*60}", flush=True)

        try:
            cfg_override = load_passport_cfg_override(filepath)
            result = run_backtest(symbols, "1h", days, cfg_override=cfg_override)
            result["name"] = name
            result["emoji"] = emoji
            result["version"] = version
            result["tag"] = tag
            result["filename"] = filename
            results.append(result)
            print(
                f"  Trades={result.get('trades',0):4d}  "
                f"WR={result.get('win_rate',0):.1f}%  "
                f"Return={result.get('return_pct',0):+.1f}%  "
                f"MaxDD={result.get('max_dd_pct',0):.1f}%  "
                f"PF={result.get('profit_factor',0):.2f}",
                flush=True
            )
        except Exception as e:
            print(f"  ❌ ERROR: {e}", flush=True)
            import traceback; traceback.print_exc()

    return results


def print_ranked(results: list[dict], logfile: str):
    """Print and save ranked results table."""
    ranked = sorted(results, key=lambda r: r.get("return_pct", -999), reverse=True)

    header = f"\n{'='*80}\n📊 RESULTS RANKED BY RETURN ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n{'='*80}"
    table_header = f"{'#':>3}  {'Tag':<5}  {'Emoji':<3}  {'Name':<22}  {'Ver':<5}  {'Trades':>6}  {'WR%':>6}  {'Ret%':>8}  {'MaxDD%':>7}  {'PF':>5}"
    sep = "-" * 80

    lines = [header, table_header, sep]
    for i, r in enumerate(ranked, 1):
        ret = r.get("return_pct", 0)
        ret_str = f"{ret:+.1f}%"
        profit_emoji = "🟢" if ret > 5 else "🟡" if ret > -5 else "🔴"
        line = (
            f"{i:>3}  {r['tag']:<5}  {r['emoji']:<3}  "
            f"{r['name']:<22}  v{r['version']:<4}  "
            f"{r.get('trades',0):>6}  "
            f"{r.get('win_rate',0):>5.1f}%  "
            f"{ret_str:>8}  "
            f"{r.get('max_dd_pct',0):>6.1f}%  "
            f"{r.get('profit_factor',0):>5.2f}  {profit_emoji}"
        )
        lines.append(line)

    lines.append(sep)
    profitable = [r for r in ranked if r.get("return_pct", 0) > 0]
    lines.append(f"\n✅ Profitable: {len(profitable)}/{len(ranked)}")
    if profitable:
        lines.append("🏆 Winners: " + ", ".join(f"{r['name']} ({r.get('return_pct',0):+.1f}%)" for r in profitable))

    output = "\n".join(lines)
    print(output)

    with open(logfile, "w") as f:
        f.write(output + "\n")
    print(f"\n📁 Saved to: {logfile}", flush=True)

    return ranked


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest all new passport candidates")
    parser.add_argument("--days", type=int, default=90, help="Days of history (default 90)")
    parser.add_argument("--pairs", type=int, default=15, help="Top N pairs by volume (default 15)")
    parser.add_argument("--symbols", nargs="+", default=None, help="Space-separated list of symbols (e.g., BTCUSDT ETHUSDT)")
    args = parser.parse_args()

    logfile = os.path.join(
        REPO_ROOT, "logs",
        f"new_passports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    print(f"🚀 New Passport Backtest — {args.days}d window, {args.pairs if not args.symbols else len(args.symbols)} pairs")
    print(f"📁 Log: {logfile}\n")

    results = run_all(args.days, args.pairs, symbols=args.symbols)
    ranked = print_ranked(results, logfile)
