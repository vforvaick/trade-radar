"""Corrected equity simulation using proper R:R-based position sizing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "validated_ledger.csv"
DEFAULT_OUTPUT = DATA_DIR / "equity_summary.json"


def simulate(trades: pd.DataFrame, risk_pct: float = 3.0):
    equity = 1000.0
    peak = equity
    max_dd = 0.0

    for _, row in trades.iterrows():
        risk_amount = equity * (risk_pct / 100)
        if row["status"] == "SL_CLOSED":
            equity -= risk_amount
        elif row["tp1_hit"]:
            entry = row["entry_price"]
            sl = row["sl_target"]
            tp1 = row["tp1_target"]
            tp2 = row["tp2_target"]
            tp3 = row["tp3_target"]
            if pd.isna(sl) or pd.isna(entry) or pd.isna(tp1):
                continue
            sl_d = abs(sl - entry) / entry
            tp1_d = abs(tp1 - entry) / entry
            gain = risk_amount * (tp1_d / sl_d) * 0.70
            if row["tp2_hit"] and not pd.isna(tp2):
                tp2_d = abs(tp2 - entry) / entry
                gain += risk_amount * (tp2_d / sl_d) * 0.20
            if row["tp3_hit"] and not pd.isna(tp3):
                tp3_d = abs(tp3 - entry) / entry
                gain += risk_amount * (tp3_d / sl_d) * 0.10
            equity += gain

        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    return equity, max_dd


def summarize_equity(
    input_path: Path,
    output_path: Path | None = DEFAULT_OUTPUT,
    risk_pct: float = 3.0,
) -> dict[str, dict[str, float | int]]:
    df = pd.read_csv(input_path)
    resolved = df[df["status"] != "OPEN"].copy().sort_values("date_signal")

    filters = {
        "All signals": resolved,
        "SHORT only": resolved[resolved["direction"] == "SHORT"],
        "4x lev only": resolved[resolved["leverage"] == 4],
        "Skip Wed+Fri": resolved[
            ~resolved["date_signal"].apply(lambda d: pd.to_datetime(d).day_name()).isin(
                ["Wednesday", "Friday"]
            )
        ],
    }

    summary = {}
    for name, sub in filters.items():
        if len(sub) > 0:
            eq, dd = simulate(sub, risk_pct=risk_pct)
            summary[name] = {
                "final_equity": eq,
                "return_pct": (eq / 1000 - 1) * 100,
                "max_drawdown_pct": dd,
                "trades": len(sub),
            }
            print(
                f"{name}: ${eq:,.0f} ({(eq / 1000 - 1) * 100:+.1f}%, "
                f"DD: {dd:.1f}%, trades: {len(sub)})"
            )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Saved {output_path}")

    return summary


def main(argv: list[str] | None = None) -> dict[str, dict[str, float | int]]:
    parser = argparse.ArgumentParser(description="Simulate Pumpradar trade equity curves.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--risk-pct", type=float, default=3.0)
    args = parser.parse_args(argv)

    return summarize_equity(
        input_path=args.input,
        output_path=args.output,
        risk_pct=args.risk_pct,
    )


if __name__ == "__main__":
    main()
