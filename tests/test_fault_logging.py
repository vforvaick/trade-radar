from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime

import pandas as pd
import pytest

from bot.notifier import TelegramCommandPoller, TelegramNotifier
from bot.passport_runner import PassportRunner
from bot.scanner import Scanner
from bot.signals import Signal
from bot.state_store import StateStore
import bot.data_fetcher as data_fetcher


def _signal(symbol: str = "BTCUSDT") -> Signal:
    return Signal(
        symbol=symbol,
        direction="LONG",
        entry_price=100.0,
        tp1=110.0,
        tp2=120.0,
        tp3=130.0,
        sl=95.0,
        leverage=5,
        confidence=75.0,
        risk_reward=2.0,
        indicators={},
        btc_trend="Uptrend",
        timestamp=datetime(2026, 4, 3, 8, 0, 0),
    )


def _klines(rows: int = 61) -> pd.DataFrame:
    ts = pd.date_range("2026-04-03 00:00:00", periods=rows, freq="min")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.0] * rows,
            "volume": [1000.0] * rows,
        }
    )


def test_scan_all_logs_symbol_failures_and_continues(monkeypatch, caplog):
    scanner = Scanner(interval="1h", limit=100)
    scanner.symbols = ["BROKENUSDT", "HEALTHYUSDT"]

    def fake_fetch(symbol, interval, limit, use_cache):
        if symbol == "BROKENUSDT":
            raise RuntimeError("boom-fetch")
        return _klines()

    monkeypatch.setattr("bot.scanner.fetch_klines", fake_fetch)
    monkeypatch.setattr(
        "bot.scanner.score_confluence",
        lambda _klines_df, _btc_trend: {
            "go": True,
            "direction": "LONG",
            "risk_reward": 2.0,
            "leverage": 5,
            "confidence": 77.0,
            "btc_trend": "Uptrend",
            "signals": {},
        },
    )
    monkeypatch.setattr(
        "bot.scanner.generate_signal",
        lambda sym, _close, _result, timestamp=None: _signal(sym),
    )
    monkeypatch.setattr("bot.scanner.time.sleep", lambda _seconds: None)

    caplog.set_level(logging.WARNING)

    signals = scanner.scan_all()

    assert [signal.symbol for signal in signals] == ["HEALTHYUSDT"]
    assert getattr(scanner, "scan_error_count", 0) == 1
    assert "BROKENUSDT" in caplog.text
    assert "boom-fetch" in caplog.text


def test_command_poller_logs_send_failures_and_status_reports_state(
    tmp_path,
    monkeypatch,
    caplog,
):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "og.json").write_text(
        json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "enabled": True, "config_overrides": {}})
    )
    (cfg_dir / "reversal.json").write_text(
        json.dumps(
            {
                "name": "Pumpradar Reversal",
                "emoji": "🔄",
                "enabled": False,
                "config_overrides": {},
            }
        )
    )

    db_path = tmp_path / "state.db"
    store = StateStore(db_path=str(db_path))
    store.save_position("Pumpradar Reversal", _signal("ETHUSDT"), 1000.0, 25.0, tg_msg_id=777)

    monkeypatch.setenv("CRYPTOPASS_STATE_DB", str(db_path))
    runner = PassportRunner(str(cfg_dir), interval="1h")
    notifier = TelegramNotifier(bot_token="token", chat_id="123")
    poller = TelegramCommandPoller(notifier, runner)

    updates = {
        "ok": True,
        "result": [
            {
                "update_id": 1,
                "message": {"text": "/ping", "chat": {"id": 123}, "date": 101},
            },
            {
                "update_id": 2,
                "message": {"text": "/status", "chat": {"id": 123}, "date": 102},
            },
        ],
    }
    sent_payloads: list[dict] = []

    def fake_get(_url, params, timeout):
        return type("Response", (), {"json": lambda self: updates})()

    def fake_post(_url, json, timeout):
        if len(sent_payloads) == 0:
            sent_payloads.append(json)
            raise RuntimeError("telegram-send-failed")
        sent_payloads.append(json)
        return type(
            "Response",
            (),
            {"json": lambda self: {"ok": True, "result": {"message_id": 99}}},
        )()

    def stop_loop(_seconds):
        raise StopIteration

    monkeypatch.setattr("bot.notifier.requests.get", fake_get)
    monkeypatch.setattr("bot.notifier.requests.post", fake_post)
    monkeypatch.setattr("bot.notifier.time.time", lambda: 100)
    monkeypatch.setattr("bot.notifier.time.sleep", stop_loop)

    caplog.set_level(logging.WARNING)

    with pytest.raises(StopIteration):
        poller._poll_loop()

    assert getattr(notifier, "send_error_count", 0) == 1
    assert "telegram-send-failed" in caplog.text
    assert sent_payloads[-1]["text"].startswith("🟢 **Bot Status**")
    assert str(db_path) in sent_payloads[-1]["text"]
    assert "🏆 Pumpradar OG: enabled | Open=0" in sent_payloads[-1]["text"]
    assert "🔄 Pumpradar Reversal: disabled | Open=1" in sent_payloads[-1]["text"]


def test_tp_sl_send_failures_log_symbol_and_passport_context(monkeypatch, caplog):
    notifier = TelegramNotifier(bot_token="token", chat_id="123")
    signal = _signal("BTCUSDT")

    def fail_post(_url, json, timeout):
        raise RuntimeError("tp-sl-send-failed")

    monkeypatch.setattr("bot.notifier.requests.post", fail_post)
    caplog.set_level(logging.WARNING)

    notifier.send_tp_sl_alert(
        signal,
        "SL_HIT",
        realized_pnl=-25.0,
        equity=975.0,
        passport_name="Pumpradar OG",
    )

    assert notifier.send_error_count == 1
    assert "tp-sl-send-failed" in caplog.text
    assert "BTCUSDT" in caplog.text
    assert "Pumpradar OG" in caplog.text
    assert "SL_HIT" in caplog.text


