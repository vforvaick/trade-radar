"""
Confluence scoring engine.
Takes OHLCV DataFrame → runs all indicators → produces confidence score + direction.

Registry-based: 23 indicators (10 production + 13 extended from research).
Extended indicators default to weight=0 for backward compatibility.
"""
from bot import config, indicators
from bot.research import indicators as ext_ind


# ---------------------------------------------------------------------------
# Indicator registry: name → callable(df) → (direction, value)
# ---------------------------------------------------------------------------

def _vol_spike_signal(df):
    spike, ratio = indicators.calc_volume_spike(df)
    # "SPIKE" is a neutral sentinel — vol_spike is NON_DIRECTIONAL (boosts dominant side).
    # Never records a false directional claim in signals_detail.
    return ("SPIKE" if spike else None, ratio)


INDICATOR_REGISTRY: dict[str, callable] = {
    # Standard 8 (original production indicators)
    "ema_trend":       lambda df: indicators.calc_ema_trend(df),
    "macd_signal":     lambda df: indicators.calc_macd(df),
    "rsi_position":    lambda df: indicators.calc_rsi_signal(df),
    "rsi_divergence":  lambda df: (indicators.detect_rsi_divergence(df), 50.0),
    "bb_position":     lambda df: indicators.calc_bollinger(df),
    "volume_spike":    _vol_spike_signal,
    "pressure":        lambda df: indicators.calc_pressure(df),
    "candle_direction": lambda df: (indicators.calc_candle_direction(df), 50.0),
    # Production extras (default weight=0 for existing passports)
    "donchian_signal": lambda df: indicators.calc_donchian_channel(df),
    "obv_signal":      lambda df: indicators.calc_obv_signal(df),
    # Extended 13 (from research, default weight=0)
    "stochrsi":        ext_ind.calc_stochrsi,
    "obv_trend":       ext_ind.calc_obv_trend,
    "ichimoku":        ext_ind.calc_ichimoku,
    "vwap_deviation":  ext_ind.calc_vwap_deviation,
    "keltner":         ext_ind.calc_keltner,
    "donchian":        ext_ind.calc_donchian,
    "heikin_ashi":     ext_ind.calc_heikin_ashi,
    "williams_r":      ext_ind.calc_williams_r,
    "cci":             ext_ind.calc_cci,
    "mfi":             ext_ind.calc_mfi,
    "hull_ma":         ext_ind.calc_hull_ma,
    "supertrend":      ext_ind.calc_supertrend,
    "pivot_points":    ext_ind.calc_pivot_points,
}

# Indicators that default to weight=0 when not explicitly set in INDICATOR_WEIGHTS.
# Keeps existing passports (which only declare the 8 standard keys) unchanged.
EXTENDED_INDICATOR_NAMES: frozenset[str] = frozenset({
    "donchian_signal", "obv_signal",
    "stochrsi", "obv_trend", "ichimoku", "vwap_deviation",
    "keltner", "donchian", "heikin_ashi", "williams_r",
    "cci", "mfi", "hull_ma", "supertrend", "pivot_points",
})

# Confirmation-only indicator: boosts whichever side is already dominant.
# Does NOT contribute a directional vote of its own.
NON_DIRECTIONAL: frozenset[str] = frozenset({"volume_spike"})

