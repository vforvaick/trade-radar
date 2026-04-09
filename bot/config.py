"""
Central strategy configuration for Cryptopass.
All parameters derived from reverse engineering of 49 historical trades.
"""

# ============================================================
# INDICATOR SETTINGS
# ============================================================

# EMA — try multiple combos in backtester
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50

# RSI
RSI_PERIOD = 14
RSI_LONG_THRESHOLD = 50   # > 50 = bullish
RSI_SHORT_THRESHOLD = 50  # < 50 = bearish

# MACD (standard)
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Bollinger Bands
BB_PERIOD = 20
BB_STD = 2

# Volume spike
VOLUME_LOOKBACK = 20
VOLUME_SPIKE_THRESHOLD = 2.0  # 2.0x average (optimized)

# Buy/Sell Pressure
PRESSURE_THRESHOLD = 60  # > 60% = directional signal

# ============================================================
# CONFLUENCE SCORING
# ============================================================

# Minimum score to generate a signal (0-100%)
CONFIDENCE_THRESHOLD = 54

# Indicator weights (equal by default, tunable)
INDICATOR_WEIGHTS = {
    "ema_trend": 1.0,
    "macd_signal": 1.0,
    "rsi_position": 1.0,
    "rsi_divergence": 1.0,
    "bb_position": 1.0,
    "volume_spike": 1.0,
    "pressure": 1.0,
    "candle_direction": 1.0,
}

# ============================================================
# LEVERAGE & RISK/REWARD TIERS
# ============================================================

LEVERAGE_TIERS = [
    # (min_confidence, max_confidence, leverage, r_r_ratio)
    (54, 60, 4, 1.25),
    (61, 69, 5, 1.43),
    (70, 100, 7, 2.08),
]

# ============================================================
# TP/SL FORMULAS
# ============================================================

# TP spacing ratios (TP2 = TP1 * TP2_RATIO, TP3 = TP2 * TP3_RATIO)
TP2_RATIO = 1.61  # TP2 distance = 1.61x TP1 distance
TP3_RATIO = 1.53  # TP3 distance = 1.53x TP2 distance

# Exit scaling (must sum to 1.0)
TP1_CLOSE_PCT = 0.70
TP2_CLOSE_PCT = 0.20
TP3_CLOSE_PCT = 0.10

# ============================================================
# RISK MANAGEMENT
# ============================================================

RISK_PER_TRADE_PCT = 0.5   # % of equity risked per trade (keeps max SL loss ~3% at 7x leverage)
MAX_SIMULTANEOUS = 999     # effectively unlimited for paper trading
MAX_OPEN_POSITIONS_PER_PASSPORT = 50
MAX_OPEN_POSITIONS_PER_SYMBOL = 1
INITIAL_EQUITY = 500.0     # for backtesting
TRADING_FEE_PCT = 0.04     # Binance taker fee per side (0.04%), so 0.08% round-trip

# BTC anomaly
BTC_ANOMALY_PCT = 1.5      # alert if BTC moves > 1.5%
BTC_ANOMALY_WINDOW_MIN = 5 # within 5 minutes

# ============================================================
# BTC TREND FILTER
# ============================================================

BTC_TREND_WEIGHTS = {
    "TREND_UP": 0.8,              # selective in bull — only high-conviction passes
    "TREND_DOWN": 1.0,            # trade freely in bear
    "HIGH_VOL_CHOP": 0.9,         # slight penalty — choppy = lower quality signals
    "LOW_VOL_COMPRESSION": 1.0,   # quiet market, trade freely
}

# Tactical guardrail for Reversal until a full regime classifier exists.
REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD = 80
REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT = 5

# ============================================================
# DATA SETTINGS
# ============================================================

TIMEFRAMES_TO_TEST = ["15m", "1h", "4h"]
DEFAULT_TIMEFRAME = "1h"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"

# Pairs to exclude (too illiquid or problematic)
EXCLUDED_PAIRS = set()

# Minimum 24h volume in USDT to consider a pair
MIN_VOLUME_USDT = 5_000_000

# ============================================================
# TRAILING STOP
# ============================================================

USE_TRAILING_STOP = False
ATR_TRAIL_MULTIPLIER = 2.0   # trail distance = 2x ATR at entry

# Per-passport direction filter: "SHORT_ONLY", "LONG_ONLY", or None (both directions)
DIRECTION_BIAS = None

# ============================================================
# WEEKDAY FILTER
# ============================================================

# Weekdays to skip (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun)
# Empty list = trade all days
SKIP_WEEKDAYS = []