def test_binance_requests_verify_tls_by_default_and_allow_explicit_escape_hatch(monkeypatch):
    monkeypatch.delenv("CRYPTOPASS_BINANCE_VERIFY_TLS", raising=False)

    request_kwargs = []

    def fake_get(_url, **kwargs):
        request_kwargs.append(kwargs)
        return type(
            "Response",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: [
                    {"symbol": "BTCUSDT", "quoteVolume": "999999999"},
                ],
            },
        )()

    monkeypatch.setattr(data_fetcher.requests, "get", fake_get)

    assert data_fetcher.get_all_futures_symbols(min_volume=0) == ["BTCUSDT"]
    assert request_kwargs[-1]["verify"] is True

    monkeypatch.setenv("CRYPTOPASS_BINANCE_VERIFY_TLS", "false")

    assert data_fetcher.get_all_futures_symbols(min_volume=0) == ["BTCUSDT"]
    assert request_kwargs[-1]["verify"] is False


def test_restore_skips_corrupt_position_rows_and_keeps_valid_rows(tmp_path, monkeypatch, caplog):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "og.json").write_text(
        json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "config_overrides": {}})
    )

    db_path = tmp_path / "state.db"
    store = StateStore(db_path=str(db_path))
    store.save_position("Pumpradar OG", _signal("BTCUSDT"), 1000.0, 30.0)
    bad_pos_id = store.save_position("Pumpradar OG", _signal("ETHUSDT"), 1000.0, 30.0)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE positions SET signal_json = ? WHERE id = ?",
            ("{bad-json", bad_pos_id),
        )
        conn.commit()

    monkeypatch.setenv("CRYPTOPASS_STATE_DB", str(db_path))
    caplog.set_level(logging.WARNING)

    runner = PassportRunner(str(cfg_dir), interval="1h")

    passport = runner.passports[0]
    assert [pos.signal.symbol for pos in passport.position_manager.positions] == ["BTCUSDT"]
    assert runner.state_restore_error_count == 1
    assert "Pumpradar OG" in caplog.text
    assert "ETHUSDT" in caplog.text
    assert "Failed to restore open position" in caplog.text


def test_restore_skips_rows_with_malformed_signal_timestamp(tmp_path, monkeypatch, caplog):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "og.json").write_text(
        json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "config_overrides": {}})
    )

    db_path = tmp_path / "state.db"
    store = StateStore(db_path=str(db_path))
    store.save_position("Pumpradar OG", _signal("BTCUSDT"), 1000.0, 30.0)
    bad_pos_id = store.save_position("Pumpradar OG", _signal("ETHUSDT"), 1000.0, 30.0)
    malformed_signal = _signal("ETHUSDT").__dict__.copy()
    malformed_signal["timestamp"] = "not-a-valid-iso-timestamp"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE positions SET signal_json = ? WHERE id = ?",
            (json.dumps(malformed_signal), bad_pos_id),
        )
        conn.commit()

    monkeypatch.setenv("CRYPTOPASS_STATE_DB", str(db_path))
    caplog.set_level(logging.WARNING)

    runner = PassportRunner(str(cfg_dir), interval="1h")

    passport = runner.passports[0]
    assert [pos.signal.symbol for pos in passport.position_manager.positions] == ["BTCUSDT"]
    assert runner.state_restore_error_count == 1
    assert "Failed to parse restored timestamp" in caplog.text
    assert "ETHUSDT" in caplog.text


def test_restore_skips_rows_with_non_string_timestamp_and_prints_actual_open_count(
    tmp_path,
    monkeypatch,
    caplog,
    capsys,
):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "og.json").write_text(
        json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "config_overrides": {}})
    )

    db_path = tmp_path / "state.db"
    store = StateStore(db_path=str(db_path))
    store.save_position("Pumpradar OG", _signal("BTCUSDT"), 1000.0, 30.0)
    bad_pos_id = store.save_position("Pumpradar OG", _signal("ETHUSDT"), 1000.0, 30.0)
    malformed_signal = _signal("ETHUSDT").__dict__.copy()
    malformed_signal["timestamp"] = 12345
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE positions SET signal_json = ? WHERE id = ?",
            (json.dumps(malformed_signal), bad_pos_id),
        )
        conn.commit()

    monkeypatch.setenv("CRYPTOPASS_STATE_DB", str(db_path))
    caplog.set_level(logging.WARNING)

    runner = PassportRunner(str(cfg_dir), interval="1h")

    passport = runner.passports[0]
    assert [pos.signal.symbol for pos in passport.position_manager.positions] == ["BTCUSDT"]
    assert isinstance(passport.position_manager.positions[0].signal.timestamp, datetime)
    assert runner.state_restore_error_count == 1
    assert "ETHUSDT" in caplog.text
    assert "Failed to restore open position" in caplog.text

    startup_output = capsys.readouterr().out
    assert "Open Pos: 1" in startup_output
    assert "Open Pos: 2" not in startup_output


def test_send_with_context_supports_legacy_text_only_send_override():
    class LegacyNotifier(TelegramNotifier):
        def __init__(self):
            super().__init__(bot_token="token", chat_id="123")
            self.calls = []

        def _send(self, text):
            self.calls.append(text)
            return 321

    notifier = LegacyNotifier()

    assert notifier.send_signal(_signal("BTCUSDT")) == 321
    notifier.send_tp_sl_alert(
        _signal("BTCUSDT"),
        "TP1_HIT",
        realized_pnl=12.0,
        equity=1012.0,
        passport_name="Pumpradar OG",
    )

    assert len(notifier.calls) == 2
