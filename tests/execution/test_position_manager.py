"""Tests for PositionManager."""
import pytest
from datetime import datetime, timedelta


def make_signal(direction="LONG", confidence=70.0, entry=30000.0, sl=29500.0, tp=31000.0):
    return {"direction": direction, "confidence": confidence,
            "entry_price": entry, "stop_loss": sl, "take_profit": tp}


def test_signal_to_intent():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=60)
    intent = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert intent is not None
    assert intent.direction == "LONG"
    assert intent.size_hint == 0.02


def test_cooldown_blocks():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=60)
    pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    blocked = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert blocked is None


def test_cooldown_expires():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=60)
    pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    pm._cooldowns["psp_abc:BTCUSDT"] = datetime.now() - timedelta(minutes=61)
    intent = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert intent is not None


def test_no_pyramiding_by_default():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=0, max_pyramiding=1)
    pm._open_positions["psp_abc:BTCUSDT"] = 1
    intent = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert intent is None


def test_missing_direction_returns_none():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02)
    assert pm.signal_to_intent("psp_abc", "BTCUSDT", {"confidence": 80}) is None


def test_low_confidence_rejected():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, min_confidence=60)
    sig = make_signal(confidence=50.0)
    assert pm.signal_to_intent("psp_abc", "BTCUSDT", sig) is None
