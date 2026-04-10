"""
CTP (COUNTER_TREND_PENALTY) comparison backtest.

Runs 3 passports under CTP=0.50 vs CTP=0.75 to measure the impact of the
penalty change on return, drawdown, win-rate, profit-factor, and L/S ratio.

Usage:
    uv run python scripts/backtest_ctp_compare.py [--days N] [--pairs N]
    uv run python scripts/backtest_ctp_compare.py --symbols BTCUSDT ETHUSDT ...
"""
import argparse
import copy
import glob as _glob
import json
import os
import sys
import time

import pandas as pd

# Ensure repo root is on path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from bot import config
from bot.backtester import backtest_pair, _precompute_btc_regimes, _summarize
from bot.data_fetcher import get_all_futures_symbols, fetch_klines_range

PASSPORT_FILES = {
    "BreakoutVol":    "passports/cryptopass-research/breakout_vol.json",
    "BBMeanRev":      "passports/cryptopass-research/bb_mean_rev.json",
    "PressureReader": "passports/cryptopass-research/pressure_reader.json",
}

CTP_VALUES = [0.50, 0.65, 0.75]

CACHE_DIR = os.path.join(REPO_ROOT, "bot", "..", ".cache")
CACHE_TTL = 3600  # seconds


def _load_from_cache(symbol: str, interval: str = "1h") -> pd.DataFrame | None:
    """Find the most recent cached parquet files for a symbol and merge them.

    Falls back to None if no valid (< 1h old) cache entries exist.
    This bypasses the exact-key matching of fetch_klines() to allow cache reuse
    even when end_ms drifts slightly between runs.
    """
    pattern = os.path.join(CACHE_DIR, f"{symbol}_{interval}_*.parquet")
    candidates = _glob.glob(pattern)
    if not candidates:
        return None

    now = time.time()
    valid = [
        f for f in candidates
        if (now - os.path.getmtime(f)) < CACHE_TTL
    ]
    if not valid:
        return None

    dfs = []
    for f in sorted(valid):
        try:
            dfs.append(pd.read_parquet(f))
        except Exception:
            pass
    if not dfs:
        return None

    combined = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    return combined if len(combined) >= 100 else None


def load_passport(name: str) -> dict:
    path = os.path.join(REPO_ROOT, PASSPORT_FILES[name])
    with open(path) as f:
        return json.load(f)


def apply_config(overrides: dict) -> dict:
    """Apply overrides to bot.config, return snapshot of originals."""
    snapshot = {}
    for k, v in overrides.items():
        snapshot[k] = copy.deepcopy(getattr(config, k, None))
        setattr(config, k, copy.deepcopy(v))
    return snapshot


def restore_config(snapshot: dict):
    for k, v in snapshot.items():
        setattr(config, k, v)


def run_for_passport(name: str, meta: dict, ctp: float, klines_cache: dict,
                     btc_df, btc_regime_map: dict) -> dict:
    """Run backtest for one passport with a specific CTP value.

    Uses pre-fetched klines_cache {symbol: DataFrame} to avoid duplicate
    network calls across CTP runs.
    """
    passport_overrides = copy.deepcopy(meta.get("config_overrides", {}))

    # If passport already hard-codes COUNTER_TREND_PENALTY, respect it (no injection).
    # Otherwise inject the test CTP value.
    passport_has_ctp = "COUNTER_TREND_PENALTY" in passport_overrides
    if not passport_has_ctp:
        passport_overrides["COUNTER_TREND_PENALTY"] = {
            "TREND_UP": ctp,
            "TREND_DOWN": ctp,
            "HIGH_VOL_CHOP": 1.0,
            "LOW_VOL_COMPRESSION": 1.0,
        }

    # Apply passport config overrides
    snap = apply_config(passport_overrides)
    try:
        all_trades = []
        sym_summaries = []
        for sym, klines in klines_cache.items():
            try:
                trades = backtest_pair(sym, klines, btc_df, btc_regime_map=btc_regime_map)
                all_trades.extend(trades)
                sym_summaries.append(_summarize(trades))
            except Exception as e:
                print(f"    Error {sym}: {e}", flush=True)

        summary = _summarize(all_trades)
        active = [s for s in sym_summaries if s["trades"] > 0]
        if active:
            summary["return_pct"] = sum(s["return_pct"] for s in active) / len(active)
            summary["max_dd"] = sum(s["max_dd"] for s in active) / len(active)

        long_c = sum(1 for t in all_trades if t.get("direction") == "LONG")
        short_c = sum(1 for t in all_trades if t.get("direction") == "SHORT")
        summary["long_count"] = long_c
        summary["short_count"] = short_c
        summary["passport_has_ctp"] = passport_has_ctp
        return summary
    finally:
        restore_config(snap)


def fmt_row(name: str, ctp: float, r: dict, note: str = "") -> str:
    ret = f"{r['return_pct']:+.1f}%"
    dd = f"-{r['max_dd']:.1f}%"
    wr = f"{r['win_rate']:.0f}%"
    pf = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float('inf') else "∞"
    tc = r['trades']
    ls = f"{r['long_count']}/{r['short_count']}"
    suffix = f"  ← {note}" if note else ""
    return (
        f"{name:<18} | {ctp:.2f} | {ret:>7} | {dd:>7} | {wr:>4} | {pf:>5} | "
        f"{tc:>6} | {ls:<10}{suffix}"
    )


