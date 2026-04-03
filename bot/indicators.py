"""
Technical indicator calculations.
All functions are pure: take DataFrame with OHLCV columns, return indicator values.
Expected columns: open, high, low, close, volume
"""
import numpy as np
import pandas as pd
from bot import config


def calc_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calc_ema_trend(df: pd.DataFrame,
                   fast: int = None, mid: int = None, slow: int = None):
    """
    EMA trend alignment.
    Returns: direction ('LONG', 'SHORT', 'NEUTRAL'), strength (0-1)
    """
    fast = fast or config.EMA_FAST
    mid = mid or config.EMA_MID
    slow = slow or config.EMA_SLOW

    ema_f = calc_ema(df['close'], fast)
    ema_m = calc_ema(df['close'], mid)
    ema_s = calc_ema(df['close'], slow)

    last_f, last_m, last_s = ema_f.iloc[-1], ema_m.iloc[-1], ema_s.iloc[-1]

    if last_f > last_m > last_s:
        return "LONG", 1.0
    elif last_f < last_m < last_s:
        return "SHORT", 1.0
    elif last_f > last_m:
        return "LONG", 0.5
    elif last_f < last_m:
        return "SHORT", 0.5
    else:
        return "NEUTRAL", 0.0


def calc_macd(df: pd.DataFrame,
              fast: int = None, slow: int = None, signal: int = None):
    """
    MACD indicator.
    Returns: direction ('LONG', 'SHORT', 'NEUTRAL'), histogram value
    """
    fast = fast or config.MACD_FAST
    slow = slow or config.MACD_SLOW
    signal = signal or config.MACD_SIGNAL

    ema_fast = calc_ema(df['close'], fast)
    ema_slow = calc_ema(df['close'], slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line

    h_now = histogram.iloc[-1]
    h_prev = histogram.iloc[-2] if len(histogram) > 1 else 0

    # Bullish: histogram positive and rising
    if h_now > 0 and h_now > h_prev:
        return "LONG", h_now
    # Bearish: histogram negative and falling
    elif h_now < 0 and h_now < h_prev:
        return "SHORT", h_now
    # Weakening but still directional
    elif h_now > 0:
        return "LONG", h_now
    elif h_now < 0:
        return "SHORT", h_now
    else:
        return "NEUTRAL", 0.0


def calc_rsi(df: pd.DataFrame, period: int = None) -> pd.Series:
    """RSI calculation using Wilder's smoothing."""
    period = period or config.RSI_PERIOD
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_rsi_signal(df: pd.DataFrame, period: int = None):
    """
    RSI directional signal.
    Returns: direction, RSI value
    """
    rsi = calc_rsi(df, period)
    val = rsi.iloc[-1]

    if val > config.RSI_LONG_THRESHOLD:
        return "LONG", val
    elif val < config.RSI_SHORT_THRESHOLD:
        return "SHORT", val
    else:
        return "NEUTRAL", val


def detect_rsi_divergence(df: pd.DataFrame, period: int = None, lookback: int = 14):
    """
    Detect RSI divergence.
    Bullish divergence: price makes lower low, RSI makes higher low → LONG
    Bearish divergence: price makes higher high, RSI makes lower high → SHORT
    Returns: direction ('LONG', 'SHORT', 'NEUTRAL')
    """
    rsi = calc_rsi(df, period)
    if len(df) < lookback + 5:
        return "NEUTRAL"

    prices = df['close'].iloc[-lookback:]
    rsi_vals = rsi.iloc[-lookback:]

    # Find local minima/maxima (simple approach)
    price_min_idx = prices.idxmin()
    price_max_idx = prices.idxmax()

    # Check recent vs older lows
    mid = len(prices) // 2
    first_half_price = prices.iloc[:mid]
    second_half_price = prices.iloc[mid:]
    first_half_rsi = rsi_vals.iloc[:mid]
    second_half_rsi = rsi_vals.iloc[mid:]

    # Bullish divergence: lower price low, higher RSI low
    if (second_half_price.min() < first_half_price.min() and
            second_half_rsi.min() > first_half_rsi.min()):
        return "LONG"

    # Bearish divergence: higher price high, lower RSI high
    if (second_half_price.max() > first_half_price.max() and
            second_half_rsi.max() < first_half_rsi.max()):
        return "SHORT"

    return "NEUTRAL"


def calc_bollinger(df: pd.DataFrame, period: int = None, std: float = None):
    """
    Bollinger Bands.
    Returns: direction based on position, BB position (0 = lower band, 1 = upper band)
    """
    period = period or config.BB_PERIOD
    std = std or config.BB_STD

    sma = df['close'].rolling(period).mean()
    rolling_std = df['close'].rolling(period).std()
    upper = sma + std * rolling_std
    lower = sma - std * rolling_std

    price = df['close'].iloc[-1]
    u = upper.iloc[-1]
    l = lower.iloc[-1]

    if u == l:
        position = 0.5
    else:
        position = (price - l) / (u - l)

    # Near lower band = potential LONG, near upper = potential SHORT
    if position < 0.2:
        return "LONG", position
    elif position > 0.8:
        return "SHORT", position
    else:
        return "NEUTRAL", position


def calc_volume_spike(df: pd.DataFrame,
                      lookback: int = None, threshold: float = None):
    """
    Volume spike detection.
    Returns: True if current volume > threshold × avg, spike ratio
    """
    lookback = lookback or config.VOLUME_LOOKBACK
    threshold = threshold or config.VOLUME_SPIKE_THRESHOLD

    if len(df) < lookback + 1:
        return False, 0.0

    avg_vol = df['volume'].iloc[-(lookback+1):-1].mean()
    current_vol = df['volume'].iloc[-1]

    if avg_vol == 0:
        return False, 0.0

    ratio = current_vol / avg_vol
    return ratio >= threshold, ratio


def calc_pressure(df: pd.DataFrame):
    """
    Buy/Sell pressure estimated from candle body vs range.
    Returns: direction, pressure percentage
    """
    recent = df.iloc[-3:]  # Last 3 candles

    buy_pressure = 0
    total_range = 0

    for _, candle in recent.iterrows():
        full_range = candle['high'] - candle['low']
        if full_range == 0:
            continue
        if candle['close'] > candle['open']:
            buy_pressure += (candle['close'] - candle['low']) / full_range
        else:
            buy_pressure += (candle['open'] - candle['low']) / full_range
        total_range += 1

    if total_range == 0:
        return "NEUTRAL", 50.0

    pct = (buy_pressure / total_range) * 100

    if pct > config.PRESSURE_THRESHOLD:
        return "LONG", pct
    elif pct < (100 - config.PRESSURE_THRESHOLD):
        return "SHORT", 100 - pct
    else:
        return "NEUTRAL", pct


def calc_candle_direction(df: pd.DataFrame):
    """
    Last candle direction.
    Returns: 'LONG' if green, 'SHORT' if red
    """
    last = df.iloc[-1]
    if last['close'] > last['open']:
        return "LONG"
    elif last['close'] < last['open']:
        return "SHORT"
    else:
        return "NEUTRAL"


# ==========================================
# ADVANCED OPTIMIZATION INDICATORS (V2)
# ==========================================

def add_atr(df: pd.DataFrame, period=14):
    """Average True Range for dynamic tp/sl."""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(period).mean()
    return df


def add_obv(df: pd.DataFrame):
    """On-Balance Volume for flow divergence."""
    obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    df['obv'] = obv
    df['obv_ema'] = obv.rolling(20).mean()
    return df


def add_stoch_rsi(df: pd.DataFrame, period=14, smoothK=3, smoothD=3):
    """Stochastic RSI for faster momentum shifts."""
    if 'rsi' not in df.columns:
        # Fallback if RSI not calculated yet
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

    rsi = df['rsi']
    rsi_min = rsi.rolling(period).min()
    rsi_max = rsi.rolling(period).max()
    
    # Avoid div by zero
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)
    
    df['stoch_k'] = stoch_rsi.rolling(smoothK).mean() * 100
    df['stoch_d'] = df['stoch_k'].rolling(smoothD).mean()
    return df
