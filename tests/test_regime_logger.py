# tests/test_regime_logger.py
"""Tests for RegimeLogger — SQLite data collection and daily digest."""
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from bot.state_store import StateStore


@pytest.fixture
def state_store():
    """Create a fresh StateStore with temp database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = StateStore(db_path=db_path)
    yield store
    os.unlink(db_path)


class TestRegimeLoggerSchema:
    """Table creation tests."""

    def test_creates_regime_snapshots_table(self, state_store):
        from bot.regime_logger import RegimeLogger
        logger = RegimeLogger(state_store)

        with sqlite3.connect(state_store.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        table_names = {t[0] for t in tables}
        assert "regime_snapshots" in table_names

    def test_creates_signal_regime_log_table(self, state_store):
        from bot.regime_logger import RegimeLogger
        logger = RegimeLogger(state_store)

        with sqlite3.connect(state_store.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        table_names = {t[0] for t in tables}
        assert "signal_regime_log" in table_names


class TestRegimeLoggerLogScan:
    """Per-scan logging tests."""

    def test_log_scan_inserts_row(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        metadata = {
            "regime": "TREND_UP",
            "btc_price": 87000.0,
            "adx": 30.5,
            "ret_30d": 12.3,
            "realized_vol": 0.45,
            "ema9_1h": 87100.0,
            "ema21_1h": 86900.0,
            "confirmation_matched": True,
        }
        rl.log_scan("TREND_UP", metadata, total_signals=15, total_opened=3)

        with sqlite3.connect(state_store.db_path) as conn:
            rows = conn.execute("SELECT * FROM regime_snapshots").fetchall()
        assert len(rows) == 1

    def test_log_scan_stores_correct_values(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        metadata = {
            "regime": "HIGH_VOL_CHOP",
            "btc_price": 85000.0,
            "adx": 18.0,
            "ret_30d": -2.1,
            "realized_vol": 0.55,
            "ema9_1h": 84900.0,
            "ema21_1h": 85100.0,
            "confirmation_matched": False,
        }
        rl.log_scan("HIGH_VOL_CHOP", metadata, total_signals=5, total_opened=1)

        with sqlite3.connect(state_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM regime_snapshots").fetchone())
        assert row["regime"] == "HIGH_VOL_CHOP"
        assert row["btc_price"] == 85000.0
        assert row["adx"] == 18.0
        assert row["total_signals"] == 5
        assert row["total_opened"] == 1


class TestRegimeLoggerLogSignal:
    """Per-signal logging tests."""

    def test_log_signal_inserts_row(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.log_signal(
            regime="TREND_UP",
            passport_name="HiddenGem",
            symbol="ETHUSDT",
            direction="LONG",
            confidence_raw=78.5,
            confidence_adjusted=62.8,
            btc_weight=0.8,
            was_executed=True,
        )

        with sqlite3.connect(state_store.db_path) as conn:
            rows = conn.execute("SELECT * FROM signal_regime_log").fetchall()
        assert len(rows) == 1

    def test_log_signal_with_skip_reason(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.log_signal(
            regime="TREND_DOWN",
            passport_name="Sniper",
            symbol="BTCUSDT",
            direction="SHORT",
            confidence_raw=55.0,
            confidence_adjusted=55.0,
            btc_weight=1.0,
            was_executed=False,
            skip_reason="DIRECTION_BIAS=LONG_ONLY",
        )

        with sqlite3.connect(state_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM signal_regime_log").fetchone())
        assert row["was_executed"] == 0
        assert row["skip_reason"] == "DIRECTION_BIAS=LONG_ONLY"


class TestRegimeLoggerTradeTagging:
    """Trade regime tagging tests."""

    def test_tag_trade_open(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.tag_trade_regime("open", 42, "TREND_UP")

        with sqlite3.connect(state_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trade_regime_tags").fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["trade_id"] == 42
        assert row["event"] == "open"
        assert row["regime"] == "TREND_UP"

    def test_tag_trade_close(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.tag_trade_regime("open", 42, "TREND_UP")
        rl.tag_trade_regime("close", 42, "HIGH_VOL_CHOP")

        with sqlite3.connect(state_store.db_path) as conn:
            rows = conn.execute("SELECT * FROM trade_regime_tags").fetchall()
        assert len(rows) == 2


class TestRegimeLoggerDailyDigest:
    """Daily digest generation tests."""

    def test_generate_daily_digest_returns_string(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        # Insert some test data
        rl.log_scan("TREND_UP", {
            "regime": "TREND_UP", "btc_price": 87000.0, "adx": 30.0,
            "ret_30d": 12.0, "realized_vol": 0.45, "ema9_1h": 87100.0,
            "ema21_1h": 86900.0, "confirmation_matched": True,
        }, total_signals=10, total_opened=2)

        digest = rl.generate_daily_digest()
        assert isinstance(digest, str)
        assert "Cryptopass" in digest or "Regime" in digest

    def test_generate_daily_digest_empty_data(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        digest = rl.generate_daily_digest()
        assert isinstance(digest, str)
        assert len(digest) > 0
