# tests/test_daily_report.py
"""Tests for daily Telegram performance report."""
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from bot.reporting.daily_report import DailyReportBuilder


@pytest.fixture
def mock_state_db(tmp_path):
    db_path = str(tmp_path / "state.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE equity_snapshots (
            id INTEGER PRIMARY KEY, passport_name TEXT,
            equity REAL, timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY, passport_name TEXT, symbol TEXT,
            signal_json TEXT, status TEXT, risk_amount REAL,
            equity_at_entry REAL, tp1_hit INTEGER DEFAULT 0,
            tp2_hit INTEGER DEFAULT 0, tp3_hit INTEGER DEFAULT 0,
            sl_is_breakeven INTEGER DEFAULT 0, realized_pnl REAL DEFAULT 0,
            trailing_sl REAL, tg_msg_id TEXT, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY, passport_name TEXT,
            trade_data_json TEXT, timestamp TEXT
        )
    """)
    now = datetime.now(timezone.utc).isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn.executemany(
        "INSERT INTO equity_snapshots (passport_name, equity, timestamp) VALUES (?, ?, ?)",
        [
            ("PassportA", 520.0, now),
            ("PassportA", 500.0, yesterday),
            ("PassportB", 480.0, now),
            ("PassportB", 500.0, yesterday),
        ],
    )
    conn.executemany(
        "INSERT INTO positions (passport_name, symbol, status, realized_pnl, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            ("PassportA", "BTCUSDT", "TP1", 15.0, now),
            ("PassportA", "ETHUSDT", "SL_HIT", -8.0, now),
            ("PassportB", "SOLUSDT", "OPEN", 0.0, now),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


class TestDailyReportBuilder:
    def test_build_report_text(self, mock_state_db):
        builder = DailyReportBuilder(state_db_path=mock_state_db, initial_equity=500.0)
        report = builder.build()
        assert "PassportA" in report
        assert "PassportB" in report
        assert "Daily Report" in report

    def test_passport_pnl_calculated(self, mock_state_db):
        builder = DailyReportBuilder(state_db_path=mock_state_db, initial_equity=500.0)
        data = builder.get_passport_summaries()
        assert len(data) == 2
        a_data = next(d for d in data if d["name"] == "PassportA")
        assert a_data["current_equity"] == 520.0
        assert a_data["pnl_pct"] == pytest.approx(4.0, rel=0.1)

    def test_empty_db(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE equity_snapshots (id INTEGER PRIMARY KEY, passport_name TEXT, equity REAL, timestamp TEXT)"
        )
        conn.execute(
            "CREATE TABLE positions (id INTEGER PRIMARY KEY, passport_name TEXT, symbol TEXT, status TEXT, realized_pnl REAL, created_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE trade_log (id INTEGER PRIMARY KEY, passport_name TEXT, trade_data_json TEXT, timestamp TEXT)"
        )
        conn.commit()
        conn.close()
        builder = DailyReportBuilder(state_db_path=db_path, initial_equity=500.0)
        report = builder.build()
        assert "No passport data" in report or "Daily Report" in report

    def test_report_sorted_by_pnl(self, mock_state_db):
        builder = DailyReportBuilder(state_db_path=mock_state_db, initial_equity=500.0)
        data = builder.get_passport_summaries()
        # PassportA (+4%) should come before PassportB (-4%)
        assert data[0]["name"] == "PassportA"
        assert data[1]["name"] == "PassportB"
