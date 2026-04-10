#!/usr/bin/env python3
"""
Cryptopass Daily PnL Monitor
Pulls state.db from VPS and displays a comprehensive performance dashboard.

Usage:
    uv run python scripts/daily_monitor.py
    uv run python scripts/daily_monitor.py --local path/to/state.db
    uv run python scripts/daily_monitor.py --no-fetch  # use last cached db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─────────────────────────────── constants ──────────────────────────────────

VPS_HOST = "fight-tres"
VPS_DB_PATH = "/home/vforvaick/pumpradar-bot/state.db"
LOCAL_DB_CACHE = Path("state_monitor_cache.db")   # relative to cwd (no /tmp)
STARTING_EQUITY_PER_PASSPORT = 500.0
CTP_DEPLOY_DATE = "2026-04-09"  # Counter-Trend Penalty deployment date

FOCUS_PASSPORTS = [
    "PressureReader",
    "MACDDivergence",
    "BreakoutVol",
    "BollingerBreakout",
]

# ANSI colours
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# ─────────────────────────────── SSH helpers ────────────────────────────────


def fetch_db_from_vps(local_path: Path) -> bool:
    """Copy state.db from VPS via scp. Returns True on success."""
    cmd = ["scp", f"{VPS_HOST}:{VPS_DB_PATH}", str(local_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"{RED}[SSH ERROR]{RESET} {result.stderr.strip()}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"{RED}[SSH ERROR]{RESET} Connection timed out after 30s")
        return False
    except FileNotFoundError:
        print(f"{RED}[SSH ERROR]{RESET} scp not found — is SSH configured?")
        return False


# ─────────────────────────────── DB queries ─────────────────────────────────


def load_trade_log(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load all rows from trade_log, parsing trade_data_json."""
    rows = conn.execute(
        "SELECT passport_name, timestamp, trade_data_json FROM trade_log ORDER BY id"
    ).fetchall()
    trades: list[dict[str, Any]] = []
    for passport_name, ts, raw in rows:
        try:
            data = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        data["passport_name"] = passport_name
        data["timestamp"] = ts or ""
        trades.append(data)
    return trades


def load_latest_snapshots(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Return the latest equity snapshot per passport."""
    rows = conn.execute(
        """
        SELECT passport_name, timestamp, realized_equity, unrealized_pnl,
               total_equity, open_positions
        FROM equity_snapshots_v2
        WHERE id IN (
            SELECT MAX(id) FROM equity_snapshots_v2 GROUP BY passport_name
        )
        """
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for name, ts, realized, unrealized, total, open_pos in rows:
        out[name] = {
            "timestamp": ts or "",
            "realized_equity": realized or 0.0,
            "unrealized_pnl": unrealized or 0.0,
            "total_equity": total or 0.0,
            "open_positions": open_pos or 0,
        }
    return out


def load_previous_snapshots(
    conn: sqlite3.Connection, cutoff_hours: int = 24
) -> dict[str, float]:
    """Return the latest equity snapshot per passport taken before ~24h ago."""
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT passport_name, timestamp, total_equity FROM equity_snapshots_v2 ORDER BY id"
    ).fetchall()
    # Gather all snapshots, pick the last one that is ≥ cutoff_hours old
    buckets: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for name, ts, eq in rows:
        buckets[name].append((ts or "", eq or 0.0))

    result: dict[str, float] = {}
    for name, entries in buckets.items():
        # Filter entries older than cutoff_hours
        old_entries = []
        for ts_str, eq in entries:
            try:
                # Try parsing ISO format
                ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                age_h = (now - ts_dt).total_seconds() / 3600
                if age_h >= cutoff_hours:
                    old_entries.append((ts_dt, eq))
            except (ValueError, AttributeError):
                pass
        if old_entries:
            # The most recent among old entries
            result[name] = sorted(old_entries)[-1][1]
    return result


# ─────────────────────────────── aggregation ────────────────────────────────


def compute_passport_stats(
    trades: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Compute per-passport win/loss stats from trade_log entries."""
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "long_pnl": 0.0,
            "short_pnl": 0.0,
            "long_trades": 0,
            "short_trades": 0,
            "long_wins": 0,
            "short_wins": 0,
            "pre_ctp_pnl": 0.0,
            "post_ctp_pnl": 0.0,
        }
    )
    for t in trades:
        name = t.get("passport_name", "Unknown")
        pnl = float(t.get("realized_pnl", 0) or 0)
        direction = (t.get("direction") or "").upper()
        ts = t.get("timestamp", "")
        s = stats[name]
        s["pnl"] += pnl
        if pnl > 0:
            s["wins"] += 1
            s["gross_profit"] += pnl
        elif pnl < 0:
            s["losses"] += 1
            s["gross_loss"] += abs(pnl)

        if direction == "LONG":
            s["long_pnl"] += pnl
            s["long_trades"] += 1
            if pnl > 0:
                s["long_wins"] += 1
        elif direction == "SHORT":
            s["short_pnl"] += pnl
            s["short_trades"] += 1
            if pnl > 0:
                s["short_wins"] += 1

        # CTP split
        if ts and ts[:10] >= CTP_DEPLOY_DATE:
            s["post_ctp_pnl"] += pnl
        else:
            s["pre_ctp_pnl"] += pnl

    return dict(stats)


