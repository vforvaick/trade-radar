#!/usr/bin/env python3
"""
Cryptopass Prometheus metrics exporter.
Reads from state.db (SQLite) and exposes /metrics on port 9103.
"""
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from bot.sqlite_utils import sqlite_connection
except ModuleNotFoundError:  # Script mode: `python bot/metrics_exporter.py`
    from sqlite_utils import sqlite_connection


DB_PATH = os.environ.get("CRYPTOPASS_STATE_DB", "state.db")
PORT = int(os.environ.get("CRYPTOPASS_METRICS_PORT", "9103"))
REFRESH_INTERVAL = 30  # seconds between DB reads


class MetricsCache:
    """Reads metrics from SQLite and caches them."""

    def __init__(self):
        self._metrics_text = ""
        self._last_refresh = 0

    def refresh(self):
        """Read metrics from DB and format as Prometheus text."""
        lines = []

        try:
            with sqlite_connection(DB_PATH, readonly=True) as conn:
                conn.row_factory = sqlite3.Row

                # --- Per-passport equity (isolated: table may not exist yet) ---
                equity_rows = []
                try:
                    equity_rows = conn.execute(
                        """SELECT passport_name, realized_equity, unrealized_pnl, total_equity, open_positions, timestamp
                           FROM equity_snapshots_v2 e1
                           WHERE timestamp = (SELECT MAX(timestamp) FROM equity_snapshots_v2 e2 WHERE e2.passport_name = e1.passport_name)"""
                    ).fetchall()
                except Exception:
                    pass  # Table not yet created — bot hasn't run its first scan

                lines.append("# HELP cryptopass_equity Current realized equity per passport")
                lines.append("# TYPE cryptopass_equity gauge")
                for row in equity_rows:
                    name = row["passport_name"].replace('"', '')
                    lines.append(f'cryptopass_equity{{passport="{name}"}} {row["realized_equity"]:.4f}')

                # --- Unrealized PnL ---
                lines.append("# HELP cryptopass_unrealized_pnl Current unrealized PnL per passport")
                lines.append("# TYPE cryptopass_unrealized_pnl gauge")
                for row in equity_rows:
                    name = row["passport_name"].replace('"', '')
                    lines.append(f'cryptopass_unrealized_pnl{{passport="{name}"}} {row["unrealized_pnl"]:.4f}')

                # --- Total equity (realized + unrealized) ---
                lines.append("# HELP cryptopass_total_equity Total equity (realized + unrealized) per passport")
                lines.append("# TYPE cryptopass_total_equity gauge")
                for row in equity_rows:
                    name = row["passport_name"].replace('"', '')
                    lines.append(f'cryptopass_total_equity{{passport="{name}"}} {row["total_equity"]:.4f}')

                # --- Open positions per passport ---
                lines.append("# HELP cryptopass_open_positions Open positions per passport")
                lines.append("# TYPE cryptopass_open_positions gauge")
                for row in equity_rows:
                    name = row["passport_name"].replace('"', '')
                    lines.append(f'cryptopass_open_positions{{passport="{name}"}} {row["open_positions"]}')

                # --- Total open positions ---
                total_open = conn.execute(
                    "SELECT COUNT(*) as c FROM positions WHERE status NOT IN ('TP3_CLOSED', 'SL_CLOSED')"
                ).fetchone()["c"]
                lines.append("# HELP cryptopass_open_positions_total Total open positions across all passports")
                lines.append("# TYPE cryptopass_open_positions_total gauge")
                lines.append(f"cryptopass_open_positions_total {total_open}")

                # --- Trade stats per passport (from trade_log) ---
                lines.append("# HELP cryptopass_trades_total Total closed trades per passport")
                lines.append("# TYPE cryptopass_trades_total counter")
                lines.append("# HELP cryptopass_wins_total Total winning trades per passport")
                lines.append("# TYPE cryptopass_wins_total counter")
                lines.append("# HELP cryptopass_win_rate Win rate percentage per passport")
                lines.append("# TYPE cryptopass_win_rate gauge")
                lines.append("# HELP cryptopass_realized_pnl_total Cumulative realized PnL per passport")
                lines.append("# TYPE cryptopass_realized_pnl_total gauge")
                lines.append("# HELP cryptopass_fees_paid_total Cumulative fees paid per passport")
                lines.append("# TYPE cryptopass_fees_paid_total gauge")

                log_rows = conn.execute(
                    "SELECT passport_name, trade_data_json FROM trade_log"
                ).fetchall()

                passport_stats: dict[str, dict] = {}
                for row in log_rows:
                    pname = row["passport_name"]
                    try:
                        data = json.loads(row["trade_data_json"])
                    except Exception:
                        continue
                    if pname not in passport_stats:
                        passport_stats[pname] = {"trades": 0, "wins": 0, "total_pnl": 0.0, "total_fees": 0.0}
                    stats = passport_stats[pname]
                    event = data.get("event", "")
                    if event in ("SL_HIT", "SL_BREAKEVEN", "TP3_HIT"):
                        stats["trades"] += 1
                        pnl = data.get("realized_pnl", 0.0)
                        if pnl > 0:
                            stats["wins"] += 1
                        stats["total_pnl"] += pnl
                        stats["total_fees"] += data.get("fees_paid", 0.0)

                for pname, stats in passport_stats.items():
                    name = pname.replace('"', '')
                    trades = stats["trades"]
                    wins = stats["wins"]
                    wr = (wins / trades * 100) if trades > 0 else 0.0
                    lines.append(f'cryptopass_trades_total{{passport="{name}"}} {trades}')
                    lines.append(f'cryptopass_wins_total{{passport="{name}"}} {wins}')
                    lines.append(f'cryptopass_win_rate{{passport="{name}"}} {wr:.2f}')
                    lines.append(f'cryptopass_realized_pnl_total{{passport="{name}"}} {stats["total_pnl"]:.4f}')
                    lines.append(f'cryptopass_fees_paid_total{{passport="{name}"}} {stats["total_fees"]:.4f}')

                # --- Drawdown per passport ---
                lines.append("# HELP cryptopass_max_drawdown_pct Max drawdown percentage from peak (per passport)")
                lines.append("# TYPE cryptopass_max_drawdown_pct gauge")

                try:
                    all_snapshots = conn.execute(
                        "SELECT passport_name, total_equity, timestamp FROM equity_snapshots_v2 ORDER BY timestamp ASC"
                    ).fetchall()

                    passport_equity_history: dict[str, list] = {}
                    for row in all_snapshots:
                        pname = row["passport_name"]
                        if pname not in passport_equity_history:
                            passport_equity_history[pname] = []
                        passport_equity_history[pname].append(row["total_equity"])

                    for pname, equities in passport_equity_history.items():
                        if len(equities) < 2:
                            continue
                        peak = equities[0]
                        max_dd = 0.0
                        for e in equities:
                            if e > peak:
                                peak = e
                            dd = (peak - e) / peak * 100 if peak > 0 else 0.0
                            if dd > max_dd:
                                max_dd = dd
                        name = pname.replace('"', '')
                        lines.append(f'cryptopass_max_drawdown_pct{{passport="{name}"}} {max_dd:.2f}')
                except Exception:
                    pass  # Table not yet created

                # --- Heartbeat ---
                lines.append("# HELP cryptopass_heartbeat_age_seconds Seconds since last equity snapshot")
                lines.append("# TYPE cryptopass_heartbeat_age_seconds gauge")

                try:
                    last_snap = conn.execute(
                        "SELECT MAX(timestamp) as ts FROM equity_snapshots_v2"
                    ).fetchone()["ts"]
                except Exception:
                    last_snap = None  # Table not yet created

                if last_snap:
                    try:
                        last_dt = datetime.fromisoformat(last_snap)
                        age = (datetime.utcnow() - last_dt).total_seconds()
                        lines.append(f"cryptopass_heartbeat_age_seconds {age:.1f}")
                    except Exception:
                        lines.append("cryptopass_heartbeat_age_seconds -1")
                else:
                    lines.append("cryptopass_heartbeat_age_seconds -1")

                # --- Release info ---
                try:
                    commit = subprocess.check_output(
                        ["git", "rev-parse", "--short", "HEAD"],
                        stderr=subprocess.DEVNULL
                    ).decode().strip()
                    branch = subprocess.check_output(
                        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                        stderr=subprocess.DEVNULL
                    ).decode().strip()
                except Exception:
                    commit = "unknown"
                    branch = "unknown"

                lines.append("# HELP cryptopass_release_info Release metadata")
                lines.append("# TYPE cryptopass_release_info gauge")
                lines.append(f'cryptopass_release_info{{commit="{commit}",branch="{branch}"}} 1')

        except Exception as e:
            lines.append(f"# ERROR reading metrics: {e}")

        self._metrics_text = "\n".join(lines) + "\n"
        self._last_refresh = time.time()

    def get(self) -> str:
        if time.time() - self._last_refresh > REFRESH_INTERVAL:
            self.refresh()
        return self._metrics_text


_cache = MetricsCache()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            content = _cache.get().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default access logs


if __name__ == "__main__":
    print(f"[cryptopass-metrics] Starting on port {PORT}, DB: {DB_PATH}", flush=True)
    _cache.refresh()
    server = HTTPServer(("0.0.0.0", PORT), MetricsHandler)
    print(f"[cryptopass-metrics] Listening on :{PORT}", flush=True)
    server.serve_forever()