# Well-known high-volume USDT perpetual futures — used when Binance API is unreachable
FALLBACK_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]


def main():
    parser = argparse.ArgumentParser(description="CTP comparison backtest")
    parser.add_argument("--days", type=int, default=90, help="Backtest window (days)")
    parser.add_argument("--pairs", type=int, default=10, help="Top N pairs by volume")
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help="Explicit symbols to use (skips Binance 24hr ticker call)",
    )
    parser.add_argument(
        "--end-ms", type=int, default=None,
        help="Fix end timestamp in ms (enables cache reuse across runs). "
             "If not set, uses current time.",
    )
    args = parser.parse_args()

    if args.symbols:
        symbols = args.symbols
        print(f"\nUsing provided symbols: {symbols}\n", flush=True)
    else:
        print(f"\nFetching top {args.pairs} USDT futures pairs by volume...", flush=True)
        try:
            all_syms = get_all_futures_symbols()
            symbols = [s for s in all_syms if s.endswith("USDT")][:args.pairs]
            print(f"Pairs: {symbols}\n", flush=True)
        except Exception as e:
            print(f"  ⚠ Binance API unavailable ({e})", flush=True)
            symbols = FALLBACK_SYMBOLS[:args.pairs]
            print(f"  Using fallback pairs: {symbols}\n", flush=True)

    print("Fetching BTC data...", flush=True)
    end_ms = args.end_ms if args.end_ms else int(time.time() * 1000)
    start_ms = end_ms - args.days * 24 * 3600 * 1000

    btc_df = _load_from_cache("BTCUSDT")
    if btc_df is not None:
        print(f"  ✓ BTCUSDT: {len(btc_df)} candles (from disk cache)", flush=True)
    else:
        btc_df = fetch_klines_range("BTCUSDT", "1h", start_ms, end_ms)
    print("Pre-computing BTC regime series...", flush=True)
    btc_regime_map = _precompute_btc_regimes(btc_df)

    # Pre-fetch all klines once — reuse across all passport/CTP combinations
    print(f"\nPre-fetching {len(symbols)} pair klines (shared across all runs)...", flush=True)
    klines_cache = {}
    for sym in symbols:
        # Try disk cache first (avoids redundant Binance calls if network is flaky)
        cached_df = _load_from_cache(sym)
        if cached_df is not None:
            klines_cache[sym] = cached_df
            print(f"  ✓ {sym}: {len(cached_df)} candles (from disk cache)", flush=True)
            continue
        try:
            df = fetch_klines_range(sym, "1h", start_ms, end_ms)
            if len(df) < 100:
                print(f"  Skipping {sym}: only {len(df)} candles", flush=True)
                continue
            klines_cache[sym] = df
            print(f"  ✓ {sym}: {len(df)} candles", flush=True)
        except Exception as e:
            print(f"  ✗ {sym}: {e}", flush=True)
    print(f"Cached {len(klines_cache)}/{len(symbols)} pairs successfully.\n", flush=True)

    results = []  # list of (name, ctp, summary)

    for name in PASSPORT_FILES:
        meta = load_passport(name)
        if not meta.get("enabled", True):
            print(f"⏭️  {name} disabled — skipping", flush=True)
            continue

        for ctp in CTP_VALUES:
            print(f"\n{'='*60}", flush=True)
            print(f"Running {name} | CTP={ctp:.2f} | {args.days}d | {len(klines_cache)} pairs", flush=True)
            summary = run_for_passport(name, meta, ctp, klines_cache, btc_df, btc_regime_map)
            results.append((name, ctp, summary))
            print(
                f"  → trades={summary['trades']} return={summary['return_pct']:+.1f}% "
                f"WR={summary['win_rate']:.0f}% PF={summary['profit_factor']:.2f} "
                f"L/S={summary['long_count']}/{summary['short_count']}",
                flush=True,
            )

    # Build table
    header = (
        f"\n{'='*90}\n"
        f"CTP COMPARISON: {args.days}-day backtest, {args.pairs} quality pairs\n"
        f"{'='*90}\n"
        f"{'Passport':<18} | {'CTP':>4} | {'Return':>7} | {'MaxDD':>7} | {'WR%':>4} | "
        f"{'PF':>5} | {'Trades':>6} | {'L/S':<10}\n"
        f"{'-'*90}"
    )

    rows = []
    for name, ctp, r in results:
        note = "no change — passport overrides CTP" if r.get("passport_has_ctp") else ""
        rows.append(fmt_row(name, ctp, r, note))

    table = header + "\n" + "\n".join(rows) + "\n" + "=" * 90

    print(table)

    # Save to log file
    log_path = os.path.join(REPO_ROOT, "logs", "ctp_comparison.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        f.write(table + "\n")
    print(f"\nResults saved to {log_path}")


if __name__ == "__main__":
    main()
