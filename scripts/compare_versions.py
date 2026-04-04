#!/usr/bin/env python3
"""CLI utility for inspecting passport version status.

Usage:
    python scripts/compare_versions.py
    python scripts/compare_versions.py --passport og
"""

import argparse
import json
from pathlib import Path


CONFIGS_DIR = Path(__file__).parent.parent / "pumpradar-passports" / "configs"


def fmt_backtest(entry: dict) -> str:
    bt = entry.get("backtest_180d", {})
    ret = bt.get("return_pct")
    return f"{ret:+.1f}%" if ret is not None else "pending"


def load_passports() -> list[dict]:
    passports = []
    for path in sorted(CONFIGS_DIR.glob("*.json")):
        with path.open() as f:
            data = json.load(f)
        data["_file"] = path.name
        passports.append(data)
    return passports


def print_summary(passports: list[dict]) -> None:
    print("Passport Version Status")
    print("═" * 51)
    for p in passports:
        emoji = p.get("emoji", "")
        name = p.get("name", p["_file"]).replace("Pumpradar ", "")
        version = p.get("version", "?")
        changelog = p.get("changelog", [])
        current_entry = next((c for c in changelog if c["version"] == version), None)
        bt_status = fmt_backtest(current_entry) if current_entry else "pending"
        label = f"{emoji} {name}"
        print(f"{label:<24} v{version}  [backtest: {bt_status}]")


def print_passport_detail(passports: list[dict], name_filter: str) -> None:
    name_lower = name_filter.lower()
    matches = [
        p for p in passports
        if name_lower in p.get("name", "").lower() or name_lower in p["_file"].lower()
    ]
    if not matches:
        print(f"No passport matching '{name_filter}' found.")
        return
    for p in matches:
        emoji = p.get("emoji", "")
        full_name = p.get("name", p["_file"])
        print(f"\n{emoji} {full_name}  (v{p.get('version', '?')})  [{p['_file']}]")
        print("─" * 60)
        for entry in p.get("changelog", []):
            bt = entry.get("backtest_180d", {})
            ret = bt.get("return_pct")
            wr = bt.get("win_rate")
            trades = bt.get("trades")
            max_dd = bt.get("max_dd_pct")
            note = bt.get("note", "")
            print(f"  v{entry['version']}  {entry.get('date', '')}  [{entry.get('git_sha', '')}]")
            print(f"    {entry.get('description', '')}")
            if ret is not None:
                print(f"    Backtest 180d: return={ret:+.1f}%  wr={wr}%  trades={trades}  max_dd={max_dd}%")
            else:
                print(f"    Backtest 180d: {note}")
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect passport version status")
    parser.add_argument(
        "--passport",
        metavar="NAME",
        help="Show full changelog for a single passport (partial name match)",
    )
    args = parser.parse_args()

    passports = load_passports()

    if args.passport:
        print_passport_detail(passports, args.passport)
    else:
        print_summary(passports)


if __name__ == "__main__":
    main()
