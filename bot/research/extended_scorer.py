"""Extended scorer with 21-indicator registry for the Strategy Research Engine.

Extends the original 8 indicators from bot/scorer.py with 13 new indicators
from bot/research/indicators.py.
"""
from __future__ import annotations

from typing import Optional

from bot import indicators as orig_ind
from bot.research import indicators as new_ind


# Registry: name → callable(df) → (direction, value)
INDICATOR_REGISTRY: dict[str, callable] = {
    # Original 8 from scorer.py
    "ema_trend": lambda df: orig_ind.calc_ema_trend(df),
    "macd_signal": lambda df: orig_ind.calc_macd(df),
    "rsi_position": lambda df: orig_ind.calc_rsi_signal(df),
    "rsi_divergence": lambda df: (orig_ind.detect_rsi_divergence(df), 50.0),
    "bb_position": lambda df: orig_ind.calc_bollinger(df),
    "volume_spike": lambda df: (
        "LONG" if orig_ind.calc_volume_spike(df)[0] else None,
        orig_ind.calc_volume_spike(df)[1],
    ),
    "pressure": lambda df: orig_ind.calc_pressure(df),
    "candle_direction": lambda df: (orig_ind.calc_candle_direction(df), 50.0),
    # New 13 from research/indicators.py
    "stochrsi": new_ind.calc_stochrsi,
    "obv_trend": new_ind.calc_obv_trend,
    "ichimoku": new_ind.calc_ichimoku,
    "vwap_deviation": new_ind.calc_vwap_deviation,
    "keltner": new_ind.calc_keltner,
    "donchian": new_ind.calc_donchian,
    "heikin_ashi": new_ind.calc_heikin_ashi,
    "williams_r": new_ind.calc_williams_r,
    "cci": new_ind.calc_cci,
    "mfi": new_ind.calc_mfi,
    "hull_ma": new_ind.calc_hull_ma,
    "supertrend": new_ind.calc_supertrend,
    "pivot_points": new_ind.calc_pivot_points,
}


def score_extended(
    df,
    weights: dict[str, float],
    btc_trend: str = "Sideways",
    confidence_threshold: float = 50.0,
) -> dict:
    """Run weighted voting using the extended 21-indicator registry.

    Args:
        df: OHLCV DataFrame
        weights: indicator_name → weight (0 = skip)
        btc_trend: "Sideways", "Uptrend", "Downtrend"
        confidence_threshold: minimum confidence to fire signal

    Returns:
        dict with direction, confidence, leverage, risk_reward, go, signals
    """
    if len(df) < 55:
        return _no_signal("Insufficient data")

    if not weights:
        return _no_signal("No weights provided")

    active = {k: v for k, v in weights.items() if v > 0 and k in INDICATOR_REGISTRY}
    if not active:
        return _no_signal("No active indicators")

    # Non-directional indicators (confirmation only)
    NON_DIRECTIONAL = {"volume_spike"}

    long_score = 0.0
    short_score = 0.0
    total_weight = 0.0
    signals_detail = {}
    dominant_volume = False

    for name, w in active.items():
        if name not in INDICATOR_REGISTRY:
            continue
        try:
            direction, value = INDICATOR_REGISTRY[name](df)
        except Exception:
            direction, value = None, 0.0

        signals_detail[name] = {"direction": direction, "value": value}

        if name in NON_DIRECTIONAL:
            if direction is not None:
                dominant_volume = True
            continue

        total_weight += w
        if direction == "LONG":
            long_score += w
        elif direction == "SHORT":
            short_score += w

    # Volume spike confirms dominant direction
    if dominant_volume and "volume_spike" in active:
        vol_w = active["volume_spike"]
        if long_score > short_score:
            total_weight += vol_w
            long_score += vol_w
        elif short_score > long_score:
            total_weight += vol_w
            short_score += vol_w

    if total_weight == 0:
        return _no_signal("Zero total weight")

    if long_score > short_score:
        direction = "LONG"
        raw_confidence = (long_score / total_weight) * 100
    elif short_score > long_score:
        direction = "SHORT"
        raw_confidence = (short_score / total_weight) * 100
    else:
        return _no_signal("No directional consensus")

    # BTC trend filter
    BTC_WEIGHT = {"Uptrend": 1.15, "Downtrend": 0.85, "Sideways": 1.0}
    confidence = raw_confidence * BTC_WEIGHT.get(btc_trend, 1.0)

    go = confidence >= confidence_threshold

    return {
        "direction": direction if go else None,
        "confidence": round(confidence, 1),
        "leverage": _leverage_from_confidence(confidence),
        "risk_reward": _rr_from_confidence(confidence),
        "signals": signals_detail,
        "go": go,
        "btc_trend": btc_trend,
        "raw_confidence": round(raw_confidence, 1),
    }


def _leverage_from_confidence(confidence: float) -> int:
    if confidence >= 80:
        return 5
    if confidence >= 70:
        return 3
    if confidence >= 60:
        return 2
    return 1


def _rr_from_confidence(confidence: float) -> float:
    if confidence >= 80:
        return 3.0
    if confidence >= 70:
        return 2.5
    if confidence >= 60:
        return 2.0
    return 1.5


def _no_signal(reason: str = "") -> dict:
    return {
        "direction": None,
        "confidence": 0,
        "leverage": 0,
        "risk_reward": 0,
        "signals": {},
        "go": False,
        "btc_trend": None,
        "raw_confidence": 0,
        "reason": reason,
    }
