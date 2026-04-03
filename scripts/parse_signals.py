"""Parse Pumpradar Telegram messages into a trade ledger CSV."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "all_messages.json"
DEFAULT_OUTPUT = DATA_DIR / "trade_ledger.csv"


def parse_number(text: str, regex_pattern: str) -> float | None:
    match = re.search(regex_pattern, text)
    return float(match.group(1).replace(",", "")) if match else None


def parse_messages(messages: list[dict]) -> pd.DataFrame:
    messages = sorted(messages, key=lambda x: str(x["date"]))
    parsed_signals = []
    active_trades = {}

    for msg in messages:
        text = msg.get("text", "")
        date = msg["date"]

        if "SIGNAL DETECTED" in text:
            direction = "LONG" if "LONG" in text else "SHORT"

            symbol_match = re.search(r"\*\*Symbol:\*\* #([A-Z0-9]+)", text)
            if not symbol_match:
                continue
            symbol = symbol_match.group(1)

            rr_match = re.search(r"Risk/Reward: ([\d.]+:\d+\.?\d*)", text)
            lev_match = re.search(r"Rec\. Leverage: \*\*(\d+)x\*\*", text)
            btc_match = re.search(r"BTC Trend: (\w+)", text)
            conf_match = re.search(r"GO Confidence: (\d+)%", text)
            insight_match = re.search(
                r"Confidence: \d+%(.*?)\(Action: GO\)",
                text,
                re.DOTALL,
            )

            trade = {
                "signal_id": msg["id"],
                "date_signal": date,
                "symbol": symbol,
                "direction": direction,
                "entry_price": parse_number(text, r"\*\*Entry:\*\* `([\d.]+)`"),
                "tp1_target": parse_number(text, r"TP1: `([\d.]+)`"),
                "tp2_target": parse_number(text, r"TP2: `([\d.]+)`"),
                "tp3_target": parse_number(text, r"TP3: `([\d.]+)`"),
                "sl_target": parse_number(text, r"\*\*Stop Loss:\*\* `([\d.]+)`"),
                "leverage": int(lev_match.group(1)) if lev_match else None,
                "risk_reward": rr_match.group(1) if rr_match else None,
                "confidence_pct": int(conf_match.group(1)) if conf_match else None,
                "btc_trend": btc_match.group(1) if btc_match else None,
                "ai_insight": insight_match.group(1).strip() if insight_match else None,
                "status": "OPEN",
                "tp1_hit": False,
                "tp2_hit": False,
                "tp3_hit": False,
                "sl_hit": False,
                "tp1_date": None,
                "tp2_date": None,
                "tp3_date": None,
                "sl_date": None,
                "tp1_profit_pct": None,
                "tp2_profit_pct": None,
                "tp3_profit_pct": None,
                "sl_loss_pct": None,
            }

            active_trades[symbol] = trade
            parsed_signals.append(trade)
            continue

        if not (
            "TP1 DONE" in text
            or "TP2 SMASHED" in text
            or "TP3 JACKPOT" in text
            or "SL HIT" in text
        ):
            continue

        symbol_match = re.search(
            r"\*\*Symbol:\*\* #\d+ (?:LONG|SHORT) ([A-Z0-9]+)",
            text,
        )
        if not symbol_match:
            symbol_match = re.search(r"\*\*Symbol:\*\* #([A-Z0-9]+)", text)
        if not symbol_match:
            continue

        symbol = symbol_match.group(1)
        if symbol not in active_trades:
            continue

        trade = active_trades[symbol]
        profit_match = re.search(r"Profit:\*\* `\+?([\d.]+)%`", text)
        loss_match = re.search(r"Loss:\*\* `-([\d.]+)%`", text)

        if "TP1 DONE" in text:
            trade["tp1_hit"] = True
            trade["tp1_date"] = date
            trade["status"] = "TP1"
            if profit_match:
                trade["tp1_profit_pct"] = float(profit_match.group(1))
        elif "TP2 SMASHED" in text:
            trade["tp2_hit"] = True
            trade["tp2_date"] = date
            trade["status"] = "TP2"
            if profit_match:
                trade["tp2_profit_pct"] = float(profit_match.group(1))
        elif "TP3 JACKPOT" in text:
            trade["tp3_hit"] = True
            trade["tp3_date"] = date
            trade["status"] = "TP3_CLOSED"
            if profit_match:
                trade["tp3_profit_pct"] = float(profit_match.group(1))
            active_trades.pop(symbol, None)
        elif "SL HIT" in text:
            trade["sl_hit"] = True
            trade["sl_date"] = date
            trade["status"] = "SL_CLOSED"
            if loss_match:
                trade["sl_loss_pct"] = float(loss_match.group(1))
            active_trades.pop(symbol, None)

    return pd.DataFrame(parsed_signals)


def write_trade_ledger(input_path: Path, output_path: Path) -> pd.DataFrame:
    messages = json.loads(Path(input_path).read_text(encoding="utf-8"))
    df = parse_messages(messages)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"Parsed {len(df)} signals into {output_path}")
    if "status" in df.columns:
        print(df["status"].value_counts())
    return df


def main(argv: list[str] | None = None) -> pd.DataFrame:
    parser = argparse.ArgumentParser(
        description="Parse Pumpradar Telegram messages into a trade ledger."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    return write_trade_ledger(args.input, args.output)


if __name__ == "__main__":
    main()
