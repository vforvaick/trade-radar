import pandas as pd

from bot import config, indicators
from bot.scorer import score_confluence
from bot.signals import generate_signal


def _frame(rows: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.5] * rows,
            "volume": [1000.0] * rows,
        }
    )


def test_generate_signal_uses_atr_exits_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "USE_ATR_EXITS", True, raising=False)

    score_result = {
        "go": True,
        "direction": "LONG",
        "confidence": 70.0,
        "leverage": 7,
        "risk_reward": 2.08,
        "signals": {},
        "btc_trend": "Sideways",
        "atr": 10.0,
    }

    signal = generate_signal("BTCUSDT", 100.0, score_result)

    assert signal is not None
    assert signal.sl == 80.0
    assert signal.tp1 == 140.0
    assert signal.tp2 == 164.4
    assert signal.tp3 == 198.532


def test_volume_spike_is_counted_once_in_confidence(monkeypatch):
    monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
        "ema_trend": 1.0,
        "macd_signal": 1.0,
        "rsi_position": 1.0,
        "rsi_divergence": 1.0,
        "bb_position": 1.0,
        "volume_spike": 1.0,
        "pressure": 1.0,
        "candle_direction": 1.0,
    }, raising=False)

    monkeypatch.setattr(indicators, "calc_ema_trend", lambda df: ("LONG", 1.0))
    monkeypatch.setattr(indicators, "calc_macd", lambda df: ("LONG", 1.0))
    monkeypatch.setattr(indicators, "calc_rsi_signal", lambda df: ("LONG", 55.0))
    monkeypatch.setattr(indicators, "detect_rsi_divergence", lambda df: "LONG")
    monkeypatch.setattr(indicators, "calc_bollinger", lambda df: ("LONG", 0.1))
    monkeypatch.setattr(indicators, "calc_volume_spike", lambda df: (True, 2.5))
    monkeypatch.setattr(indicators, "calc_pressure", lambda df: ("LONG", 75.0))
    monkeypatch.setattr(indicators, "calc_candle_direction", lambda df: "LONG")

    result = score_confluence(_frame())

    assert result["go"] is True
    assert result["confidence"] == 100.0


def test_reversal_mode_uses_neutral_for_neutral_rsi_vote(monkeypatch):
    monkeypatch.setattr(config, "INDICATOR_WEIGHTS", {
        "ema_trend": 0.0,
        "macd_signal": 0.0,
        "rsi_position": 0.0,
        "rsi_divergence": 0.0,
        "bb_position": 0.0,
        "volume_spike": 0.0,
        "pressure": 0.0,
        "candle_direction": 1.0,
        "REVERSAL_MODE": True,
    }, raising=False)

    monkeypatch.setattr(indicators, "calc_ema_trend", lambda df: ("NEUTRAL", 0.0))
    monkeypatch.setattr(indicators, "calc_macd", lambda df: ("NEUTRAL", 0.0))
    monkeypatch.setattr(indicators, "calc_rsi_signal", lambda df: ("NONE", 50.0))
    monkeypatch.setattr(indicators, "detect_rsi_divergence", lambda df: "NEUTRAL")
    monkeypatch.setattr(indicators, "calc_bollinger", lambda df: ("NEUTRAL", 0.5))
    monkeypatch.setattr(indicators, "calc_volume_spike", lambda df: (False, 1.0))
    monkeypatch.setattr(indicators, "calc_pressure", lambda df: ("NEUTRAL", 50.0))
    monkeypatch.setattr(indicators, "calc_candle_direction", lambda df: "LONG")

    result = score_confluence(_frame())

    assert result["go"] is True
    assert result["direction"] == "LONG"
    assert result["signals"]["rsi_position"]["direction"] == "NEUTRAL"
