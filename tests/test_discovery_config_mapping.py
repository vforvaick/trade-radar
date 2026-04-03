import pandas as pd

from bot import config, indicators
from bot.discovery_engine import StrategyDiscoveryEngine
from bot.scorer import score_confluence


def _synthetic_ohlcv(rows: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.5] * rows,
            "volume": [1000.0] * rows,
        }
    )


def test_generated_weight_profiles_use_runtime_indicator_keys():
    engine = StrategyDiscoveryEngine(["BTCUSDT"], "1h", days=30)
    cfg = engine.generate_search_space()[0]

    assert "CONFIDENCE_THRESHOLD" in cfg
    assert "MIN_SCORE_THRESHOLD" not in cfg
    assert "INDICATOR_WEIGHTS" in cfg
    assert "ema_trend" in cfg["INDICATOR_WEIGHTS"]
    assert "volume_spike" in cfg["INDICATOR_WEIGHTS"]
    assert "w_ema" not in cfg["INDICATOR_WEIGHTS"]
    assert "w_volume" not in cfg["INDICATOR_WEIGHTS"]


def test_generated_profiles_change_score_direction_on_synthetic_ohlcv(monkeypatch):
    engine = StrategyDiscoveryEngine(["BTCUSDT"], "1h", days=30)
    combos = engine.generate_search_space()
    equal_cfg = next(cfg for cfg in combos if cfg["_profile_name"] == "Equal")
    reversal_cfg = next(cfg for cfg in combos if cfg["_profile_name"] == "Reversal")

    monkeypatch.setattr(config, "CONFIDENCE_THRESHOLD", 50, raising=False)
    monkeypatch.setattr(indicators, "calc_ema_trend", lambda df: ("LONG", 1.0))
    monkeypatch.setattr(indicators, "calc_macd", lambda df: ("LONG", 0.5))
    monkeypatch.setattr(indicators, "calc_rsi_signal", lambda df: ("SHORT", 70.0))
    monkeypatch.setattr(indicators, "detect_rsi_divergence", lambda df: "SHORT")
    monkeypatch.setattr(indicators, "calc_bollinger", lambda df: ("SHORT", 0.9))
    monkeypatch.setattr(indicators, "calc_volume_spike", lambda df: (False, 1.0))
    monkeypatch.setattr(indicators, "calc_pressure", lambda df: ("LONG", 70.0))
    monkeypatch.setattr(indicators, "calc_candle_direction", lambda df: "LONG")

    monkeypatch.setattr(config, "INDICATOR_WEIGHTS", equal_cfg["INDICATOR_WEIGHTS"], raising=False)
    equal_result = score_confluence(_synthetic_ohlcv(), btc_trend="Sideways")

    monkeypatch.setattr(config, "INDICATOR_WEIGHTS", reversal_cfg["INDICATOR_WEIGHTS"], raising=False)
    reversal_result = score_confluence(_synthetic_ohlcv(), btc_trend="Sideways")

    assert equal_result["direction"] == "LONG"
    assert reversal_result["direction"] == "SHORT"
    assert equal_result["confidence"] != reversal_result["confidence"]
