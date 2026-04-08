"""
ATR Trailing Stop Comparison Script
Runs backtest on quality pairs with 3 configurations and prints comparison.

Usage:
    uv run python scripts/backtest_atr_comparison.py --passport macd_divergence --days 90
    uv run python scripts/backtest_atr_comparison.py --passport pressure_reader --days 90
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot import config
from bot.backtester import run_backtest

QUALITY_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]


def run_scenario(passport_name: str, days: int, use_trailing: bool, multiplier: float) -> dict:
    """Run backtest with specific trailing stop config."""
    # Find passport file
    passport_dirs = [
        Path("passports/cryptopass-research"),
        Path("passports/pumpradar"),
    ]
    passport_cfg = None
    for d in passport_dirs:
        for f in d.glob("*.json"):
            data = json.loads(f.read_text())
            if data.get("name", "").lower().replace(" ", "_") == passport_name.lower().replace(" ", "_"):
                passport_cfg = data
                break

    if passport_cfg is None:
        raise FileNotFoundError(f"Passport not found: {passport_name}")

    overrides = passport_cfg.get("config_overrides", {}).copy()
    overrides["USE_TRAILING_STOP"] = use_trailing
    overrides["ATR_TRAIL_MULTIPLIER"] = multiplier

    result = run_backtest(
        symbols=QUALITY_PAIRS,
        days=days,
        cfg_override=overrides,
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="ATR trailing stop A/B comparison")
    parser.add_argument("--passport", required=True, help="Passport name (e.g. macd_divergence)")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"ATR Trailing Stop Comparison: {args.passport} ({args.days}d)")
    print(f"{'='*60}\n")

    scenarios = [
        ("No trailing stop", False, 2.0),
        ("ATR trail 2.0x",  True,  2.0),
        ("ATR trail 2.5x",  True,  2.5),
    ]

    for label, use_trailing, mult in scenarios:
        try:
            r = run_scenario(args.passport, args.days, use_trailing, mult)
            trades = r.get("trades", 0)
            ret = r.get("return_pct", 0)
            max_dd = r.get("max_dd", 0)
            pf = r.get("profit_factor", 0)
            wr = r.get("win_rate", 0)
            print(f"{label:25s}  trades={trades:4d}  return={ret:+7.2f}%  "
                  f"max_dd={max_dd:6.2f}%  PF={pf:.2f}  WR={wr:.1f}%")
        except Exception as e:
            print(f"{label:25s}  ERROR: {e}")

    print(f"\n{'='*60}")
    print("VERDICT: only enable ATR trailing if 'ATR trail' row shows return >= 'No trailing'")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
