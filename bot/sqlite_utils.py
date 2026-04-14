from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


SQLITE_BUSY_TIMEOUT_MS = 30000


def connect_sqlite(db_path: str, *, readonly: bool = False) -> sqlite3.Connection:
    resolved = os.path.abspath(db_path)
    timeout = SQLITE_BUSY_TIMEOUT_MS / 1000

    if readonly:
        conn = sqlite3.connect(
            f"file:{resolved}?mode=ro",
            uri=True,
            timeout=timeout,
        )
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA query_only=ON")
        return conn

    conn = sqlite3.connect(resolved, timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def sqlite_connection(db_path: str, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    conn = connect_sqlite(db_path, readonly=readonly)
    try:
        yield conn
        if not readonly and conn.in_transaction:
            conn.commit()
    except Exception:
        if not readonly and conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