def compute_portfolio_direction_stats(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate LONG vs SHORT across entire portfolio."""
    agg: dict[str, Any] = {
        "long_trades": 0,
        "short_trades": 0,
        "long_pnl": 0.0,
        "short_pnl": 0.0,
        "long_wins": 0,
        "short_wins": 0,
    }
    for t in trades:
        pnl = float(t.get("realized_pnl", 0) or 0)
        direction = (t.get("direction") or "").upper()
        if direction == "LONG":
            agg["long_trades"] += 1
            agg["long_pnl"] += pnl
            if pnl > 0:
                agg["long_wins"] += 1
        elif direction == "SHORT":
            agg["short_trades"] += 1
            agg["short_pnl"] += pnl
            if pnl > 0:
                agg["short_wins"] += 1
    return agg


# ─────────────────────────────── formatting ─────────────────────────────────


def _pnl_color(val: float) -> str:
    return GREEN if val >= 0 else RED


def _fmt_pnl(val: float, width: int = 10) -> str:
    sign = "+" if val >= 0 else ""
    colored = f"{_pnl_color(val)}{sign}${val:,.2f}{RESET}"
    return colored


def _fmt_pct(val: float, width: int = 7) -> str:
    sign = "+" if val >= 0 else ""
    colored = f"{_pnl_color(val)}{sign}{val:.1f}%{RESET}"
    return colored


def _win_rate(wins: int, total: int) -> float:
    return (wins / total * 100) if total > 0 else 0.0


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    return (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)


def _pf_str(pf: float) -> str:
    if pf == float("inf"):
        return "∞"
    return f"{pf:.2f}"


def print_header() -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M WIB")
    width = 68
    print(f"\n{BOLD}╔{'═' * width}╗")
    title = "CRYPTOPASS DAILY MONITOR"
    pad_t = (width - len(title)) // 2
    print(f"║{' ' * pad_t}{title}{' ' * (width - pad_t - len(title))}║")
    pad_d = (width - len(now_str)) // 2
    print(f"║{' ' * pad_d}{now_str}{' ' * (width - pad_d - len(now_str))}║")
    print(f"╠{'═' * width}╣{RESET}")


def print_focus_section(
    focus: list[str],
    passport_stats: dict[str, dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    prev_snapshots: dict[str, float],
) -> None:
    print(f"\n{BOLD}{YELLOW}⭐ FOCUS PASSPORTS{RESET}")
    _print_passport_table(focus, passport_stats, snapshots, prev_snapshots)


def print_all_passports_section(
    passport_stats: dict[str, dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    prev_snapshots: dict[str, float],
) -> None:
    print(f"\n{BOLD}{CYAN}📊 ALL PASSPORTS (sorted by total equity){RESET}")
    # Combine keys from both sources
    all_names = sorted(
        set(passport_stats.keys()) | set(snapshots.keys()),
        key=lambda n: -(snapshots.get(n, {}).get("total_equity") or
                        (STARTING_EQUITY_PER_PASSPORT + (passport_stats.get(n, {}).get("pnl") or 0))),
    )
    _print_passport_table(all_names, passport_stats, snapshots, prev_snapshots)


def _print_passport_table(
    names: list[str],
    passport_stats: dict[str, dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    prev_snapshots: dict[str, float],
) -> None:
    header = f"  {'Passport':<22} {'Equity':>10}  {'Daily Δ':>10}  {'WR':>7}  {'PF':>6}  {'Trades':>6}  Open"
    print(f"{DIM}{header}{RESET}")
    print(f"  {'─' * 78}")

    for name in names:
        snap = snapshots.get(name, {})
        st = passport_stats.get(name, {})

        total_eq = snap.get("total_equity") or (
            STARTING_EQUITY_PER_PASSPORT + st.get("pnl", 0.0)
        )
        unrealized = snap.get("unrealized_pnl", 0.0)
        open_pos = snap.get("open_positions", 0)

        wins = st.get("wins", 0)
        losses = st.get("losses", 0)
        trades = wins + losses
        wr = _win_rate(wins, trades)
        pf = _profit_factor(st.get("gross_profit", 0.0), st.get("gross_loss", 0.0))

        # Daily delta
        prev_eq = prev_snapshots.get(name)
        if prev_eq is not None:
            delta = total_eq - prev_eq
            delta_str = _fmt_pnl(delta, 10)
        else:
            delta_str = f"{DIM}  n/a      {RESET}"

        eq_color = _pnl_color(total_eq - STARTING_EQUITY_PER_PASSPORT)
        eq_str = f"{eq_color}${total_eq:>8,.2f}{RESET}"

        focus_marker = "⭐" if name in FOCUS_PASSPORTS else "  "
        print(
            f"  {focus_marker}{name:<20} {eq_str}  {delta_str:<10}  "
            f"{wr:>5.1f}%  {_pf_str(pf):>6}  {trades:>6}  {open_pos}"
        )


def print_direction_analysis(
    direction_stats: dict[str, Any],
    passport_stats: dict[str, dict[str, Any]],
) -> None:
    print(f"\n{BOLD}{CYAN}📈 DIRECTION ANALYSIS{RESET}")

    long_t = direction_stats["long_trades"]
    short_t = direction_stats["short_trades"]
    long_pnl = direction_stats["long_pnl"]
    short_pnl = direction_stats["short_pnl"]
    long_w = direction_stats["long_wins"]
    short_w = direction_stats["short_wins"]

    long_wr = _win_rate(long_w, long_t)
    short_wr = _win_rate(short_w, short_t)

    print(f"  LONG : {long_t:>5} trades  {_fmt_pnl(long_pnl):<20}  WR:{long_wr:>5.1f}%")
    print(f"  SHORT: {short_t:>5} trades  {_fmt_pnl(short_pnl):<20}  WR:{short_wr:>5.1f}%")

    # CTP breakdown
    print(f"\n{BOLD}{CYAN}🗓  PRE vs POST CTP ({CTP_DEPLOY_DATE}){RESET}")
    pre_total = sum(s.get("pre_ctp_pnl", 0) for s in passport_stats.values())
    post_total = sum(s.get("post_ctp_pnl", 0) for s in passport_stats.values())
    print(f"  Pre-CTP  (before {CTP_DEPLOY_DATE}): {_fmt_pnl(pre_total)}")
    print(f"  Post-CTP (from   {CTP_DEPLOY_DATE}): {_fmt_pnl(post_total)}")


def print_portfolio_total(
    snapshots: dict[str, dict[str, Any]],
    passport_stats: dict[str, dict[str, Any]],
    prev_snapshots: dict[str, float],
) -> None:
    all_names = set(snapshots.keys()) | set(passport_stats.keys())
    total_eq = 0.0
    total_unrealized = 0.0
    for name in all_names:
        snap = snapshots.get(name, {})
        st = passport_stats.get(name, {})
        eq = snap.get("total_equity") or (
            STARTING_EQUITY_PER_PASSPORT + st.get("pnl", 0.0)
        )
        total_eq += eq
        total_unrealized += snap.get("unrealized_pnl", 0.0)

    n_passports = len(all_names)
    starting_total = STARTING_EQUITY_PER_PASSPORT * n_passports
    pnl_total = total_eq - starting_total
    pct = (pnl_total / starting_total * 100) if starting_total > 0 else 0.0

    # Daily portfolio delta
    if prev_snapshots:
        prev_total = sum(prev_snapshots.values())
        # For passports not in prev_snapshots use current equity (no change)
        for name in all_names:
            if name not in prev_snapshots:
                snap = snapshots.get(name, {})
                st = passport_stats.get(name, {})
                prev_total += snap.get("total_equity") or (
                    STARTING_EQUITY_PER_PASSPORT + st.get("pnl", 0.0)
                )
        daily_delta = total_eq - prev_total
        daily_str = f"  Daily Δ: {_fmt_pnl(daily_delta)}"
    else:
        daily_str = ""

    width = 68
    print(f"\n{BOLD}{'═' * (width + 2)}{RESET}")
    color = _pnl_color(pnl_total)
    print(
        f"{BOLD}💰 PORTFOLIO TOTAL: "
        f"${total_eq:,.2f} / ${starting_total:,.0f} "
        f"({color}{'+' if pct>=0 else ''}{pct:.1f}%{RESET}{BOLD}){RESET}"
    )
    if total_unrealized != 0:
        print(f"   Unrealized: {_fmt_pnl(total_unrealized)}")
    if daily_str:
        print(daily_str)
    print(f"   Passports tracked: {n_passports}")
    print()


# ─────────────────────────────── main ───────────────────────────────────────


def run(db_path: Path) -> None:
    if not db_path.exists():
        print(f"{RED}DB not found: {db_path}{RESET}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        _check_schema(conn)
        trades = load_trade_log(conn)
        snapshots = load_latest_snapshots(conn)
        prev_snapshots = load_previous_snapshots(conn, cutoff_hours=24)
    finally:
        conn.close()

    passport_stats = compute_passport_stats(trades)
    direction_stats = compute_portfolio_direction_stats(trades)

    print_header()
    print_focus_section(FOCUS_PASSPORTS, passport_stats, snapshots, prev_snapshots)
    print_all_passports_section(passport_stats, snapshots, prev_snapshots)
    print_direction_analysis(direction_stats, passport_stats)
    print_portfolio_total(snapshots, passport_stats, prev_snapshots)


def _check_schema(conn: sqlite3.Connection) -> None:
    """Verify expected tables exist; raise with a helpful message if not."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    missing = {"trade_log", "equity_snapshots_v2"} - tables
    if missing:
        available = ", ".join(sorted(tables)) or "(none)"
        raise RuntimeError(
            f"Missing tables: {missing}. Available: {available}\n"
            "Ensure the DB is from the correct VPS instance."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Cryptopass Daily Monitor")
    parser.add_argument("--local", metavar="PATH", help="Use a local DB file instead of fetching from VPS")
    parser.add_argument("--no-fetch", action="store_true", help="Skip VPS fetch; use cached DB")
    args = parser.parse_args()

    if args.local:
        db_path = Path(args.local)
        if not db_path.exists():
            print(f"{RED}Local DB not found: {db_path}{RESET}")
            sys.exit(1)
    elif args.no_fetch:
        db_path = LOCAL_DB_CACHE
        if not db_path.exists():
            print(f"{RED}No cached DB found. Run without --no-fetch first.{RESET}")
            sys.exit(1)
    else:
        db_path = LOCAL_DB_CACHE
        print(f"{DIM}Fetching state.db from {VPS_HOST}…{RESET}", flush=True)
        ok = fetch_db_from_vps(db_path)
        if not ok:
            if db_path.exists():
                print(f"{YELLOW}Using cached DB (may be stale).{RESET}")
            else:
                print(f"{RED}Cannot connect to VPS and no cached DB available.{RESET}")
                sys.exit(1)
        else:
            print(f"{GREEN}✓ DB fetched.{RESET}")

    try:
        run(db_path)
    except RuntimeError as exc:
        print(f"{RED}[ERROR]{RESET} {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
