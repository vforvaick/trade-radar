from __future__ import annotations

import pytest

from bot.notifier import TelegramNotifier
from bot.signals import Signal


class MockNotifier(TelegramNotifier):
    def __init__(self) -> None:
        super().__init__(bot_token="fake", chat_id="fake")
        self.calls: list[tuple[str, int | None]] = []

    def _send(self, text: str, reply_to_message_id: int | None = None):
        self.calls.append((text, reply_to_message_id))
        return 123


@pytest.fixture()
def signal() -> Signal:
    return Signal(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=50000.0,
        tp1=52000.0,
        tp2=54000.0,
        tp3=56000.0,
        sl=49000.0,
        leverage=7,
        risk_reward=2.08,
        confidence=75.0,
        btc_trend="Uptrend",
    )


@pytest.mark.parametrize(
    ("event", "realized_pnl", "equity", "expected_fragment"),
    [
        ("TP1_HIT", 350.0, 1350.0, "Closed: 70% of position"),
        ("SL_BREAKEVEN", 0.0, 1350.0, "Hit Price: `50000` (Breakeven)"),
        ("TP3_HIT", 50.0, 1400.0, "Closed: 10% of position (All targets hit!)"),
        ("SL_HIT", -150.0, 850.0, "Loss: -2.00%"),
    ],
)
def test_send_tp_sl_alert_formats_message_and_threads_reply(signal, event, realized_pnl, equity, expected_fragment):
    notifier = MockNotifier()
    notifier.store_signal_message_id(signal.symbol, 77, passport_name="📊 [Aggressive]")

    notifier.send_tp_sl_alert(
        signal,
        event,
        realized_pnl=realized_pnl,
        equity=equity,
        passport_name="📊 [Aggressive]",
    )

    assert len(notifier.calls) == 1
    message, reply_to = notifier.calls[0]
    assert reply_to == 77
    assert "📊 [Aggressive]" in message
    assert f"**{event.replace('_', ' ')}** — #{signal.symbol}" in message
    assert expected_fragment in message


def test_store_signal_message_id_uses_symbol_and_passport_name(signal):
    notifier = MockNotifier()

    notifier.store_signal_message_id(signal.symbol, 88, passport_name="🛡️ [Conservative]")

    assert notifier.signal_message_ids[(signal.symbol, "🛡️ [Conservative]")] == 88
