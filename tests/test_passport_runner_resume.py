import json
from datetime import datetime

import numpy as np

from bot.notifier import TelegramNotifier
from bot.passport_runner import PassportRunner
from bot.signals import Signal
from bot.state_store import StateStore


def test_runner_restores_equity_open_positions_and_message_ids(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "og.json").write_text(
        json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "config_overrides": {}})
    )
    (cfg_dir / "reversal.json").write_text(
        json.dumps({"name": "Pumpradar Reversal", "emoji": "🔄", "enabled": False, "config_overrides": {}})
    )

    db_path = tmp_path / "state.db"
    store = StateStore(db_path=str(db_path))
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=100.0,
        tp1=110.0,
        tp2=120.0,
        tp3=130.0,
        sl=95.0,
        leverage=5,
        confidence=70.0,
        risk_reward=1.43,
        indicators={"volume_spike": {"spike": np.bool_(True), "ratio": np.float64(2.0)}},
        btc_trend="Sideways",
        timestamp=datetime(2026, 4, 3, 8, 0, 0),
    )
    pos_id = store.save_position("Pumpradar OG", signal, 1234.0, 37.02, tg_msg_id=77)
    store.save_equity("Pumpradar OG", 1234.0)

    monkeypatch.setenv("PUMPRADAR_STATE_DB", str(db_path))
    runner = PassportRunner(str(cfg_dir), interval="1h")

    assert [passport.name for passport in runner.passports] == ["Pumpradar OG"]
    passport = runner.passports[0]
    assert passport.equity == 1234.0
    assert passport.position_manager.open_count == 1
    restored_position = passport.position_manager.positions[0]
    assert restored_position.pos_id == pos_id
    assert restored_position.signal.timestamp == datetime(2026, 4, 3, 8, 0, 0)

    notifier = TelegramNotifier(bot_token="token", chat_id="chat")
    notifier.restore_message_ids(runner.state_store)
    assert notifier.signal_message_ids[("BTCUSDT", "Pumpradar OG")] == 77


def test_disabled_passport_with_open_positions_is_restored_but_not_scanned(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
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
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=100.0,
        tp1=110.0,
        tp2=120.0,
        tp3=130.0,
        sl=95.0,
        leverage=5,
        confidence=70.0,
        risk_reward=1.43,
        indicators={},
        btc_trend="Sideways",
        timestamp=datetime(2026, 4, 3, 8, 0, 0),
    )
    store.save_position("Pumpradar Reversal", signal, 1000.0, 30.0)
    store.save_equity("Pumpradar Reversal", 970.0)

    monkeypatch.setenv("PUMPRADAR_STATE_DB", str(db_path))
    monkeypatch.setattr("bot.passport_runner.Scanner.update_btc_trend", lambda scanner: None)

    def fail_scan(scanner):
        raise AssertionError("disabled passport should not be scanned")

    monkeypatch.setattr("bot.passport_runner.Scanner.scan_all", fail_scan)

    runner = PassportRunner(str(cfg_dir), interval="1h")

    assert [passport.name for passport in runner.passports] == ["Pumpradar Reversal"]
    passport = runner.passports[0]
    assert passport.position_manager.open_count == 1
    assert passport.equity == 970.0

    assert runner.run_scan_cycle() == []
    assert passport.position_manager.open_count == 1


def test_runner_restores_zero_equity_snapshot(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "og.json").write_text(
        json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "config_overrides": {}})
    )

    db_path = tmp_path / "state.db"
    store = StateStore(db_path=str(db_path))
    store.save_equity("Pumpradar OG", 0.0)

    monkeypatch.setenv("PUMPRADAR_STATE_DB", str(db_path))
    runner = PassportRunner(str(cfg_dir), interval="1h")

    assert runner.passports[0].equity == 0.0


def test_update_all_positions_logs_fetch_exception_details(tmp_path, monkeypatch, capsys):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "og.json").write_text(
        json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "config_overrides": {}})
    )

    db_path = tmp_path / "state.db"
    store = StateStore(db_path=str(db_path))
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=100.0,
        tp1=110.0,
        tp2=120.0,
        tp3=130.0,
        sl=95.0,
        leverage=5,
        confidence=70.0,
        risk_reward=1.43,
        indicators={},
        btc_trend="Sideways",
        timestamp=datetime(2026, 4, 3, 8, 0, 0),
    )
    store.save_position("Pumpradar OG", signal, 1000.0, 30.0, tg_msg_id=77)
    store.save_equity("Pumpradar OG", 1000.0)

    monkeypatch.setenv("PUMPRADAR_STATE_DB", str(db_path))
    runner = PassportRunner(str(cfg_dir), interval="1h")

    def fail_fetch(*args, **kwargs):
        raise RuntimeError("boom-fetch")

    monkeypatch.setattr("bot.passport_runner.fetch_klines", fail_fetch)

    assert runner.update_all_positions() == []
    assert "boom-fetch" in capsys.readouterr().out
