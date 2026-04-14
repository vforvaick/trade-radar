# bot/reporting/daily_report.py
"""Daily Telegram performance report for all passports."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from bot.sqlite_utils import sqlite_connection


class DailyReportBuilder:
    """Builds daily performance summary for all passports."""

    def __init__(
        self,
        state_db_path: str = "state.db",
        initial_equity: float = 500.0,
    ):
        self.state_db_path = state_db_path
        self.initial_equity = initial_equity

    def get_passport_summaries(self) -> list[dict]:
        try:
            with sqlite_connection(self.state_db_path, readonly=True) as conn:
                conn.row_factory = sqlite3.Row

                cur = conn.execute("""
                    SELECT passport_name,
                           equity as current_equity,
                           timestamp
                    FROM equity_snapshots e1
                    WHERE timestamp = (
                        SELECT MAX(timestamp) FROM equity_snapshots e2
                        WHERE e2.passport_name = e1.passport_name
                    )
                    GROUP BY passport_name
                """)
                snapshots = {row["passport_name"]: dict(row) for row in cur.fetchall()}

                cur = conn.execute("""
                    SELECT passport_name,
                           COUNT(*) as total_trades,
                           SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                           COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open_positions
                    FROM positions
                    GROUP BY passport_name
                """)
                trade_stats = {row["passport_name"]: dict(row) for row in cur.fetchall()}
        except sqlite3.OperationalError:
            return []

        summaries = []
        for name, snap in snapshots.items():
            equity = snap["current_equity"]
            pnl_pct = ((equity - self.initial_equity) / self.initial_equity) * 100
            stats = trade_stats.get(name, {})
            total = stats.get("total_trades", 0)
            wins = stats.get("wins", 0)
            wr = (wins / total * 100) if total > 0 else 0

            summaries.append({
                "name": name,
                "current_equity": equity,
                "pnl_pct": round(pnl_pct, 2),
                "total_trades": total,
                "win_rate": round(wr, 1),
                "open_positions": stats.get("open_positions", 0),
            })

        summaries.sort(key=lambda x: x["pnl_pct"], reverse=True)
        return summaries

    def build(self) -> str:
        summaries = self.get_passport_summaries()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            f"📊 Cryptopass Daily Report — {now}",
            "",
        ]

        if not summaries:
            lines.append("No passport data available.")
            return "\n".join(lines)

        total_equity = sum(s["current_equity"] for s in summaries)
        total_initial = self.initial_equity * len(summaries)
        total_pnl_pct = ((total_equity - total_initial) / total_initial) * 100 if total_initial > 0 else 0

        lines.append(
            f"💰 Total: ${total_equity:,.2f} / ${total_initial:,.2f} ({total_pnl_pct:+.1f}%)"
        )
        lines.append("")

        # Top performers
        lines.append("=== TOP PERFORMERS ===")
        for s in summaries[:10]:
            icon = "🔥" if s["pnl_pct"] > 10 else "📈" if s["pnl_pct"] > 0 else "📉"
            lines.append(
                f"{icon} {s['name']}: {s['pnl_pct']:+.1f}% | "
                f"{s['total_trades']}t WR={s['win_rate']:.0f}% | "
                f"{s['open_positions']} open"
            )

        # Worst performers
        worst = [s for s in summaries if s["pnl_pct"] < -10]
        if worst:
            lines.append("")
            lines.append("=== NEEDS ATTENTION ===")
            for s in worst[-5:]:
                lines.append(
                    f"⚠️ {s['name']}: {s['pnl_pct']:+.1f}% | "
                    f"{s['total_trades']}t WR={s['win_rate']:.0f}%"
                )

        return "\n".join(lines)

    def send_via_telegram(self, notifier) -> None:
        report = self.build()
        notifier.send_update(report)
