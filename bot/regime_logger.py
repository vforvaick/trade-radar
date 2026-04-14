# bot/regime_logger.py
"""Regime data collection and daily digest reporting.

Collects per-scan regime snapshots, per-signal regime tags, and per-trade
regime tags into SQLite tables in state.db. Generates daily Telegram digest.
"""
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from bot.state_store import StateStore
from bot.sqlite_utils import sqlite_connection

logger = logging.getLogger(__name__)


class RegimeLogger:
    """Handles all regime data collection and reporting."""

    def __init__(self, state_store: StateStore):
        self.state_store = state_store
        self._ensure_tables()

    def _ensure_tables(self):
        """Create regime logging tables if they don't exist."""
        with sqlite_connection(self.state_store.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS regime_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    regime TEXT NOT NULL,
                    btc_price REAL,
                    adx REAL,
                    ret_30d REAL,
                    realized_vol REAL,
                    ema9_1h REAL,
                    ema21_1h REAL,
                    confirmation_matched INTEGER,
                    total_signals INTEGER,
                    total_opened INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_regime_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    regime TEXT NOT NULL,
                    passport_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence_raw REAL,
                    confidence_adjusted REAL,
                    btc_weight_applied REAL,
                    was_executed INTEGER DEFAULT 0,
                    skip_reason TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_regime_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    trade_id INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    regime TEXT NOT NULL
                )
            """)

    def log_scan(self, regime: str, metadata: dict,
                 total_signals: int, total_opened: int):
        """Log per-scan regime snapshot."""
        with sqlite_connection(self.state_store.db_path) as conn:
            conn.execute(
                """INSERT INTO regime_snapshots
                   (regime, btc_price, adx, ret_30d, realized_vol,
                    ema9_1h, ema21_1h, confirmation_matched,
                    total_signals, total_opened)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    regime,
                    metadata.get("btc_price"),
                    metadata.get("adx"),
                    metadata.get("ret_30d"),
                    metadata.get("realized_vol"),
                    metadata.get("ema9_1h"),
                    metadata.get("ema21_1h"),
                    1 if metadata.get("confirmation_matched") else 0,
                    total_signals,
                    total_opened,
                ),
            )

    def log_signal(self, regime: str, passport_name: str, symbol: str,
                   direction: str, confidence_raw: float, confidence_adjusted: float,
                   btc_weight: float, was_executed: bool,
                   skip_reason: Optional[str] = None):
        """Log per-signal regime tag."""
        with sqlite_connection(self.state_store.db_path) as conn:
            conn.execute(
                """INSERT INTO signal_regime_log
                   (regime, passport_name, symbol, direction,
                    confidence_raw, confidence_adjusted, btc_weight_applied,
                    was_executed, skip_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    regime, passport_name, symbol, direction,
                    confidence_raw, confidence_adjusted, btc_weight,
                    1 if was_executed else 0, skip_reason,
                ),
            )

    def tag_trade_regime(self, event: str, trade_id: int, regime: str):
        """Tag a trade with current regime (event='open' or 'close')."""
        with sqlite_connection(self.state_store.db_path) as conn:
            conn.execute(
                "INSERT INTO trade_regime_tags (trade_id, event, regime) VALUES (?, ?, ?)",
                (trade_id, event, regime),
            )

    def generate_daily_digest(self) -> str:
        """Generate daily regime report text for Telegram."""
        with sqlite_connection(self.state_store.db_path, readonly=True) as conn:
            conn.row_factory = sqlite3.Row

            latest = conn.execute(
                "SELECT * FROM regime_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()

            cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            dist_rows = conn.execute(
                "SELECT regime, COUNT(*) as cnt FROM regime_snapshots "
                "WHERE timestamp >= ? GROUP BY regime ORDER BY cnt DESC",
                (cutoff,),
            ).fetchall()

            sig_stats = conn.execute(
                "SELECT COUNT(*) as total, SUM(was_executed) as executed "
                "FROM signal_regime_log WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()

        lines = [
            "📊 Cryptopass Daily Regime Report",
            "━" * 32,
        ]

        if latest:
            latest = dict(latest)
            lines.append(f"🌍 Current: {latest.get('regime', 'Unknown')}")
            btc_price = latest.get("btc_price")
            adx = latest.get("adx")
            ret = latest.get("ret_30d")
            vol = latest.get("realized_vol")
            lines.append(
                f"📈 BTC: ${btc_price:,.0f} | ADX: {adx:.1f} | "
                f"30d: {ret:+.1f}% | Vol: {vol:.1%}"
                if btc_price else "📈 No BTC data yet"
            )
        else:
            lines.append("🌍 No regime data collected yet")

        lines.append("")
        lines.append("⏰ Regime Distribution (24h):")
        total_scans = sum(dict(r)["cnt"] for r in dist_rows) if dist_rows else 0
        if dist_rows:
            for row in dist_rows:
                row = dict(row)
                pct = row["cnt"] / total_scans * 100 if total_scans > 0 else 0
                lines.append(f"  {row['regime']}: {row['cnt']}/{total_scans} ({pct:.0f}%)")
        else:
            lines.append("  No data")

        lines.append("")
        if sig_stats:
            sig_stats = dict(sig_stats)
            total = sig_stats["total"] or 0
            executed = sig_stats["executed"] or 0
            rate = executed / total * 100 if total > 0 else 0
            lines.append(
                f"💡 Signals: {total} generated → {executed} executed ({rate:.0f}% rate)"
            )
        else:
            lines.append("💡 No signals generated")

        lines.append("━" * 32)
        return "\n".join(lines)

    def send_daily_digest(self, notifier):
        """Send daily digest to Telegram via notifier.send_update()."""
        text = self.generate_daily_digest()
        if notifier:
            notifier.send_update(text)
        else:
            print(text, flush=True)
