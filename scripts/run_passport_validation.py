"""
Passport Validation Script — v0.1 vs v0.2 Before/After Comparison
====================================================================
Runs 180-day backtests for all passports at both their v0.1 (baseline)
and v0.2 (revised) configs, then prints a side-by-side comparison table.

Usage:
    cd /path/to/crypto-signal
    python scripts/run_passport_validation.py

Output:
    logs/passport_validation_YYYYMMDD_HHMMSS.log
"""

import os
import sys
import json
import time
from datetime import datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from bot.backtester import run_backtest
from bot.data_fetcher import get_all_futures_symbols

# ─────────────────────────────────────────────────────────────
# Passport definitions: v0.1 (before) and v0.2 (after revision)
# ─────────────────────────────────────────────────────────────

PASSPORTS = [
    {
        "name": "OG",
        "emoji": "🏆",
        "v0.1": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 1.5,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
                "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 1.0,
                "pressure": 1.0, "candle_direction": 1.0,
            },
        },
        "v0.2": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
                "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 1.0,
                "pressure": 1.0, "candle_direction": 1.0,
            },
        },
    },
    {
        "name": "HiddenGem",
        "emoji": "💎",
        "v0.1": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            },
        },
        "v0.2": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "CONFIDENCE_THRESHOLD": 58,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.5, "candle_direction": 0.0,
            },
        },
    },
    {
        "name": "Momentum",
        "emoji": "🚀",
        "v0.1": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
                "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 1.0, "candle_direction": 1.0,
            },
        },
        "v0.2": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "CONFIDENCE_THRESHOLD": 60,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 30,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 2.0, "macd_signal": 1.0, "rsi_position": 1.0,
                "rsi_divergence": 0.5, "bb_position": 1.0, "volume_spike": 1.5,
                "pressure": 0.5, "candle_direction": 0.5,
            },
        },
    },
    {
        "name": "Dynamic",
        "emoji": "🎯",
        "v0.1": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "USE_ATR_EXITS": True, "USE_TRAILING_STOP": True,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 1.0, "rsi_position": 1.0,
                "rsi_divergence": 1.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 1.0, "candle_direction": 1.0,
            },
        },
        "v0.2": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "CONFIDENCE_THRESHOLD": 60,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 30,
            "USE_ATR_EXITS": True, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 2.0, "macd_signal": 1.0, "rsi_position": 1.0,
                "rsi_divergence": 0.5, "bb_position": 1.0, "volume_spike": 1.5,
                "pressure": 0.5, "candle_direction": 0.5,
            },
        },
    },
    {
        "name": "Sniper",
        "emoji": "🔫",
        "v0.1": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "CONFIDENCE_THRESHOLD": 70,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            },
        },
        "v0.2": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "CONFIDENCE_THRESHOLD": 65,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 1.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            },
        },
    },
    {
        "name": "VolumeKing",
        "emoji": "📢",
        "v0.1": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.5,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 3.0,
                "pressure": 0.0, "candle_direction": 1.0,
            },
        },
        "v0.2": {
            "EMA_FAST": 9, "EMA_MID": 21, "EMA_SLOW": 50,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "CONFIDENCE_THRESHOLD": 58,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.5, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 2.5,
                "pressure": 0.5, "candle_direction": 1.0,
            },
        },
    },
]

# Reversal is skipped (disabled/quarantined — no entry signals expected)


def _pct(val, bold=False):
    sign = "+" if val >= 0 else ""
    s = f"{sign}{val:.1f}%"
    return s


def _delta(a, b):
    """Show delta b-a with arrow."""
    d = b - a
    arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
    sign = "+" if d >= 0 else ""
    return f"{arrow}{sign}{d:.1f}"


def run():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(REPO_ROOT, "logs", f"passport_validation_{timestamp}.log")
    os.makedirs(os.path.join(REPO_ROOT, "logs"), exist_ok=True)

    print(f"📊 Passport Validation — v0.1 vs v0.2 (180-day backtest)")
    print(f"   Log: {log_path}\n")

    symbols = get_all_futures_symbols()[:10]
    days = 180
    interval = "1h"

    results = {}  # passport_name -> {"v0.1": summary, "v0.2": summary}

    for passport in PASSPORTS:
        name = passport["name"]
        emoji = passport["emoji"]
        results[name] = {}

        for version in ("v0.1", "v0.2"):
            cfg = passport[version]
            print(f"\n[{emoji} {name} {version}] Running 180-day backtest...")
            t0 = time.time()
            summary = run_backtest(symbols, interval, days, cfg_override=cfg)
            elapsed = time.time() - t0
            summary["version"] = version
            summary["elapsed_s"] = round(elapsed)
            results[name][version] = summary
            print(
                f"  → {summary['trades']} trades | "
                f"WR: {summary['win_rate']:.1f}% | "
                f"Return: {summary['return_pct']:+.1f}% | "
                f"MaxDD: {summary.get('max_dd', 0):.1f}% "
                f"({elapsed:.0f}s)"
            )

    # ── Print comparison table ──────────────────────────────
    separator = "─" * 90
    header = (
        f"\n{'Passport':<14} {'Ver':<5} {'Return':>8} {'Δ':>7} "
        f"{'WR':>6} {'Δ':>5} {'Trades':>7} {'MaxDD':>7} {'Δ':>7}"
    )

    lines = [
        "",
        "=" * 90,
        "PASSPORT VALIDATION — v0.1 vs v0.2 COMPARISON",
        "=" * 90,
        header,
        separator,
    ]

    for passport in PASSPORTS:
        name = passport["name"]
        emoji = passport["emoji"]
        v1 = results[name].get("v0.1", {})
        v2 = results[name].get("v0.2", {})

        if not v1 or not v2:
            continue

        r1, r2 = v1["return_pct"], v2["return_pct"]
        w1, w2 = v1["win_rate"], v2["win_rate"]
        t1, t2 = v1["trades"], v2["trades"]
        d1, d2 = v1.get("max_dd", 0), v2.get("max_dd", 0)

        verdict = "✅ BETTER" if r2 > r1 else ("⚠️  WORSE" if r2 < r1 else "→ SAME")

        lines.append(
            f"{emoji} {name:<12} v0.1  {_pct(r1):>8}        "
            f"{w1:>5.1f}%        {t1:>7}  {_pct(d1):>7}"
        )
        lines.append(
            f"{'':14} v0.2  {_pct(r2):>8} {_delta(r1,r2):>7} "
            f"{w2:>5.1f}% {_delta(w1,w2):>5} {t2:>7}  {_pct(d2):>7} {_delta(d1,d2):>7}  {verdict}"
        )
        lines.append(separator)

    lines += [
        "",
        "NOTES:",
        "  Δ = v0.2 minus v0.1. ↑ = improvement (higher return/WR, lower DD).",
        "  Reversal excluded (quarantined, no meaningful backtest).",
        f"  Backtest period: {days} days | Interval: {interval} | Symbols: {len(symbols)}",
        "",
    ]

    output = "\n".join(lines)
    print(output)

    with open(log_path, "w") as f:
        f.write(output)
        f.write("\n\nRAW RESULTS JSON:\n")
        f.write(json.dumps(results, indent=2, default=str))

    print(f"\n✅ Results saved to {log_path}")
    return results


if __name__ == "__main__":
    run()
