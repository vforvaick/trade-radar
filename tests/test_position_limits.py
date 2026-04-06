import json
from datetime import datetime

from bot import config
from bot import main
from bot.executor import PaperExecutor
from bot.passport_runner import PassportRunner
from bot.position_manager import PositionManager
from bot.signals import Signal


def _make_signal(
    symbol: str,
    *,
    confidence: float = 70.0,
    btc_trend: str = "Sideways",
) -> Signal:
    return Signal(
        symbol=symbol,
        direction="LONG",
        entry_price=100.0,
        tp1=110.0,
        tp2=120.0,
        tp3=130.0,
        sl=95.0,
        leverage=5,
        risk_reward=1.43,
        confidence=confidence,
        btc_trend=btc_trend,
        timestamp=datetime(2026, 4, 3, 8, 0, 0),
        indicators={},
    )


def test_position_manager_enforces_passport_and_symbol_caps(monkeypatch):
    monkeypatch.setattr(config, "MAX_OPEN_POSITIONS_PER_PASSPORT", 2, raising=False)
    monkeypatch.setattr(config, "MAX_OPEN_POSITIONS_PER_SYMBOL", 1, raising=False)

    pm = PositionManager()

    assert pm.open_position(_make_signal("BTCUSDT"), equity=1000.0) is not None
    assert pm.open_position(_make_signal("ETHUSDT"), equity=1000.0) is not None

    assert pm.can_open(_make_signal("SOLUSDT")) is False
    assert pm.open_position(_make_signal("SOLUSDT"), equity=1000.0) is None

    assert pm.can_open(_make_signal("BTCUSDT")) is False
    assert pm.open_position(_make_signal("BTCUSDT"), equity=1000.0) is None

    assert pm.open_count == 2


def test_position_manager_blocks_symbol_stacking_before_global_cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_OPEN_POSITIONS_PER_PASSPORT", 10, raising=False)
    monkeypatch.setattr(config, "MAX_OPEN_POSITIONS_PER_SYMBOL", 1, raising=False)

    pm = PositionManager()

    assert pm.open_position(_make_signal("BTCUSDT"), equity=1000.0) is not None
    assert pm.can_open(_make_signal("BTCUSDT")) is False
    assert pm.open_position(_make_signal("BTCUSDT"), equity=1000.0) is None
    assert pm.can_open(_make_signal("ETHUSDT")) is True
    assert pm.open_count == 1


def test_reversal_sideways_scan_replay_is_confidence_filtered_and_capped(
    tmp_path,
    monkeypatch,
):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "reversal.json").write_text(
        json.dumps(
            {
                "name": "Pumpradar Reversal",
                "emoji": "🔄",
                "enabled": True,
                "config_overrides": {
                    "INDICATOR_WEIGHTS": {"REVERSAL_MODE": True},
                    "CONFIDENCE_THRESHOLD": 54,
                    "MAX_OPEN_POSITIONS_PER_PASSPORT": 50,
                    "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
                    "REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD": 80,
                    "REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT": 5,
                },
            }
        )
    )

    monkeypatch.setenv("CRYPTOPASS_STATE_DB", str(tmp_path / "state.db"))

    def fake_update_btc_trend(scanner):
        scanner.btc_trend = "Sideways"

    # Deterministic replay of a high-signal scan: 120 symbols with confidence
    # alternating around the stricter Sideways threshold.
    signals = [
        _make_signal(f"ALT{i:03d}USDT", confidence=90.0 if i % 2 == 0 else 70.0)
        for i in range(120)
    ]

    monkeypatch.setattr("bot.passport_runner.Scanner.update_btc_trend", fake_update_btc_trend)
    monkeypatch.setattr("bot.passport_runner.Scanner.scan_all", lambda scanner: signals)

    runner = PassportRunner(str(cfg_dir), interval="1h")
    results = runner.run_scan_cycle()

    assert len(results) == 5
    assert runner.passports[0].position_manager.open_count == 5
    assert all(item["signal"].confidence >= 80 for item in results)
    assert config.CONFIDENCE_THRESHOLD == 54


def test_run_bot_does_not_execute_duplicate_same_symbol_signals(monkeypatch, capsys):
    monkeypatch.setattr(config, "MAX_OPEN_POSITIONS_PER_PASSPORT", 10, raising=False)
    monkeypatch.setattr(config, "MAX_OPEN_POSITIONS_PER_SYMBOL", 1, raising=False)

    signals = [_make_signal("BTCUSDT"), _make_signal("BTCUSDT")]
    executed = []

    class OneCycleScanner:
        def __init__(self, interval: str = "1h", limit: int = 100):
            self.interval = interval
            self.limit = limit

        def refresh_symbols(self):
            return None

        def update_btc_trend(self):
            return None

        def scan_all(self):
            return signals

    class CapturingPaperExecutor(PaperExecutor):
        def execute_signal(self, signal, equity):
            executed.append(signal.symbol)
            return super().execute_signal(signal, equity)

    class SilentNotifier:
        def __init__(self, bot_token=None, chat_id=None):
            return None

        def send_signal(self, signal):
            return 1

        def store_signal_message_id(self, symbol, msg_id):
            return None

        def send_tp_sl_alert(self, signal, event, pnl, equity):
            return None

    monkeypatch.setattr(main, "Scanner", OneCycleScanner)
    monkeypatch.setattr(main, "PaperExecutor", CapturingPaperExecutor)
    monkeypatch.setattr(main, "TelegramNotifier", SilentNotifier)
    monkeypatch.setattr(main.time, "time", lambda: 3600)

    def stop_after_one_loop(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(main.time, "sleep", stop_after_one_loop)

    main.run_bot(mode="paper", interval="1h")

    assert executed == ["BTCUSDT"]
    output = capsys.readouterr().out
    assert "position guardrail" in output
    assert "Max positions reached" not in output
