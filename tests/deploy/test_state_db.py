"""Tests for StateDB."""
import os
import tempfile
import pytest


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as d:
        from bot.deploy.state_db import StateDB
        sdb = StateDB(os.path.join(d, "test_state.db"))
        yield sdb
        sdb.close()


def test_upsert_and_get(db):
    db.upsert_passport("psp_og_v01", "paper_live", version="v0.1",
                        family="ema_crossover", config={"pairs": ["BTCUSDT"]})
    p = db.get_passport("psp_og_v01")
    assert p is not None
    assert p["status"] == "paper_live"
    assert p["config"]["pairs"] == ["BTCUSDT"]


def test_list_by_status(db):
    db.upsert_passport("psp_a", "paper_live")
    db.upsert_passport("psp_b", "production")
    db.upsert_passport("psp_c", "paper_live")
    result = db.list_passports(status="paper_live")
    assert len(result) == 2


def test_list_passports_deserializes_json(db):
    db.upsert_passport("psp_x", "paper_live", config={"pairs": ["BTCUSDT"]},
                        metrics={"sharpe": 1.2})
    results = db.list_passports()
    assert isinstance(results[0]["config"], dict)
    assert results[0]["config"]["pairs"] == ["BTCUSDT"]
    assert isinstance(results[0]["metrics"], dict)


def test_trade_logging(db):
    db.log_trade("psp_a", "BTCUSDT", "LONG", entry_price=30000.0,
                 exit_price=31000.0, pnl=3.33)
    trades = db.get_trades(passport_id="psp_a")
    assert len(trades) == 1
    assert trades[0]["pnl"] == 3.33


def test_namespace_filtering(db):
    db.log_trade("psp_a", "BTCUSDT", "LONG", 30000, namespace="paper")
    db.log_trade("psp_a", "BTCUSDT", "LONG", 30000, namespace="prod")
    assert len(db.get_trades(namespace="paper")) == 1
    assert len(db.get_trades(namespace="prod")) == 1


def test_system_events(db):
    db.log_event("promotion", {"passport_id": "psp_a", "from": "paper", "to": "prod"})
    # Verify it doesn't crash (events are write-only for now)
    assert True
