"""Validate parsed Pumpradar entries against Binance 1m market data."""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytz
import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "trade_ledger.csv"
DEFAULT_OUTPUT = DATA_DIR / "validated_ledger.csv"


def _verify_tls() -> bool:
    raw = os.environ.get("CRYPTOPASS_BINANCE_VERIFY_TLS", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def parse_date(date_str):
    if pd.isna(date_str):
        return None
    dt = datetime.fromisoformat(date_str)
    return int(dt.timestamp() * 1000)


def format_date(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts / 1000, tz=pytz.UTC).isoformat()


def get_klines(symbol, start_ts, end_ts):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": 1500,
    }
    response = requests.get(url, params=params, timeout=30, verify=_verify_tls())
    if response.status_code != 200:
        raise Exception(f"API Error {response.status_code}: {response.text}")
    return response.json()


def validate_market_entries(df: pd.DataFrame, sleep_seconds: float = 0.1) -> pd.DataFrame:
    results = []

    print(f"Validating {len(df)} trades against Binance market data...")

    for i, row in df.iterrows():
        row = row.copy()
        symbol = row["symbol"]
        direction = row["direction"]
        sig_date = parse_date(row["date_signal"])
        start_ts = sig_date - (5 * 60 * 1000)

        close_dates = [row["tp3_date"], row["tp2_date"], row["tp1_date"], row["sl_date"]]
        close_dates = [parse_date(d) for d in close_dates if not pd.isna(d)]
        end_ts = (
            max(close_dates) + (5 * 60 * 1000)
            if close_dates
            else sig_date + (48 * 60 * 60 * 1000)
        )

        try:
            print(f"[{i + 1}/{len(df)}] Fetching {symbol}...")
            klines = get_klines(symbol, start_ts, end_ts)
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            row["entry_valid"] = False
            row["actual_signal_price"] = None
            row["entry_slippage_pct"] = np.nan
            row["tp3_missed"] = False
            row["validation_status"] = "fetch_error"
            results.append(row)
            continue

        entry_target = row["entry_price"]
        entry_valid = False
        signal_actual_price = None

        for kline in klines:
            ts = kline[0]
            open_p = float(kline[1])
            high_p = float(kline[2])
            low_p = float(kline[3])

            if ts >= sig_date and ts <= sig_date + (15 * 60 * 1000):
                if low_p <= entry_target <= high_p:
                    entry_valid = True
                    break

            if signal_actual_price is None and ts >= sig_date and ts < sig_date + 60000:
                signal_actual_price = open_p

        slippage_pct = 0.0
        if not entry_valid and signal_actual_price:
            slippage_pct = abs(signal_actual_price - entry_target) / entry_target * 100

        row["entry_valid"] = entry_valid
        row["actual_signal_price"] = signal_actual_price
        row["entry_slippage_pct"] = slippage_pct
        row["validation_status"] = "validated" if entry_valid else "entry_not_reached"

        tp3_missed = False
        tp3_target = row["tp3_target"]
        if not pd.isna(tp3_target) and row["status"] in ["TP1", "TP2"]:
            for kline in klines:
                ts = kline[0]
                high_p = float(kline[2])
                low_p = float(kline[3])
                if ts > sig_date and (
                    (direction == "LONG" and high_p >= tp3_target)
                    or (direction == "SHORT" and low_p <= tp3_target)
                ):
                    tp3_missed = True
                    row["actual_tp3_hit_time"] = format_date(ts)
                    row["status"] = "TP3_MISSED"
                    break

        row["tp3_missed"] = tp3_missed
        results.append(row)
        time.sleep(sleep_seconds)

    return pd.DataFrame(results)


def write_validated_ledger(
    input_path: Path,
    output_path: Path,
    sleep_seconds: float = 0.1,
) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    val_df = validate_market_entries(df, sleep_seconds=sleep_seconds)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    val_df.to_csv(output_path, index=False)

    print("\nValidation Complete!")
    print("Entry Validity Summary:")
    print(val_df["entry_valid"].value_counts())
    avg_slippage = val_df[~val_df["entry_valid"]]["entry_slippage_pct"].mean()
    print("\nAverage slippage on invalid entries:", avg_slippage, "%")
    print("\nMissed TP3s detected:", val_df["tp3_missed"].sum())

    return val_df


def main(argv: list[str] | None = None) -> pd.DataFrame:
    parser = argparse.ArgumentParser(
        description="Validate parsed Pumpradar trades against Binance 1m market data."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    args = parser.parse_args(argv)

    return write_validated_ledger(
        input_path=args.input,
        output_path=args.output,
        sleep_seconds=args.sleep_seconds,
    )


if __name__ == "__main__":
    main()
