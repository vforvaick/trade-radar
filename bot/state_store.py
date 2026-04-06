import os
import sqlite3
import json
from dataclasses import asdict
from datetime import datetime
from typing import Optional


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _json_default(value):
    """Serialize datetime and numpy scalar values from Signal payloads."""
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _resolve_db_path(db_path=None) -> str:
    candidate = db_path or os.environ.get("CRYPTOPASS_STATE_DB", "state.db")
    if os.path.isabs(candidate):
        return candidate
    return os.path.abspath(os.path.join(_REPO_ROOT, candidate))


class StateStore:
    def __init__(self, db_path=None):
        self.db_path = _resolve_db_path(db_path)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table for open and closed positions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    passport_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal_json TEXT NOT NULL,
                    status TEXT DEFAULT 'OPEN',
                    risk_amount REAL NOT NULL,
                    equity_at_entry REAL NOT NULL,
                    tp1_hit INTEGER DEFAULT 0,
                    tp2_hit INTEGER DEFAULT 0,
                    tp3_hit INTEGER DEFAULT 0,
                    sl_is_breakeven INTEGER DEFAULT 0,
                    realized_pnl REAL DEFAULT 0.0,
                    trailing_sl REAL,
                    tg_msg_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table for equity snapshots
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    passport_name TEXT NOT NULL,
                    equity REAL NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table for trade logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    passport_name TEXT NOT NULL,
                    trade_data_json TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for equity snapshots with unrealized PnL (v2)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS equity_snapshots_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    passport_name TEXT NOT NULL,
                    realized_equity REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
                    total_equity REAL NOT NULL,
                    open_positions INTEGER NOT NULL DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()

    def save_position(self, passport_name: str, signal, equity_at_entry: float, risk_amount: float, tg_msg_id: Optional[int] = None) -> int:
        """Save a new position to the database."""
        sig_dict = asdict(signal)
        signal_json = json.dumps(sig_dict, default=_json_default)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO positions (passport_name, symbol, signal_json, equity_at_entry, risk_amount, tg_msg_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (passport_name, signal.symbol, signal_json, equity_at_entry, risk_amount, tg_msg_id))
            conn.commit()
            return cursor.lastrowid

    def update_position(self, pos_id: int, **kwargs):
        """Update fields of an existing position."""
        if not kwargs:
            return
            
        set_clauses = []
        values = []
        
        # Mapping boolean to integer for SQLite
        for k, v in kwargs.items():
            if isinstance(v, bool):
                v = 1 if v else 0
            set_clauses.append(f"{k} = ?")
            values.append(v)
            
        values.append(pos_id)
        
        query = f"UPDATE positions SET {', '.join(set_clauses)} WHERE id = ?"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(values))
            conn.commit()

    def load_open_positions(self, passport_name: Optional[str] = None) -> list[dict]:
        """Load all open positions, optionally filtered by passport."""
        query = "SELECT * FROM positions WHERE status NOT IN ('TP3_CLOSED', 'SL_CLOSED')"
        params = ()
        
        if passport_name:
            query += " AND passport_name = ?"
            params = (passport_name,)
            
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]

    def save_equity(self, passport_name: str, equity: float):
        """Save current equity snapshot."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO equity_snapshots (passport_name, equity)
                VALUES (?, ?)
            ''', (passport_name, equity))
            conn.commit()

    def get_last_equity(self, passport_name: str) -> Optional[float]:
        """Get the most recent equity snapshot for a passport."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT equity FROM equity_snapshots
                WHERE passport_name = ?
                ORDER BY timestamp DESC, id DESC LIMIT 1
            ''', (passport_name,))
            row = cursor.fetchone()
            
            return row[0] if row else None

    def log_trade(self, passport_name: str, trade_data: dict):
        """Log a trade event/closure."""
        trade_json = json.dumps(trade_data, default=_json_default)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trade_log (passport_name, trade_data_json)
                VALUES (?, ?)
            ''', (passport_name, trade_json))
            conn.commit()

    def save_equity_v2(self, passport_name: str, realized_equity: float, unrealized_pnl: float, open_positions: int):
        """Save equity snapshot with unrealized PnL breakdown."""
        total = realized_equity + unrealized_pnl
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO equity_snapshots_v2 (passport_name, realized_equity, unrealized_pnl, total_equity, open_positions) VALUES (?,?,?,?,?)",
                (passport_name, realized_equity, unrealized_pnl, total, open_positions),
            )

    def get_equity_history_v2(self, passport_name: str, limit: int = 100) -> list[dict]:
        """Get recent equity snapshots with unrealized PnL for a passport."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM equity_snapshots_v2 WHERE passport_name=? ORDER BY timestamp DESC LIMIT ?",
                (passport_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_signal_message_id(self, symbol: str, passport_name: str) -> Optional[int]:
        """Find the telegram message ID associated with an active signal."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Try to get the latest open position for this symbol/passport
            cursor.execute('''
                SELECT tg_msg_id FROM positions 
                WHERE symbol = ? AND passport_name = ? AND status NOT IN ('TP3_CLOSED', 'SL_CLOSED')
                ORDER BY created_at DESC LIMIT 1
            ''', (symbol, passport_name))
            row = cursor.fetchone()
            
            if row and row[0]:
                return row[0]
                
            # Fallback if position closed, get the most recent one
            cursor.execute('''
                SELECT tg_msg_id FROM positions 
                WHERE symbol = ? AND passport_name = ?
                ORDER BY created_at DESC LIMIT 1
            ''', (symbol, passport_name))
            row = cursor.fetchone()
            return row[0] if row else None

    def load_active_message_ids(self) -> dict:
        """Load all active signal message IDs for Notifier."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, passport_name, tg_msg_id FROM positions 
                WHERE tg_msg_id IS NOT NULL 
                AND status NOT IN ('TP3_CLOSED', 'SL_CLOSED')
            ''')
            rows = cursor.fetchall()
            return {(row[0], row[1]): row[2] for row in rows}
