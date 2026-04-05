"""Tests for execution types."""
import pytest
from datetime import datetime


def test_order_intent_creation():
    from bot.execution.types import OrderIntent
    oi = OrderIntent(
        passport_id="psp_abc", symbol="BTCUSDT", direction="LONG",
        signal_confidence=72.5, size_hint=0.02, stop_loss=29500.0,
        take_profit=31000.0, entry_price=30000.0, cooldown_key="psp_abc:BTCUSDT",
        metadata={"family": "ema_crossover"},
    )
    assert oi.direction == "LONG"
    assert oi.signal_confidence == 72.5


def test_order_intent_validates_direction():
    from bot.execution.types import OrderIntent
    with pytest.raises(ValueError):
        OrderIntent(passport_id="x", symbol="X", direction="INVALID",
                    signal_confidence=50, size_hint=0.01,
                    stop_loss=0, take_profit=0, entry_price=0,
                    cooldown_key="x", metadata={})


def test_fill_creation():
    from bot.execution.types import Fill
    f = Fill(order_intent_id="oi_1", fill_price=30050.0, fill_size=0.02,
             slippage_bps=1.67, fee_bps=4.0, timestamp=datetime.now(),
             is_paper=True)
    assert f.is_paper is True


def test_position_record():
    from bot.execution.types import PositionRecord
    p = PositionRecord(
        position_id="pos_1", passport_id="psp_abc", symbol="BTCUSDT",
        direction="LONG", entry_price=30000.0, current_price=30500.0,
        size=0.02, unrealized_pnl=10.0, stop_loss=29500.0,
        take_profit=31000.0, namespace="paper",
        opened_at=datetime.now(), status="open",
    )
    assert p.namespace == "paper"
    assert p.status == "open"
