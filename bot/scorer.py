"""
Confluence scoring engine.
Takes OHLCV DataFrame → runs all indicators → produces confidence score + direction.
"""
from bot import config, indicators


def score_confluence(df, btc_trend="Sideways"):
    """
    Run all indicators and compute confluence score.

    Args:
        df: DataFrame with columns [open, high, low, close, volume]
        btc_trend: 'Sideways', 'Uptrend', or 'Downtrend'

    Returns:
        dict with keys:
            direction: 'LONG' | 'SHORT' | None
            confidence: float 0-100
            leverage: int
            risk_reward: float
            signals: dict of individual indicator results
            go: bool (True if confidence >= threshold)
    """
    if len(df) < 55:  # need enough history for indicators
        return _no_signal("Insufficient data")

    indicators.add_atr(df, period=14)  # enables trailing stop + ATR exits

    # Run all indicators
    ema_dir, ema_str = indicators.calc_ema_trend(df)
    macd_dir, macd_val = indicators.calc_macd(df)
    rsi_dir, rsi_val = indicators.calc_rsi_signal(df)
    rsi_div = indicators.detect_rsi_divergence(df)
    bb_dir, bb_pos = indicators.calc_bollinger(df)
    vol_spike, vol_ratio = indicators.calc_volume_spike(df)
    press_dir, press_pct = indicators.calc_pressure(df)
    candle_dir = indicators.calc_candle_direction(df)
    donchian_dir, donchian_str = indicators.calc_donchian_channel(df)
    obv_dir, obv_str = indicators.calc_obv_signal(df)

    active_weights = getattr(config, 'INDICATOR_WEIGHTS', {})
    is_reversal = active_weights.get('REVERSAL_MODE', False)

    if is_reversal and rsi_dir not in ("LONG", "SHORT"):
        rsi_dir = "NEUTRAL"

    # Collect all directional votes
    votes = {
        "ema_trend": ema_dir,
        "macd_signal": macd_dir,
        "rsi_position": rsi_dir,
        "rsi_divergence": rsi_div,
        "bb_position": bb_dir,
        "volume_spike": None,  # volume is confirmation, not directional
        "pressure": press_dir,
        "candle_direction": candle_dir,
        "donchian_signal": donchian_dir,
        "obv_signal": obv_dir,
    }

    signals_detail = {
        "ema_trend": {"direction": ema_dir, "strength": ema_str},
        "macd_signal": {"direction": macd_dir, "histogram": macd_val},
        "rsi_position": {"direction": rsi_dir, "value": rsi_val},
        "rsi_divergence": {"direction": rsi_div},
        "bb_position": {"direction": bb_dir, "position": bb_pos},
        "volume_spike": {"spike": vol_spike, "ratio": vol_ratio},
        "pressure": {"direction": press_dir, "pct": press_pct},
        "candle_direction": {"direction": candle_dir},
        "donchian_signal": {"direction": donchian_dir, "strength": donchian_str},
        "obv_signal": {"direction": obv_dir, "strength": obv_str},
    }

    # Determine primary direction via weighted voting
    long_score = 0.0
    short_score = 0.0
    total_weight = 0.0

    # Get optional overrides if passed by backtester, else use config
    for indicator, direction in votes.items():
        w = active_weights.get(indicator, 1.0)

        # New indicators added after initial deployment default to 0 to avoid
        # affecting existing passports that don't declare them.
        if indicator in ("donchian_signal", "obv_signal") and indicator not in active_weights:
            w = 0.0

        if is_reversal:
            if indicator in ["ema_trend", "macd_signal"]:
                w = 0.0
            if indicator == "rsi_position" and direction not in ("LONG", "SHORT"):
                direction = "NEUTRAL"

        if indicator != "volume_spike":
            total_weight += w

        if direction == "LONG":
            long_score += w
        elif direction == "SHORT":
            short_score += w

    # Volume spike is a confirmation multiplier, not directional
    if vol_spike:
        vol_w = active_weights.get("volume_spike", 1.0)
        # If volume confirms the dominant direction
        if long_score > short_score:
            total_weight += vol_w
            long_score += vol_w
        elif short_score > long_score:
            total_weight += vol_w
            short_score += vol_w

    # Determine direction and raw confidence
    if long_score > short_score:
        direction = "LONG"
        # Avoid division by zero
        raw_confidence = (long_score / total_weight) * 100 if total_weight > 0 else 0
    elif short_score > long_score:
        direction = "SHORT"
        raw_confidence = (short_score / total_weight) * 100 if total_weight > 0 else 0
    else:
        return _no_signal("No directional consensus")

    # Apply BTC trend filter
    btc_weight = config.BTC_TREND_WEIGHTS.get(btc_trend, 1.0)
    confidence = raw_confidence * btc_weight

    # Apply counter-trend penalty: penalize signals opposing BTC trend
    ctp = getattr(config, 'COUNTER_TREND_PENALTY', {})
    ct_penalty = ctp.get(btc_trend, 1.0)
    is_counter = (
        (btc_trend == "TREND_UP" and direction == "SHORT") or
        (btc_trend == "TREND_DOWN" and direction == "LONG")
    )
    if is_counter:
        confidence *= ct_penalty

    # Determine leverage tier
    leverage, rr = _get_leverage_tier(confidence)

    go = confidence >= config.CONFIDENCE_THRESHOLD

    return {
        "direction": direction if go else None,
        "confidence": round(confidence, 1),
        "leverage": leverage,
        "risk_reward": rr,
        "signals": signals_detail,
        "go": go,
        "btc_trend": btc_trend,
        "raw_confidence": round(raw_confidence, 1),
        "counter_trend_penalty": ct_penalty if is_counter else 1.0,
        "atr": df['atr'].iloc[-1] if 'atr' in df.columns else None,
    }


def _get_leverage_tier(confidence):
    """Map confidence score to leverage and R:R."""
    for min_c, max_c, lev, rr in config.LEVERAGE_TIERS:
        if min_c <= confidence <= max_c:
            return lev, rr
    # Default to lowest tier
    return config.LEVERAGE_TIERS[0][2], config.LEVERAGE_TIERS[0][3]


def _no_signal(reason=""):
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
