"""Market regime classification using BTC 4H data.

Classifies each bar into one of 4 exclusive regimes:
- TREND_UP: 30d return > +10% AND ADX > 25
- TREND_DOWN: 30d return < -10% AND ADX > 25
- HIGH_VOL_CHOP: abs(30d return) <= 10% AND realized vol > median
- LOW_VOL_COMPRESSION: abs(30d return) <= 10% AND realized vol <= median
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bot.research.types import RegimeType

# 30 days in 4H bars
_30D_BARS_4H = 180
# Minimum bars needed for classification (30d lookback + warmup)
_MIN_BARS = 45


def _calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ADX (Average Directional Index)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx


def _calc_realized_vol(close: pd.Series, window: int = 30) -> pd.Series:
    """Rolling realized volatility (annualized std of log returns)."""
    log_returns = np.log(close / close.shift(1))
    # 252 trading days x 6 bars/day for 4H
    return log_returns.rolling(window).std() * np.sqrt(252 * 6)


def classify_regime(df: pd.DataFrame, window: int = 180) -> RegimeType:
    """Classify current regime from BTC 4H OHLCV data.

    Args:
        df: BTC 4H OHLCV DataFrame
        window: Lookback bars for 30d return (default 180 for 4H)

    Returns:
        RegimeType for the most recent bar

    Raises:
        ValueError: If fewer than _MIN_BARS bars provided
    """
    if len(df) < _MIN_BARS:
        raise ValueError(f"Need minimum {_MIN_BARS} bars, got {len(df)}")

    close = df["close"]
    lookback = min(window, len(close) - 1)
    ret_30d = (close.iloc[-1] / close.iloc[-lookback - 1] - 1) * 100

    adx = _calc_adx(df)
    adx_current = adx.iloc[-1]

    if ret_30d > 10 and adx_current > 25:
        return RegimeType.TREND_UP
    if ret_30d < -10 and adx_current > 25:
        return RegimeType.TREND_DOWN

    rvol = _calc_realized_vol(close)
    rvol_current = rvol.iloc[-1]
    rvol_median = rvol.rolling(60, min_periods=30).median().iloc[-1]

    if np.isnan(rvol_median) or rvol_current > rvol_median:
        return RegimeType.HIGH_VOL_CHOP
    return RegimeType.LOW_VOL_COMPRESSION


def classify_regime_series(df: pd.DataFrame, window: int = 180) -> pd.Series:
    """Classify regime for every bar in the DataFrame.

    Returns:
        pd.Series of regime string values (RegimeType.value), indexed like df
    """
    if len(df) < _MIN_BARS:
        raise ValueError(f"Need minimum {_MIN_BARS} bars, got {len(df)}")

    close = df["close"]
    ret_rolling = close.pct_change(min(window, len(close) - 1)) * 100
    adx = _calc_adx(df)
    rvol = _calc_realized_vol(close)
    rvol_median = rvol.rolling(60, min_periods=30).median()

    regimes = []
    for i in range(len(df)):
        if i < _MIN_BARS or pd.isna(ret_rolling.iloc[i]):
            regimes.append(RegimeType.LOW_VOL_COMPRESSION.value)
            continue

        ret = ret_rolling.iloc[i]
        adx_val = adx.iloc[i]

        if ret > 10 and adx_val > 25:
            regimes.append(RegimeType.TREND_UP.value)
        elif ret < -10 and adx_val > 25:
            regimes.append(RegimeType.TREND_DOWN.value)
        elif pd.isna(rvol_median.iloc[i]) or rvol.iloc[i] > rvol_median.iloc[i]:
            regimes.append(RegimeType.HIGH_VOL_CHOP.value)
        else:
            regimes.append(RegimeType.LOW_VOL_COMPRESSION.value)

    return pd.Series(regimes, index=df.index)
