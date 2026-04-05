"""13 new technical indicators for Strategy Research Engine families 6-18.

Each function takes an OHLCV DataFrame and returns (direction, value) where:
- direction: "LONG", "SHORT", or None
- value: numeric confidence/strength (0-100 scale where possible)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _safe(direction: str | None, value: float) -> tuple[str | None, float]:
    """Validate direction and clamp value."""
    if direction not in ("LONG", "SHORT", None):
        return None, 0.0
    return direction, float(value)


def calc_stochrsi(
    df: pd.DataFrame, rsi_period: int = 14, k_period: int = 3, d_period: int = 3,
) -> tuple[str | None, float]:
    """Stochastic RSI. LONG if %K crosses above %D from oversold (<30).
    SHORT if %K crosses below %D from overbought (>70)."""
    min_bars = rsi_period + k_period + d_period + 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    close = df["close"].values
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = pd.Series(gain).rolling(rsi_period).mean().values
    avg_loss = pd.Series(loss).rolling(rsi_period).mean().values
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 100.0)
    rsi = 100 - 100 / (1 + rs)

    rsi_series = pd.Series(rsi)
    rsi_min = rsi_series.rolling(k_period).min()
    rsi_max = rsi_series.rolling(k_period).max()
    with np.errstate(divide="ignore", invalid="ignore"):
        stoch_k = np.where(
            rsi_max - rsi_min != 0,
            (rsi_series - rsi_min) / (rsi_max - rsi_min) * 100,
            50.0,
        )
    stoch_d = pd.Series(stoch_k).rolling(d_period).mean().values

    k_now, k_prev = stoch_k[-1], stoch_k[-2]
    d_now, d_prev = stoch_d[-1], stoch_d[-2]

    if np.isnan(k_now) or np.isnan(d_now):
        return _safe(None, 0.0)

    if k_prev < d_prev and k_now > d_now and k_now < 30:
        return _safe("LONG", min(100, (30 - k_now) * 2 + 50))
    if k_prev > d_prev and k_now < d_now and k_now > 70:
        return _safe("SHORT", min(100, (k_now - 70) * 2 + 50))
    return _safe(None, abs(k_now - d_now))


def calc_obv_trend(
    df: pd.DataFrame, period: int = 20,
) -> tuple[str | None, float]:
    """OBV linear regression slope. LONG if positive trend, SHORT if negative."""
    min_bars = period + 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    close = df["close"].values
    volume = df["volume"].values
    direction_sign = np.sign(np.diff(close, prepend=close[0]))
    obv = np.cumsum(direction_sign * volume)

    recent = obv[-period:]
    x = np.arange(period, dtype=float)
    slope = np.polyfit(x, recent, 1)[0]

    # Normalize slope relative to mean OBV
    mean_obv = np.abs(recent).mean()
    if mean_obv == 0:
        return _safe(None, 0.0)
    norm_slope = slope / mean_obv * 100

    if norm_slope > 0.5:
        return _safe("LONG", min(100, abs(norm_slope) * 10 + 50))
    if norm_slope < -0.5:
        return _safe("SHORT", min(100, abs(norm_slope) * 10 + 50))
    return _safe(None, abs(norm_slope) * 10)


def calc_ichimoku(df: pd.DataFrame) -> tuple[str | None, float]:
    """Ichimoku Cloud. Counts signals from Tenkan/Kijun cross, cloud position,
    and span color. Majority vote decides direction."""
    min_bars = 52
    if len(df) < min_bars:
        return _safe(None, 0.0)

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    def _midline(data, period):
        return pd.Series(data).rolling(period).max().values / 2 + \
               pd.Series(data).rolling(period).min().values / 2

    tenkan = (_hl_mid(high, low, 9))
    kijun = (_hl_mid(high, low, 26))
    senkou_a = (tenkan + kijun) / 2
    senkou_b = _hl_mid(high, low, 52)

    signals = []
    # Tenkan/Kijun cross
    if tenkan[-1] > kijun[-1] and tenkan[-2] <= kijun[-2]:
        signals.append(1)
    elif tenkan[-1] < kijun[-1] and tenkan[-2] >= kijun[-2]:
        signals.append(-1)
    else:
        signals.append(0)

    # Price vs cloud
    cloud_top = max(senkou_a[-1], senkou_b[-1])
    cloud_bot = min(senkou_a[-1], senkou_b[-1])
    if close[-1] > cloud_top:
        signals.append(1)
    elif close[-1] < cloud_bot:
        signals.append(-1)
    else:
        signals.append(0)

    # Span color (bullish = A > B)
    if senkou_a[-1] > senkou_b[-1]:
        signals.append(1)
    elif senkou_a[-1] < senkou_b[-1]:
        signals.append(-1)
    else:
        signals.append(0)

    total = sum(signals)
    if total >= 2:
        return _safe("LONG", 50 + total * 15)
    if total <= -2:
        return _safe("SHORT", 50 + abs(total) * 15)
    return _safe(None, abs(total) * 15)


def _hl_mid(high: np.ndarray, low: np.ndarray, period: int) -> np.ndarray:
    """Rolling (highest high + lowest low) / 2."""
    h = pd.Series(high).rolling(period).max().values
    l = pd.Series(low).rolling(period).min().values
    return (h + l) / 2


def calc_vwap_deviation(
    df: pd.DataFrame, period: int = 20,
) -> tuple[str | None, float]:
    """Rolling VWAP z-score. LONG if z < -1.5 (below VWAP), SHORT if z > 1.5."""
    min_bars = period + 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"]
    cum_tp_vol = (tp * vol).rolling(period).sum()
    cum_vol = vol.rolling(period).sum()
    vwap = (cum_tp_vol / cum_vol).values

    close = df["close"].values
    diff = close - vwap
    std = pd.Series(diff).rolling(period).std().values

    if std[-1] == 0 or np.isnan(std[-1]):
        return _safe(None, 0.0)

    z = diff[-1] / std[-1]
    if z < -1.5:
        return _safe("LONG", min(100, abs(z) * 20 + 30))
    if z > 1.5:
        return _safe("SHORT", min(100, abs(z) * 20 + 30))
    return _safe(None, abs(z) * 20)


def calc_keltner(
    df: pd.DataFrame, period: int = 20, atr_mult: float = 2.0,
) -> tuple[str | None, float]:
    """Keltner Channel. LONG on upper breakout, SHORT on lower breakout."""
    min_bars = period + 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    ema = pd.Series(close).ewm(span=period).mean().values
    tr = np.maximum(high - low, np.maximum(
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1)),
    ))
    tr[0] = high[0] - low[0]
    atr = pd.Series(tr).rolling(period).mean().values

    upper = ema + atr_mult * atr
    lower = ema - atr_mult * atr

    if close[-1] > upper[-1]:
        dist = (close[-1] - upper[-1]) / atr[-1] if atr[-1] > 0 else 0
        return _safe("LONG", min(100, 50 + dist * 20))
    if close[-1] < lower[-1]:
        dist = (lower[-1] - close[-1]) / atr[-1] if atr[-1] > 0 else 0
        return _safe("SHORT", min(100, 50 + dist * 20))
    return _safe(None, 30.0)


def calc_donchian(
    df: pd.DataFrame, period: int = 20,
) -> tuple[str | None, float]:
    """Donchian Channel. LONG at new high, SHORT at new low."""
    min_bars = period + 2
    if len(df) < min_bars:
        return _safe(None, 0.0)

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    # Use previous bar's channel (no look-ahead)
    prev_high = pd.Series(high[:-1]).rolling(period).max().iloc[-1]
    prev_low = pd.Series(low[:-1]).rolling(period).min().iloc[-1]

    if np.isnan(prev_high) or np.isnan(prev_low):
        return _safe(None, 0.0)

    if close[-1] >= prev_high:
        return _safe("LONG", 70.0)
    if close[-1] <= prev_low:
        return _safe("SHORT", 70.0)

    chan_range = prev_high - prev_low
    if chan_range > 0:
        pos = (close[-1] - prev_low) / chan_range * 100
        return _safe(None, abs(pos - 50))
    return _safe(None, 0.0)


def calc_heikin_ashi(df: pd.DataFrame) -> tuple[str | None, float]:
    """Heikin-Ashi candle persistence. LONG if 3+ green HA, SHORT if 3+ red."""
    min_bars = 10
    if len(df) < min_bars:
        return _safe(None, 0.0)

    o = df["open"].values.copy()
    h = df["high"].values.copy()
    l = df["low"].values.copy()
    c = df["close"].values.copy()

    ha_close = (o + h + l + c) / 4
    ha_open = np.empty_like(ha_close)
    ha_open[0] = (o[0] + c[0]) / 2
    for i in range(1, len(ha_close)):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2

    # Count consecutive green/red from the end
    green_count = 0
    red_count = 0
    for i in range(len(ha_close) - 1, -1, -1):
        if ha_close[i] > ha_open[i]:
            if red_count > 0:
                break
            green_count += 1
        elif ha_close[i] < ha_open[i]:
            if green_count > 0:
                break
            red_count += 1
        else:
            break

    if green_count >= 3:
        return _safe("LONG", min(100, 40 + green_count * 10))
    if red_count >= 3:
        return _safe("SHORT", min(100, 40 + red_count * 10))
    return _safe(None, max(green_count, red_count) * 15)


def calc_williams_r(
    df: pd.DataFrame, period: int = 14,
) -> tuple[str | None, float]:
    """Williams %R. LONG if < -80 (oversold), SHORT if > -20 (overbought)."""
    min_bars = period + 2
    if len(df) < min_bars:
        return _safe(None, 0.0)

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    hh = pd.Series(high).rolling(period).max().values
    ll = pd.Series(low).rolling(period).min().values

    denom = hh[-1] - ll[-1]
    if denom == 0:
        return _safe(None, 0.0)

    wr = -100 * (hh[-1] - close[-1]) / denom

    if wr < -80:
        return _safe("LONG", min(100, 50 + abs(wr + 80) * 2))
    if wr > -20:
        return _safe("SHORT", min(100, 50 + abs(wr + 20) * 2))
    return _safe(None, 30.0)


def calc_cci(
    df: pd.DataFrame, period: int = 20,
) -> tuple[str | None, float]:
    """CCI with 0.015 MAD constant. LONG if > 100 or crossing up, SHORT if < -100."""
    min_bars = period + 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)

    cci = ((tp - sma) / (0.015 * mad)).values

    if np.isnan(cci[-1]):
        return _safe(None, 0.0)

    # Cross detection
    if cci[-1] > 100:
        return _safe("LONG", min(100, 50 + abs(cci[-1] - 100) * 0.2))
    if cci[-1] < -100:
        return _safe("SHORT", min(100, 50 + abs(cci[-1] + 100) * 0.2))
    # Crossing up from -100
    if len(cci) >= 2 and cci[-2] < -100 and cci[-1] >= -100:
        return _safe("LONG", 55.0)
    # Crossing down from 100
    if len(cci) >= 2 and cci[-2] > 100 and cci[-1] <= 100:
        return _safe("SHORT", 55.0)
    return _safe(None, abs(cci[-1]) * 0.3)


def calc_mfi(
    df: pd.DataFrame, period: int = 14,
) -> tuple[str | None, float]:
    """Money Flow Index (volume-weighted RSI). LONG if < 20, SHORT if > 80."""
    min_bars = period + 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    tp = (df["high"].values + df["low"].values + df["close"].values) / 3
    mf = tp * df["volume"].values
    delta_tp = np.diff(tp, prepend=tp[0])

    pos_flow = np.where(delta_tp > 0, mf, 0.0)
    neg_flow = np.where(delta_tp < 0, mf, 0.0)

    pos_sum = pd.Series(pos_flow).rolling(period).sum().values
    neg_sum = pd.Series(neg_flow).rolling(period).sum().values

    with np.errstate(divide="ignore", invalid="ignore"):
        mfr = np.where(neg_sum != 0, pos_sum / neg_sum, 100.0)
    mfi = 100 - 100 / (1 + mfr)

    val = mfi[-1]
    if np.isnan(val):
        return _safe(None, 0.0)

    if val < 20:
        return _safe("LONG", min(100, 50 + (20 - val) * 2))
    if val > 80:
        return _safe("SHORT", min(100, 50 + (val - 80) * 2))
    return _safe(None, 30.0)


def calc_hull_ma(
    df: pd.DataFrame, period: int = 16,
) -> tuple[str | None, float]:
    """Hull Moving Average. LONG if rising, SHORT if falling."""
    min_bars = period * 2 + 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    close = pd.Series(df["close"].values)
    half = max(2, period // 2)
    sqrt_p = max(2, int(np.sqrt(period)))

    wma_half = close.rolling(half).apply(
        lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True,
    )
    wma_full = close.rolling(period).apply(
        lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True,
    )
    diff = 2 * wma_half - wma_full
    hma = diff.rolling(sqrt_p).apply(
        lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True,
    ).values

    if np.isnan(hma[-1]) or np.isnan(hma[-2]):
        return _safe(None, 0.0)

    slope = hma[-1] - hma[-2]
    if slope > 0:
        return _safe("LONG", min(100, 50 + abs(slope) / close.iloc[-1] * 5000))
    if slope < 0:
        return _safe("SHORT", min(100, 50 + abs(slope) / close.iloc[-1] * 5000))
    return _safe(None, 0.0)


def calc_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0,
) -> tuple[str | None, float]:
    """ATR-based Supertrend. LONG if close > supertrend level."""
    min_bars = period + 10
    if len(df) < min_bars:
        return _safe(None, 0.0)

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    tr = np.maximum(high - low, np.maximum(
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1)),
    ))
    tr[0] = high[0] - low[0]
    atr = pd.Series(tr).rolling(period).mean().values

    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = np.zeros_like(close)
    direction = np.ones_like(close)

    for i in range(1, len(close)):
        if np.isnan(atr[i]):
            supertrend[i] = close[i]
            continue

        if close[i] > upper_band[i - 1]:
            direction[i] = 1
        elif close[i] < lower_band[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

        if direction[i] == 1:
            supertrend[i] = max(lower_band[i], supertrend[i - 1] if direction[i - 1] == 1 else lower_band[i])
        else:
            supertrend[i] = min(upper_band[i], supertrend[i - 1] if direction[i - 1] == -1 else upper_band[i])

    if close[-1] > supertrend[-1] and direction[-1] == 1:
        dist = (close[-1] - supertrend[-1]) / atr[-1] if atr[-1] > 0 else 0
        return _safe("LONG", min(100, 50 + dist * 10))
    if close[-1] < supertrend[-1] and direction[-1] == -1:
        dist = (supertrend[-1] - close[-1]) / atr[-1] if atr[-1] > 0 else 0
        return _safe("SHORT", min(100, 50 + dist * 10))
    return _safe(None, 30.0)


def calc_pivot_points(df: pd.DataFrame) -> tuple[str | None, float]:
    """Pivot Points from previous bar HLC. LONG near S1/S2, SHORT near R1/R2."""
    min_bars = 5
    if len(df) < min_bars:
        return _safe(None, 0.0)

    prev = df.iloc[-2]
    pivot = (prev["high"] + prev["low"] + prev["close"]) / 3
    r1 = 2 * pivot - prev["low"]
    s1 = 2 * pivot - prev["high"]
    r2 = pivot + (prev["high"] - prev["low"])
    s2 = pivot - (prev["high"] - prev["low"])

    close = df["close"].iloc[-1]
    high = df["high"].values
    low = df["low"].values

    # ATR for proximity threshold
    tr = np.maximum(
        high[-5:] - low[-5:],
        np.maximum(
            np.abs(np.diff(df["close"].values[-6:], prepend=df["close"].values[-6])),
            np.abs(np.diff(df["close"].values[-6:], prepend=df["close"].values[-6])),
        )[-5:],
    )
    atr = np.mean(tr)
    threshold = atr * 0.15

    if abs(close - s1) < threshold or abs(close - s2) < threshold:
        return _safe("LONG", 60.0)
    if abs(close - r1) < threshold or abs(close - r2) < threshold:
        return _safe("SHORT", 60.0)
    return _safe(None, 20.0)
