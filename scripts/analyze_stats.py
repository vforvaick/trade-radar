"""
Phase 3: Statistical Deep Dive
Phase 4: Strategy Parameter Extraction

Produces analysis_report.md, equity_curve.png, and strategy_spec.md.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
DEFAULT_LEDGER = DATA_DIR / "validated_ledger.csv"
DEFAULT_MESSAGES = DATA_DIR / "all_messages.json"
DEFAULT_REPORT = DOCS_DIR / "analysis_report.md"
DEFAULT_SPEC = DOCS_DIR / "strategy_spec.md"
DEFAULT_EQUITY_PLOT = DATA_DIR / "equity_curve.png"


def parse_duration_hours(date_signal, date_outcome) -> float | None:
    if pd.isna(date_outcome):
        return None
    d1 = pd.to_datetime(date_signal)
    d2 = pd.to_datetime(date_outcome)
    return (d2 - d1).total_seconds() / 3600


def simulate_equity_curve(trades_df: pd.DataFrame, risk_pct: float = 3.0):
    """Simulate equity curve with fixed risk per trade and 70/20/10 TP exits."""
    equity = 1000.0
    curve = [(trades_df["date_signal"].min(), equity)]
    max_equity = equity
    max_dd = 0.0

    for _, row in trades_df.sort_values("date_signal").iterrows():
        risk_amount = equity * (risk_pct / 100)
        if row["is_loss"]:
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

        curve.append((row["date_signal"], equity))
        max_equity = max(max_equity, equity)
        max_dd = max(max_dd, (max_equity - equity) / max_equity * 100)

    return curve, max_dd, equity


def _count_mentions(messages: list[dict]) -> tuple[dict[str, int], list[int], list[float], list[float]]:
    signal_msgs = [m for m in messages if "SIGNAL DETECTED" in m.get("text", "")]
    insights = [m["text"] for m in signal_msgs if "AI Insight" in m.get("text", "")]

    indicator_mentions = {
        "EMA": 0,
        "MACD": 0,
        "RSI": 0,
        "Bollinger Band": 0,
        "Volume": 0,
        "Buy/Sell Pressure": 0,
        "ROC": 0,
        "Candle": 0,
        "Divergence": 0,
    }
    rsi_values = []
    bb_positions = []
    pressure_values = []

    for text in insights:
        if "ema" in text.lower():
            indicator_mentions["EMA"] += 1
        if "MACD" in text:
            indicator_mentions["MACD"] += 1
        if "RSI" in text:
            indicator_mentions["RSI"] += 1
            rsi_values.extend(int(v) for v in re.findall(r"RSI[:\s<>]*(\d+)", text))
        if "bb" in text.lower() or "bollinger" in text.lower():
            indicator_mentions["Bollinger Band"] += 1
            bb_positions.extend(
                float(v) for v in re.findall(r"BB Position[:\s]*([\d.]+)", text)
            )
        if "volume" in text.lower():
            indicator_mentions["Volume"] += 1
        if "pressure" in text.lower() or "tekanan" in text.lower():
            indicator_mentions["Buy/Sell Pressure"] += 1
            pressure_values.extend(float(v) for v in re.findall(r"(\d+\.?\d*)%\)", text))
        if "ROC" in text:
            indicator_mentions["ROC"] += 1
        if "candle" in text.lower():
            indicator_mentions["Candle"] += 1
        if "divergence" in text.lower():
            indicator_mentions["Divergence"] += 1

    return indicator_mentions, rsi_values, bb_positions, pressure_values


def _prepare_resolved(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date_signal"] = pd.to_datetime(df["date_signal"])
    resolved = df[df["status"] != "OPEN"].copy()
    resolved["is_win"] = resolved["status"].isin(["TP1", "TP2", "TP3_CLOSED", "TP3_MISSED"])
    resolved["is_loss"] = resolved["status"] == "SL_CLOSED"
    resolved["dur_tp1"] = resolved.apply(
        lambda r: parse_duration_hours(r["date_signal"], r["tp1_date"]),
        axis=1,
    )
    resolved["dur_sl"] = resolved.apply(
        lambda r: parse_duration_hours(r["date_signal"], r["sl_date"]),
        axis=1,
    )
    resolved["tp1_dist_pct"] = (
        abs(resolved["tp1_target"] - resolved["entry_price"]) / resolved["entry_price"] * 100
    )
    resolved["tp2_dist_pct"] = (
        abs(resolved["tp2_target"] - resolved["entry_price"]) / resolved["entry_price"] * 100
    )
    resolved["tp3_dist_pct"] = (
        abs(resolved["tp3_target"] - resolved["entry_price"]) / resolved["entry_price"] * 100
    )
    resolved["sl_dist_pct"] = (
        abs(resolved["sl_target"] - resolved["entry_price"]) / resolved["entry_price"] * 100
    )
    return resolved


def _format_pct(value: float) -> str:
    return f"{value:+.1f}%"


def _render_report(df: pd.DataFrame, resolved: pd.DataFrame) -> tuple[str, float, float]:
    wins = int(resolved["is_win"].sum())
    losses = int(resolved["is_loss"].sum())
    win_rate = wins / len(resolved) * 100 if len(resolved) else 0.0
    avg_tp1_profit = resolved.loc[resolved["tp1_hit"], "tp1_profit_pct"].mean()
    avg_sl_loss = resolved.loc[resolved["sl_hit"], "sl_loss_pct"].mean()
    gross_profit = resolved.loc[resolved["tp1_hit"], "tp1_profit_pct"].sum()
    gross_loss = resolved.loc[resolved["sl_hit"], "sl_loss_pct"].sum()
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    curve_all, dd_all, final_all = simulate_equity_curve(resolved)

    max_consec_loss = 0
    curr_consec = 0
    consec_losses_list = []
    for _, row in resolved.sort_values("date_signal").iterrows():
        if row["is_loss"]:
            curr_consec += 1
            max_consec_loss = max(max_consec_loss, curr_consec)
        else:
            if curr_consec > 0:
                consec_losses_list.append(curr_consec)
            curr_consec = 0
    if curr_consec > 0:
        consec_losses_list.append(curr_consec)

    validated_entries = int(df["entry_valid"].fillna(False).astype(bool).sum())
    validation_note = ""
    if validated_entries == 0 and len(df) > 0:
        validation_note = (
            "\n- Validation note: local Binance Futures requests currently return HTTP 403 "
            "for all symbols, so `entry_valid` should be regenerated from an allowed egress host "
            "before using market-revalidation metrics."
        )

    lines = [
        "# 📊 Pumpradar Signal — Statistical Deep Dive",
        "",
        "> Canonical report generated from `data/validated_ledger.csv` and `data/all_messages.json`.",
        f"> Analysis of {len(resolved)} resolved trades ({len(df) - len(resolved)} still open)",
        f"> Period: {df['date_signal'].min().strftime('%Y-%m-%d')} to {df['date_signal'].max().strftime('%Y-%m-%d')}",
        "> Methodology: fixed 3% risk-per-trade simulation with 70/20/10 TP cascade and SL-at-risk accounting.",
        "",
        "## Overall Performance",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total resolved | {len(resolved)} |",
        f"| Wins (TP1+) | {wins} ({win_rate:.1f}%) |",
        f"| Losses (SL) | {losses} ({100 - win_rate:.1f}%) |",
        f"| Avg TP1 profit | +{avg_tp1_profit:.1f}% (leveraged) |",
        f"| Avg SL loss | -{avg_sl_loss:.1f}% (leveraged) |",
        f"| Profit factor | {profit_factor:.2f} |",
        "",
        "## Win Rate by Direction",
        "",
        "| Direction | Trades | Wins | Win Rate |",
        "|---|---|---|---|",
    ]

    for direction in ["LONG", "SHORT"]:
        sub = resolved[resolved["direction"] == direction]
        sub_wins = int(sub["is_win"].sum())
        sub_wr = sub_wins / len(sub) * 100 if len(sub) else 0.0
        lines.append(f"| {direction} | {len(sub)} | {sub_wins} | {sub_wr:.1f}% |")

    lines.extend([
        "",
        "## Equity Curve Simulation",
        "",
        "### Results (starting $1,000, 3% risk per trade)",
        "",
        "| Strategy | Final Equity | Return | Max Drawdown | Trades |",
        "|---|---|---|---|---|",
        f"| All signals | ${final_all:,.0f} | {_format_pct((final_all / 1000 - 1) * 100)} | {dd_all:.1f}% | {len(resolved)} |",
        "",
        "## Drawdown & Consecutive Loss Analysis",
        "",
        f"- Max consecutive losses: **{max_consec_loss}**",
        f"- Consecutive loss streaks: {Counter(consec_losses_list)}",
        "",
        "## Market Validation Summary",
        "",
        f"- Entries validated against Binance: **{validated_entries}/{len(df)}**",
        f"- Missed TP3s (price reached but not announced): **{int(df['tp3_missed'].fillna(False).astype(bool).sum())}**{validation_note}",
    ])

    return "\n".join(lines), dd_all, final_all


def _render_spec(resolved: pd.DataFrame, messages: list[dict]) -> str:
    indicator_mentions, rsi_values, bb_positions, pressure_values = _count_mentions(messages)
    signal_msgs = [m for m in messages if "SIGNAL DETECTED" in m.get("text", "")]
    insights_total = max(1, len([m for m in signal_msgs if "AI Insight" in m.get("text", "")]))

    avg_tp1_d = resolved["tp1_dist_pct"].mean()
    avg_tp2_d = resolved["tp2_dist_pct"].mean()
    avg_tp3_d = resolved["tp3_dist_pct"].mean()
    avg_sl_d = resolved["sl_dist_pct"].mean()
    avg_dur_sl = resolved["dur_sl"].dropna().mean()

    max_consec_loss = 0
    curr_consec = 0
    for _, row in resolved.sort_values("date_signal").iterrows():
        if row["is_loss"]:
            curr_consec += 1
            max_consec_loss = max(max_consec_loss, curr_consec)
        else:
            curr_consec = 0

    lines = [
        "# 🔬 Pumpradar — Reverse-Engineered Strategy Specification",
        "",
        "> Canonical spec generated from `data/validated_ledger.csv` + `data/all_messages.json`.",
        f"> Sample period: {resolved['date_signal'].min().strftime('%Y-%m-%d')} to {resolved['date_signal'].max().strftime('%Y-%m-%d')}",
        "> Interpretation note: indicator counts and distances are observed measurements; threshold and BB-setting statements below are hypotheses inferred from sparse AI Insight text, not ground-truth constants.",
        "",
        "## TP/SL Distance Formula",
        "",
        "### Overall Distance Averages",
        "",
        f"- **TP1 distance**: {avg_tp1_d:.2f}% from entry",
        f"- **TP2 distance**: {avg_tp2_d:.2f}% from entry",
        f"- **TP3 distance**: {avg_tp3_d:.2f}% from entry",
        f"- **SL distance**: {avg_sl_d:.2f}% from entry",
        f"- **TP1/SL ratio**: {avg_tp1_d / avg_sl_d:.2f}",
        f"- **TP spacing ratio (TP2/TP1)**: {avg_tp2_d / avg_tp1_d:.2f}",
        f"- **TP spacing ratio (TP3/TP2)**: {avg_tp3_d / avg_tp2_d:.2f}",
        "",
        "## Indicator Parameters (from AI Insight NLP)",
        "",
        "### Indicator Frequency in AI Insights",
        "",
        "| Indicator | Mentions | % of Signals |",
        "|---|---|---|",
    ]

    for indicator, count in sorted(indicator_mentions.items(), key=lambda x: -x[1]):
        lines.append(f"| {indicator} | {count} | {count / insights_total * 100:.0f}% |")

    if rsi_values:
        lines.extend([
            "",
            "### RSI Values Mentioned",
            f"- Values found: {rsi_values}",
            "- Hypothesis from observed mentions: **RSI <50 for SHORT, >50 for LONG**",
        ])

    if bb_positions:
        lines.extend([
            "",
            "### Bollinger Band Positions",
            f"- BB Position values: {bb_positions}",
            f"- BB Position range: {min(bb_positions):.2f} – {max(bb_positions):.2f}",
            "- Hypothesis from observed BB references: **(20, 2)** standard",
        ])

    if pressure_values:
        lines.extend([
            "",
            "### Buy/Sell Pressure Thresholds",
            f"- Values: {pressure_values}",
        ])

    lines.extend([
        "",
        "## 🎯 Complete Strategy Specification",
        "",
        "### Entry Conditions",
        "1. **Multi-indicator confluence** scoring system:",
        "   - EMA trend alignment (9/21/50)",
        "   - MACD signal confirmation",
        "   - RSI position (>50 for LONG, <50 for SHORT)",
        "   - RSI divergence detection",
        "   - Bollinger Band position (20, 2)",
        "   - Volume spike detection",
        "   - Buy/Sell pressure ratio",
        "   - Last candle direction",
        "2. **BTC trend filter** with confidence down-weighting in Uptrend",
        "3. **Confidence threshold** around 54%",
        "",
        "### Position Sizing & Leverage",
        "- Risk per trade: 2-3% of equity",
        "- 7x, 5x, and 4x leverage tiers map to confidence and R:R",
        "",
        "### Exit Management",
        "```",
        "Signal fires → Enter position 100%",
        "  ├─ TP1 hit → Close 70%, move SL to breakeven",
        "  ├─ TP2 hit → Close 20% more",
        "  └─ TP3 hit → Close final 10%",
        "```",
        "",
        "### Risk Management",
        f"- Max consecutive losses observed: **{max_consec_loss}**",
        f"- Average time to SL: **{avg_dur_sl:.1f}h**",
        "- BTC anomaly monitoring for fast market shocks",
    ])

    return "\n".join(lines)


def _write_equity_plot(curve, output_path: Path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    dates = [point[0] for point in curve]
    values = [point[1] for point in curve]
    ax.plot(dates, values, label="All Signals", color="#00d2ff", linewidth=2)
    ax.axhline(y=1000, color="white", linestyle="--", alpha=0.3, label="Starting Capital")
    ax.set_title(
        "Pumpradar Signal Equity Curve Simulation",
        color="white",
        fontsize=16,
        fontweight="bold",
    )
    ax.set_xlabel("Date", color="white", fontsize=12)
    ax.set_ylabel("Equity ($)", color="white", fontsize=12)
    ax.legend(fontsize=10, facecolor="#16213e", edgecolor="white", labelcolor="white")
    ax.tick_params(colors="white")
    ax.grid(True, alpha=0.15, color="white")
    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved {output_path}")


def write_reports(
    ledger_path: Path,
    messages_path: Path,
    report_path: Path,
    spec_path: Path,
    equity_plot_path: Path,
) -> dict[str, float]:
    df = pd.read_csv(ledger_path)
    df["date_signal"] = pd.to_datetime(df["date_signal"])
    resolved = _prepare_resolved(df)
    messages = json.loads(Path(messages_path).read_text(encoding="utf-8"))

    report_text, dd_all, final_all = _render_report(df, resolved)
    spec_text = _render_spec(resolved, messages)
    curve_all, _, _ = simulate_equity_curve(resolved)

    report_path = Path(report_path)
    spec_path = Path(spec_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    spec_path.write_text(spec_text, encoding="utf-8")
    _write_equity_plot(curve_all, Path(equity_plot_path))

    print(f"Saved {report_path}")
    print(f"Saved {spec_path}")
    print("\n=== DONE ===")
    print(f"Final equity (all signals, 3% risk): ${final_all:,.0f}")
    print(f"Max drawdown: {dd_all:.1f}%")

    return {"final_equity": final_all, "max_drawdown": dd_all}


def main(argv: list[str] | None = None) -> dict[str, float]:
    parser = argparse.ArgumentParser(
        description="Generate research reports from validated Pumpradar trade data."
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--messages", type=Path, default=DEFAULT_MESSAGES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--equity-plot", type=Path, default=DEFAULT_EQUITY_PLOT)
    args = parser.parse_args(argv)

    return write_reports(
        ledger_path=args.ledger,
        messages_path=args.messages,
        report_path=args.report,
        spec_path=args.spec,
        equity_plot_path=args.equity_plot,
    )


if __name__ == "__main__":
    main()
