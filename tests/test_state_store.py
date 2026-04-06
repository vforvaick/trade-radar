import os
from datetime import datetime

import numpy as np

from bot.signals import Signal
from bot.state_store import StateStore


def test_save_and_reload_open_position_with_numpy_safe_json(tmp_path):
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
        confidence=66.7,
        risk_reward=1.43,
        indicators={"volume_spike": {"spike": np.bool_(True), "ratio": np.float64(2.5)}},
        btc_trend="Sideways",
        timestamp=datetime(2026, 4, 3, 8, 0, 0),
    )

    pos_id = store.save_position("Pumpradar OG", signal, 1000.0, 30.0, tg_msg_id=123)
    rows = store.load_open_positions("Pumpradar OG")

    assert pos_id > 0
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["tg_msg_id"] == 123
    assert '"timestamp": "2026-04-03T08:00:00"' in rows[0]["signal_json"]


def test_get_last_equity_returns_latest_row_when_same_second(tmp_path):
    store = StateStore(db_path=str(tmp_path / "state.db"))

    store.save_equity("Pumpradar OG", 100.0)
    store.save_equity("Pumpradar OG", 0.0)

    assert store.get_last_equity("Pumpradar OG") == 0.0


def test_env_db_path_is_resolved_from_repo_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CRYPTOPASS_STATE_DB", "relative-state.db")

    store = StateStore()

    expected_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "relative-state.db")
    )
    assert store.db_path == expected_path
    if os.path.exists(expected_path):
        os.remove(expected_path)