# Convenience groups used by score_confluence
PRODUCTION_10: frozenset[str] = frozenset({
    "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
    "bb_position", "volume_spike", "pressure", "candle_direction",
    "donchian_signal", "obv_signal",
})
EXTENDED_13: frozenset[str] = frozenset({
    "stochrsi", "obv_trend", "ichimoku", "vwap_deviation",
    "keltner", "donchian", "heikin_ashi", "williams_r",
    "cci", "mfi", "hull_ma", "supertrend", "pivot_points",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_confluence(df, btc_trend="Sideways"):
    if len(df) < 55:
        return _no_signal("Insufficient data")

    indicators.add_atr(df, period=14)

    active_weights = getattr(config, 'INDICATOR_WEIGHTS', {})
    is_reversal = active_weights.get('REVERSAL_MODE', False)

    long_score = 0.0
    short_score = 0.0
    total_weight = 0.0
    signals_detail = {}

    # --- Production indicators (10): always computed for signals_detail ---
    # Volume spike handled separately as NON_DIRECTIONAL.
    prod_directional = [n for n in INDICATOR_REGISTRY if n in PRODUCTION_10 and n not in NON_DIRECTIONAL]
    prod_results: dict[str, tuple] = {}
    for name in prod_directional:
        try:
            prod_results[name] = INDICATOR_REGISTRY[name](df)
        except Exception:
            prod_results[name] = (None, 0.0)

    # Apply REVERSAL_MODE: override rsi_position to NEUTRAL if not directional
    if is_reversal:
        rsi_dir, rsi_val = prod_results.get("rsi_position", (None, 0.0))
        if rsi_dir not in ("LONG", "SHORT"):
            prod_results["rsi_position"] = ("NEUTRAL", rsi_val)

    # Populate signals_detail with production directional results
    for name, (direction, value) in prod_results.items():
        signals_detail[name] = {"direction": direction, "value": value}

    # Score production directional indicators
    for name, (direction, value) in prod_results.items():
        if name in active_weights:
            w = active_weights[name]
        elif name in EXTENDED_INDICATOR_NAMES:
            w = 0.0
        else:
            w = 1.0

        if is_reversal and name in ("ema_trend", "macd_signal"):
            w = 0.0

        if w == 0.0:
            continue

        total_weight += w
        if direction == "LONG":
            long_score += w
        elif direction == "SHORT":
            short_score += w

    # --- Volume spike (NON_DIRECTIONAL): always computed ---
    vol_spike_weight = active_weights.get("volume_spike", 1.0)
    vol_spike_occurred = False
    try:
        vol_dir, vol_val = INDICATOR_REGISTRY["volume_spike"](df)
        signals_detail["volume_spike"] = {"direction": vol_dir, "value": vol_val}
        if vol_dir is not None:
            vol_spike_occurred = True
    except Exception:
        signals_detail["volume_spike"] = {"direction": None, "value": 0.0}

    # Volume spike boosts dominant side (confirmation, not direction)
    if vol_spike_occurred and vol_spike_weight > 0:
        if long_score > short_score:
            total_weight += vol_spike_weight
            long_score += vol_spike_weight
        elif short_score > long_score:
            total_weight += vol_spike_weight
            short_score += vol_spike_weight

    # --- Extended indicators (13): only computed when weight > 0 ---
    for name in EXTENDED_13:
        w = active_weights.get(name, 0.0)
        if w == 0.0:
            continue
        try:
            direction, value = INDICATOR_REGISTRY[name](df)
        except Exception:
            direction, value = None, 0.0
        signals_detail[name] = {"direction": direction, "value": value}
        total_weight += w
        if direction == "LONG":
            long_score += w
        elif direction == "SHORT":
            short_score += w

    if long_score > short_score:
        direction = "LONG"
        raw_confidence = (long_score / total_weight) * 100 if total_weight > 0 else 0
    elif short_score > long_score:
        direction = "SHORT"
        raw_confidence = (short_score / total_weight) * 100 if total_weight > 0 else 0
    else:
        return _no_signal("No directional consensus")

    confidence_cap = getattr(config, 'CONFIDENCE_CAP', 100)
    raw_confidence = min(raw_confidence, confidence_cap)

    btc_weight = config.BTC_TREND_WEIGHTS.get(btc_trend, 1.0)
    confidence = raw_confidence * btc_weight

    ctp = getattr(config, 'COUNTER_TREND_PENALTY', {})
    ct_penalty = ctp.get(btc_trend, 1.0)
    is_counter = (
        (btc_trend == "TREND_UP" and direction == "SHORT") or
        (btc_trend == "TREND_DOWN" and direction == "LONG")
    )
    if is_counter:
        confidence *= ct_penalty

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
    for min_c, max_c, lev, rr in config.LEVERAGE_TIERS:
        if min_c <= confidence <= max_c:
            return lev, rr
    return config.LEVERAGE_TIERS[0][2], config.LEVERAGE_TIERS[0][3]


def _no_signal(reason=""):
    return {
        "direction": None,
        "confidence": 0.0,
        "leverage": 0,
        "risk_reward": 0,
        "signals": {},
        "go": False,
        "btc_trend": None,
        "raw_confidence": 0.0,
        "counter_trend_penalty": 1.0,
        "atr": None,
        "reason": reason,
    }
