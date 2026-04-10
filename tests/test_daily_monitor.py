"""
Tests for scripts/daily_monitor.py (no SSH, no VPS dependency).
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

# ── load the module without relying on package imports ──────────────────────
_SCRIPT = Path(__file__).parent.parent / "scripts" / "daily_monitor.py"
_spec = importlib.util.spec_from_file_location("daily_monitor", _SCRIPT)
dm = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(dm)  # type: ignore[union-attr]


# ─────────────────────────────── helpers ────────────────────────────────────

def _make_db(tmp_path: Path, rows: list[dict]) -> Path:
    """Create a minimal in-memory-style SQLite DB with test data."""
    db_path = tmp_path / "test_state.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passport_name TEXT,
            timestamp TEXT,
            trade_data_json TEXT
        );
        CREATE TABLE equity_snapshots_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passport_name TEXT,
            timestamp TEXT,
            realized_equity REAL,
            unrealized_pnl REAL,
            total_equity REAL,
            open_positions INTEGER
        );
        """
    )
    for r in rows:
        conn.execute(
            "INSERT INTO trade_log (passport_name, timestamp, trade_data_json) VALUES (?,?,?)",
            (r["passport_name"], r.get("timestamp", "2026-04-10T10:00:00"),
             json.dumps(r.get("data", {}))),
        )
    conn.commit()
    conn.close()
    return db_path


# ─────────────────────────────── PnL calculation tests ──────────────────────


def test_compute_passport_stats_basic():
    trades = [
        {"passport_name": "Alpha", "realized_pnl": 20.0, "direction": "LONG",  "timestamp": "2026-04-10"},
        {"passport_name": "Alpha", "realized_pnl": -5.0, "direction": "SHORT", "timestamp": "2026-04-10"},
        {"passport_name": "Beta",  "realized_pnl": 10.0, "direction": "LONG",  "timestamp": "2026-04-10"},
    ]
    stats = dm.compute_passport_stats(trades)

    assert round(stats["Alpha"]["pnl"], 2) == 15.0
    assert stats["Alpha"]["wins"] == 1
    assert stats["Alpha"]["losses"] == 1
    assert round(stats["Alpha"]["gross_profit"], 2) == 20.0
    assert round(stats["Alpha"]["gross_loss"], 2) == 5.0

    assert round(stats["Beta"]["pnl"], 2) == 10.0
    assert stats["Beta"]["wins"] == 1
    assert stats["Beta"]["losses"] == 0


def test_compute_passport_stats_direction_split():
    trades = [
        {"passport_name": "X", "realized_pnl": 15.0,  "direction": "LONG",  "timestamp": "2026-04-10"},
        {"passport_name": "X", "realized_pnl": -8.0,  "direction": "SHORT", "timestamp": "2026-04-10"},
        {"passport_name": "X", "realized_pnl": 5.0,   "direction": "SHORT", "timestamp": "2026-04-10"},
    ]
    stats = dm.compute_passport_stats(trades)
    s = stats["X"]

    assert s["long_trades"] == 1
    assert s["short_trades"] == 2
    assert round(s["long_pnl"], 2) == 15.0
    assert round(s["short_pnl"], 2) == -3.0
    assert s["long_wins"] == 1
    assert s["short_wins"] == 1


def test_compute_passport_stats_ctp_split():
    trades = [
        {"passport_name": "A", "realized_pnl": 10.0, "direction": "LONG", "timestamp": "2026-04-08"},
        {"passport_name": "A", "realized_pnl": -3.0, "direction": "LONG", "timestamp": "2026-04-09"},
        {"passport_name": "A", "realized_pnl": 7.0,  "direction": "LONG", "timestamp": "2026-04-11"},
    ]
    stats = dm.compute_passport_stats(trades)
    s = stats["A"]

    assert round(s["pre_ctp_pnl"], 2) == 10.0   # only Apr 8 is before Apr 9
    assert round(s["post_ctp_pnl"], 2) == 4.0   # Apr 9 + Apr 11


def test_compute_passport_stats_empty():
    stats = dm.compute_passport_stats([])
    assert stats == {}


def test_compute_portfolio_direction_stats():
    trades = [
        {"passport_name": "A", "realized_pnl": 20.0, "direction": "LONG"},
        {"passport_name": "A", "realized_pnl": -5.0, "direction": "LONG"},
        {"passport_name": "B", "realized_pnl": 10.0, "direction": "SHORT"},
        {"passport_name": "B", "realized_pnl": -2.0, "direction": "SHORT"},
    ]
    ds = dm.compute_portfolio_direction_stats(trades)

    assert ds["long_trades"] == 2
    assert ds["short_trades"] == 2
    assert round(ds["long_pnl"], 2) == 15.0
    assert round(ds["short_pnl"], 2) == 8.0
    assert ds["long_wins"] == 1
    assert ds["short_wins"] == 1


