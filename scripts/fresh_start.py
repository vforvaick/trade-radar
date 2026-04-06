#!/usr/bin/env python3
"""
Cryptopass Fresh Start Migration Script.

Clears all trade history and equity snapshots from state.db,
preparing for a clean re-run with corrected PnL calculations.

Usage:
    python scripts/fresh_start.py [--db /path/to/state.db] [--confirm]
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime


def run_fresh_start(db_path: str, confirm: bool = False):
    if not os.path.exists(db_path):
        print(f"[fresh_start] DB not found: {db_path}")
        print("[fresh_start] Nothing to clear — starting fresh automatically.")
        return

    conn = sqlite3.connect(db_path)

    # Count existing data
    try:
        positions = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        equity_snaps = conn.execute("SELECT COUNT(*) FROM equity_snapshots").fetchone()[0]
        trade_log = conn.execute("SELECT COUNT(*) FROM trade_log").fetchone()[0]
    except Exception:
        positions = equity_snaps = trade_log = 0

    print(f"[fresh_start] Current state:")
    print(f"  positions:        {positions}")
    print(f"  equity_snapshots: {equity_snaps}")
    print(f"  trade_log:        {trade_log}")

    if positions == 0 and equity_snaps == 0 and trade_log == 0:
        print("[fresh_start] DB is already empty. Creating equity_snapshots_v2 table if needed.")
    else:
        if not confirm:
            print("\n[fresh_start] ⚠️  This will DELETE all trade history!")
            print("[fresh_start] Run with --confirm to proceed.")
            conn.close()
            return

        print(f"\n[fresh_start] Clearing all trade history at {datetime.utcnow().isoformat()}Z...")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM equity_snapshots")
        conn.execute("DELETE FROM trade_log")
        # Also clear v2 snapshots if the table exists
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "equity_snapshots_v2" in tables:
            conn.execute("DELETE FROM equity_snapshots_v2")
        conn.commit()
        print("[fresh_start] ✅ Cleared positions, equity_snapshots, equity_snapshots_v2, trade_log")

    # Ensure equity_snapshots_v2 table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equity_snapshots_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passport_name TEXT NOT NULL,
            realized_equity REAL NOT NULL,
            unrealized_pnl REAL NOT NULL DEFAULT 0.0,
            total_equity REAL NOT NULL,
            open_positions INTEGER NOT NULL DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    print("[fresh_start] ✅ equity_snapshots_v2 table ready")

    conn.close()
    print("[fresh_start] 🚀 Ready for fresh start at $500 per passport")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cryptopass fresh start migration")
    parser.add_argument("--db", default=os.environ.get("CRYPTOPASS_STATE_DB", "state.db"))
    parser.add_argument("--confirm", action="store_true", help="Actually delete data")
    args = parser.parse_args()
    run_fresh_start(args.db, args.confirm)
