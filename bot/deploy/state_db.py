"""State DB — SQLite schema for tracking trading state across restarts."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional


class StateDB:
    """Persistent state database for the trading system."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS passport_state (
        passport_id TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'generated',
        version TEXT,
        family TEXT,
        config TEXT,
        metrics TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS trade_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        passport_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        entry_price REAL,
        exit_price REAL,
        pnl REAL,
        namespace TEXT NOT NULL DEFAULT 'paper',
        opened_at TEXT,
        closed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        payload TEXT,
        timestamp TEXT NOT NULL
    );
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self.SCHEMA)

    def upsert_passport(self, passport_id: str, status: str,
                         version: Optional[str] = None,
                         family: Optional[str] = None,
                         config: Optional[dict] = None,
                         metrics: Optional[dict] = None):
        now = datetime.now().isoformat()
        self._conn.execute("""
            INSERT INTO passport_state (passport_id, status, version, family, config, metrics, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(passport_id) DO UPDATE SET
                status=excluded.status, version=excluded.version,
                family=excluded.family, config=excluded.config,
                metrics=excluded.metrics, updated_at=excluded.updated_at
        """, (passport_id, status, version, family,
              json.dumps(config) if config else None,
              json.dumps(metrics) if metrics else None,
              now, now))
        self._conn.commit()

    def get_passport(self, passport_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM passport_state WHERE passport_id = ?",
            (passport_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("config"):
            d["config"] = json.loads(d["config"])
        if d.get("metrics"):
            d["metrics"] = json.loads(d["metrics"])
        return d

    def list_passports(self, status: Optional[str] = None) -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM passport_state WHERE status = ?", (status,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM passport_state").fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("config"):
                d["config"] = json.loads(d["config"])
            if d.get("metrics"):
                d["metrics"] = json.loads(d["metrics"])
            results.append(d)
        return results

    def log_trade(self, passport_id: str, symbol: str, direction: str,
                  entry_price: float, exit_price: Optional[float] = None,
                  pnl: Optional[float] = None, namespace: str = "paper"):
        now = datetime.now().isoformat()
        self._conn.execute("""
            INSERT INTO trade_log (passport_id, symbol, direction, entry_price,
                                    exit_price, pnl, namespace, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (passport_id, symbol, direction, entry_price,
              exit_price, pnl, namespace, now))
        self._conn.commit()

    def get_trades(self, passport_id: Optional[str] = None,
                   namespace: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM trade_log WHERE 1=1"
        params = []
        if passport_id:
            query += " AND passport_id = ?"
            params.append(passport_id)
        if namespace:
            query += " AND namespace = ?"
            params.append(namespace)
        return [dict(r) for r in self._conn.execute(query, params).fetchall()]

    def log_event(self, event_type: str, payload: Optional[dict] = None):
        self._conn.execute("""
            INSERT INTO system_events (event_type, payload, timestamp) VALUES (?, ?, ?)
        """, (event_type, json.dumps(payload) if payload else None,
              datetime.now().isoformat()))
        self._conn.commit()

    def close(self):
        self._conn.close()