def test_missing_direction_is_ignored():
    trades = [
        {"passport_name": "A", "realized_pnl": 10.0, "direction": None},
        {"passport_name": "A", "realized_pnl": 10.0, "direction": ""},
    ]
    ds = dm.compute_portfolio_direction_stats(trades)
    assert ds["long_trades"] == 0
    assert ds["short_trades"] == 0


# ─────────────────────────────── formatting tests ───────────────────────────


def test_win_rate_zero_trades():
    assert dm._win_rate(0, 0) == 0.0


def test_win_rate_all_wins():
    assert dm._win_rate(5, 5) == 100.0


def test_profit_factor_no_losses():
    assert dm._profit_factor(50.0, 0.0) == float("inf")


def test_profit_factor_no_trades():
    assert dm._profit_factor(0.0, 0.0) == 0.0


def test_profit_factor_normal():
    assert round(dm._profit_factor(60.0, 40.0), 2) == 1.50


def test_pf_str_infinity():
    assert dm._pf_str(float("inf")) == "∞"


def test_pf_str_normal():
    assert dm._pf_str(1.50) == "1.50"


def test_fmt_pnl_positive_contains_plus():
    result = dm._fmt_pnl(42.0)
    # strip ANSI
    plain = result.replace(dm.GREEN, "").replace(dm.RESET, "").replace(dm.RED, "")
    assert plain.startswith("+")
    assert "42.00" in plain


def test_fmt_pnl_negative_no_plus():
    result = dm._fmt_pnl(-10.0)
    plain = result.replace(dm.GREEN, "").replace(dm.RESET, "").replace(dm.RED, "")
    assert "+" not in plain
    assert "10.00" in plain


# ─────────────────────────────── DB loading tests ───────────────────────────


def test_load_trade_log_parses_json(tmp_path):
    rows = [
        {
            "passport_name": "HiddenGem",
            "data": {"realized_pnl": 12.5, "event": "TP1_HIT", "direction": "LONG"},
        }
    ]
    db_path = _make_db(tmp_path, rows)
    conn = sqlite3.connect(str(db_path))
    trades = dm.load_trade_log(conn)
    conn.close()

    assert len(trades) == 1
    t = trades[0]
    assert t["passport_name"] == "HiddenGem"
    assert t["realized_pnl"] == 12.5
    assert t["direction"] == "LONG"


def test_load_trade_log_handles_bad_json(tmp_path):
    db_path = tmp_path / "bad.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE trade_log (id INTEGER PRIMARY KEY, passport_name TEXT,
            timestamp TEXT, trade_data_json TEXT);
        CREATE TABLE equity_snapshots_v2 (id INTEGER PRIMARY KEY, passport_name TEXT,
            timestamp TEXT, realized_equity REAL, unrealized_pnl REAL,
            total_equity REAL, open_positions INTEGER);
        """
    )
    conn.execute(
        "INSERT INTO trade_log VALUES (1,'X','2026-04-10','NOT_JSON')"
    )
    conn.commit()
    trades = dm.load_trade_log(conn)
    conn.close()
    # Should not raise; bad JSON becomes empty dict (only passport_name + timestamp added)
    assert trades[0]["passport_name"] == "X"
    assert "realized_pnl" not in trades[0]


def test_load_latest_snapshots(tmp_path):
    db_path = tmp_path / "snap.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE trade_log (id INTEGER PRIMARY KEY, passport_name TEXT,
            timestamp TEXT, trade_data_json TEXT);
        CREATE TABLE equity_snapshots_v2 (id INTEGER PRIMARY KEY, passport_name TEXT,
            timestamp TEXT, realized_equity REAL, unrealized_pnl REAL,
            total_equity REAL, open_positions INTEGER);
        """
    )
    conn.execute(
        "INSERT INTO equity_snapshots_v2 VALUES (1,'A','2026-04-09',510,5,515,3)"
    )
    conn.execute(
        "INSERT INTO equity_snapshots_v2 VALUES (2,'A','2026-04-10',520,10,530,5)"
    )
    conn.commit()
    snaps = dm.load_latest_snapshots(conn)
    conn.close()

    assert "A" in snaps
    assert snaps["A"]["total_equity"] == 530.0
    assert snaps["A"]["open_positions"] == 5


def test_check_schema_raises_on_missing_tables(tmp_path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE trade_log (id INTEGER PRIMARY KEY)")
    conn.commit()
    with pytest.raises(RuntimeError, match="Missing tables"):
        dm._check_schema(conn)
    conn.close()


def test_check_schema_passes_with_both_tables(tmp_path):
    db_path = tmp_path / "ok.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE trade_log (id INTEGER PRIMARY KEY, passport_name TEXT,
            timestamp TEXT, trade_data_json TEXT);
        CREATE TABLE equity_snapshots_v2 (id INTEGER PRIMARY KEY, passport_name TEXT,
            timestamp TEXT, realized_equity REAL, unrealized_pnl REAL,
            total_equity REAL, open_positions INTEGER);
        """
    )
    conn.commit()
    dm._check_schema(conn)  # should not raise
    conn.close()
