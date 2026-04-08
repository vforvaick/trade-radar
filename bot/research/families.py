"""Scoring family definitions — weight profiles and parameter ranges.

Each family uses the existing 8 indicators in scorer.py with different
weight combinations and parameter settings. Passport generation iterates
over the param_ranges to create multiple variants per family.
"""
from __future__ import annotations

import itertools
from typing import Optional

_ALL_INDICATORS = [
    "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
    "bb_position", "volume_spike", "pressure", "candle_direction",
    # New 13 indicators from research/indicators.py
    "stochrsi", "obv_trend", "ichimoku", "vwap_deviation",
    "keltner", "donchian", "heikin_ashi", "williams_r",
    "cci", "mfi", "hull_ma", "supertrend", "pivot_points",
]

_ZERO_WEIGHTS = {ind: 0.0 for ind in _ALL_INDICATORS}


def _w(**overrides: float) -> dict:
    """Create weight dict with zeros for unspecified indicators."""
    weights = _ZERO_WEIGHTS.copy()
    weights.update(overrides)
    return weights


SCORING_FAMILIES: dict[str, dict] = {
    "ema_crossover": {
        "name": "EMA Crossover",
        "description": "Trend-following via EMA alignment with volume confirmation",
        "weights": _w(ema_trend=2.0, volume_spike=1.0),
        "param_ranges": {
            "EMA_FAST": [5, 8, 9, 12],
            "EMA_MID": [13, 21, 26],
            "EMA_SLOW": [34, 50, 55],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0, 2.5],
            "CONFIDENCE_THRESHOLD": [50, 55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 30,
    },
    "rsi_momentum": {
        "name": "RSI Momentum",
        "description": "RSI trend + divergence for momentum signals",
        "weights": _w(rsi_position=2.0, rsi_divergence=1.5, ema_trend=0.5),
        "param_ranges": {
            "RSI_PERIOD": [10, 14, 20],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
            "CONFIDENCE_THRESHOLD": [50, 55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 30,
    },
    "bollinger_breakout": {
        "name": "Bollinger Breakout",
        "description": "BB squeeze into breakout with volume confirmation",
        "weights": _w(bb_position=2.0, volume_spike=1.5, pressure=1.0),
        "param_ranges": {
            "BB_PERIOD": [15, 20, 25],
            "BB_STD": [1.5, 2.0, 2.5],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0, 2.5],
            "CONFIDENCE_THRESHOLD": [50, 55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP"],
        "min_trades": 30,
    },
    "macd_divergence": {
        "name": "MACD Divergence",
        "description": "MACD histogram + signal cross with EMA trend confirmation",
        "weights": _w(macd_signal=2.0, ema_trend=1.0, volume_spike=0.5),
        "param_ranges": {
            "MACD_FAST": [8, 12],
            "MACD_SLOW": [21, 26],
            "MACD_SIGNAL": [7, 9],
            "CONFIDENCE_THRESHOLD": [50, 55, 60],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 30,
    },
    "volume_spike_breakout": {
        "name": "Volume Spike Breakout",
        "description": "High volume anomaly with directional confirmation",
        "weights": _w(volume_spike=3.0, pressure=2.0, candle_direction=1.0),
        "param_ranges": {
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0, 2.5, 3.0],
            "CONFIDENCE_THRESHOLD": [50, 55, 60, 65, 70],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "hidden_gem_variant": {
        "name": "Hidden Gem Variant",
        "description": "Ultra-selective EMA+BB+Volume (inspired by profitable HiddenGem v0.1)",
        "weights": _w(ema_trend=1.0, bb_position=1.0, volume_spike=2.0),
        "param_ranges": {
            "EMA_FAST": [8, 9, 12],
            "EMA_SLOW": [45, 50, 55],
            "BB_PERIOD": [18, 20, 22],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0, 2.5],
            "CONFIDENCE_THRESHOLD": [55, 60, 65, 70],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "sniper_variant": {
        "name": "Sniper Variant",
        "description": "High-threshold BB+Volume only (inspired by profitable Sniper v0.1)",
        "weights": _w(bb_position=1.0, volume_spike=2.0),
        "param_ranges": {
            "BB_PERIOD": [18, 20, 25],
            "BB_STD": [1.5, 2.0, 2.5],
            "VOLUME_SPIKE_THRESHOLD": [2.0, 2.5, 3.0],
            "CONFIDENCE_THRESHOLD": [65, 70, 75],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 15,
    },
    "trend_purist": {
        "name": "Trend Purist",
        "description": "EMA+MACD trend confirmation, minimal noise indicators",
        "weights": _w(ema_trend=2.0, macd_signal=2.0, volume_spike=0.5),
        "param_ranges": {
            "EMA_FAST": [5, 9, 12],
            "EMA_SLOW": [34, 50, 55],
            "MACD_FAST": [8, 12],
            "MACD_SLOW": [21, 26],
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 25,
    },
    "pressure_reader": {
        "name": "Pressure Reader",
        "description": "Buy/sell pressure + candle + volume directional bias",
        "weights": _w(pressure=2.0, candle_direction=1.5, volume_spike=1.5),
        "param_ranges": {
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0, 2.5],
            "CONFIDENCE_THRESHOLD": [50, 55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP"],
        "min_trades": 30,
    },
    "balanced_all": {
        "name": "Balanced All-Indicator",
        "description": "Equal weight across all indicators (OG-style)",
        "weights": _w(
            ema_trend=1.0, macd_signal=1.0, rsi_position=1.0,
            rsi_divergence=1.0, bb_position=1.0, volume_spike=1.0,
            pressure=1.0, candle_direction=1.0,
        ),
        "param_ranges": {
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
            "CONFIDENCE_THRESHOLD": [50, 54, 60],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 30,
    },
    "rsi_bb_reversal": {
        "name": "RSI + Bollinger Reversal",
        "description": "Mean-reversion using RSI extremes + BB position",
        "weights": _w(rsi_position=2.0, bb_position=2.0, volume_spike=1.0),
        "param_ranges": {
            "RSI_PERIOD": [10, 14, 20],
            "BB_PERIOD": [15, 20, 25],
            "BB_STD": [1.5, 2.0, 2.5],
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 25,
    },
    "momentum_heavy": {
        "name": "Momentum Heavy",
        "description": "Momentum v0.2 style — EMA emphasis with threshold gate",
        "weights": _w(ema_trend=2.0, macd_signal=1.0, rsi_position=1.0, volume_spike=1.0),
        "param_ranges": {
            "EMA_FAST": [5, 8, 9],
            "EMA_SLOW": [34, 50, 55],
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 25,
    },
    # --- Families 6-18 (using new indicators) ---
    "stochastic_reversal": {
        "name": "Stochastic Reversal",
        "description": "Mean-reversion via Stochastic RSI crossovers in extreme zones",
        "weights": _w(stochrsi=2.5, rsi_position=1.5, bb_position=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "obv_trend": {
        "name": "OBV Trend",
        "description": "Volume-confirmed trend via OBV slope + EMA alignment",
        "weights": _w(obv_trend=2.5, ema_trend=1.5, volume_spike=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 25,
    },
    "ichimoku_cloud": {
        "name": "Ichimoku Cloud",
        "description": "Full Ichimoku system — Tenkan/Kijun cross + cloud + span color",
        "weights": _w(ichimoku=3.0, ema_trend=1.0, macd_signal=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 20,
    },
    "vwap_deviation": {
        "name": "VWAP Deviation",
        "description": "Mean-reversion from VWAP z-score extremes",
        "weights": _w(vwap_deviation=2.5, bb_position=1.5, rsi_position=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "keltner_breakout": {
        "name": "Keltner Breakout",
        "description": "Volatility breakout via Keltner Channel with volume confirmation",
        "weights": _w(keltner=2.5, volume_spike=2.0, ema_trend=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP"],
        "min_trades": 20,
    },
    "donchian_breakout": {
        "name": "Donchian Breakout",
        "description": "Breakout on new period high/low with trend confirmation",
        "weights": _w(donchian=2.5, ema_trend=1.5, volume_spike=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 20,
    },
    "heikin_ashi_momentum": {
        "name": "Heikin-Ashi Momentum",
        "description": "Momentum via HA candle persistence + EMA/MACD confirmation",
        "weights": _w(heikin_ashi=2.0, ema_trend=1.5, macd_signal=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 20,
    },
    "williams_reversal": {
        "name": "Williams Reversal",
        "description": "Mean-reversion via Williams %R extremes + RSI/BB confirmation",
        "weights": _w(williams_r=2.5, rsi_position=1.5, bb_position=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "cci_divergence": {
        "name": "CCI Divergence",
        "description": "CCI extreme/crossing signals with MACD/RSI confirmation",
        "weights": _w(cci=2.0, macd_signal=1.5, rsi_position=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "mfi_flow": {
        "name": "MFI Flow",
        "description": "Money flow extremes with volume and pressure confirmation",
        "weights": _w(mfi=2.5, volume_spike=1.5, pressure=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "hull_ma_crossover": {
        "name": "Hull MA Crossover",
        "description": "Fast trend following via Hull Moving Average direction + EMA/MACD",
        "weights": _w(hull_ma=2.5, ema_trend=1.5, macd_signal=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 20,
    },
    "supertrend_follow": {
        "name": "Supertrend Follow",
        "description": "ATR-based trend following via Supertrend + EMA confirmation",
        "weights": _w(supertrend=3.0, ema_trend=1.5),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["TREND_UP", "TREND_DOWN"],
        "min_trades": 20,
    },
    "pivot_bounce": {
        "name": "Pivot Bounce",
        "description": "Support/resistance bounce via pivot points + BB/RSI",
        "weights": _w(pivot_points=2.0, bb_position=1.5, rsi_position=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
        },
        "compatible_regimes": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "pressure_flow_short": {
        "name": "Pressure Flow (SHORT-biased)",
        "description": "Pressure + candle direction SHORT_ONLY for downtrend conditions",
        "weights": _w(pressure=2.5, candle_direction=1.5, ema_trend=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [60, 65],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
            "DIRECTION_BIAS": ["SHORT_ONLY"],
        },
        "compatible_regimes": ["TREND_DOWN", "HIGH_VOL_CHOP"],
        "min_trades": 20,
    },
}


def get_family(name: str) -> Optional[dict]:
    """Get family definition by name. Returns None if not found."""
    return SCORING_FAMILIES.get(name)


def get_param_grid(family_name: str) -> list[dict]:
    """Generate all parameter combinations for a family.

    Returns list of config_override dicts ready for backtester.
    Each dict contains INDICATOR_WEIGHTS + all varied parameters.
    """
    family = get_family(family_name)
    if family is None:
        return []

    param_names = list(family["param_ranges"].keys())
    param_values = list(family["param_ranges"].values())

    grid = []
    for combo in itertools.product(*param_values):
        override = dict(zip(param_names, combo))
        override["INDICATOR_WEIGHTS"] = family["weights"].copy()
        override["USE_ATR_EXITS"] = False
        override["USE_TRAILING_STOP"] = False
        override["MAX_OPEN_POSITIONS_PER_PASSPORT"] = 50
        override["MAX_OPEN_POSITIONS_PER_SYMBOL"] = 1
        grid.append(override)

    return grid
