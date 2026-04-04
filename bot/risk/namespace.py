"""Namespace Manager — paper/prod isolation with separate SQLite DBs."""
from __future__ import annotations

import json
import os
import sqlite3


VALID_NAMESPACES = {"paper", "prod"}


class NamespaceManager:
    """Manages paper/prod namespace isolation via separate SQLite databases."""

    def __init__(self, base_dir: str, namespace: str):
        if namespace not in VALID_NAMESPACES:
            raise ValueError(f"Invalid namespace: {namespace}. Must be one of {VALID_NAMESPACES}")
        self.namespace = namespace
        self.base_dir = base_dir
        self.db_path = os.path.join(base_dir, f"{namespace}.db")
        self.table_prefix = f"{namespace}_"
        self.telegram_prefix = f"[{namespace.upper()}]"
        os.makedirs(base_dir, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL
        )""")
        conn.commit()
        conn.close()

    def write_position(self, data: dict):
        conn = sqlite3.connect(self.db_path)
        pos_id = data.get("id", data.get("position_id", "unknown"))
        conn.execute("INSERT OR REPLACE INTO positions (id, data) VALUES (?, ?)",
                      (pos_id, json.dumps(data)))
        conn.commit()
        conn.close()

    def read_positions(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT data FROM positions").fetchall()
        conn.close()
        return [json.loads(r[0]) for r in rows]

    def write_fill(self, data: dict):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO fills (data) VALUES (?)", (json.dumps(data),))
        conn.commit()
        conn.close()

    def read_fills(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT data FROM fills").fetchall()
        conn.close()
        return [json.loads(r[0]) for r in rows]

    def clear_all(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM fills")
        conn.commit()
        conn.close()
