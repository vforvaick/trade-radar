"""
Binance Futures data access layer.
Handles OHLCV fetching, rate limiting, and caching.
"""
import logging
import time
import json
import os
import requests
import pandas as pd
from bot import config


logger = logging.getLogger(__name__)
CACHE_READ_ERROR_COUNT = 0
CACHE_WRITE_ERROR_COUNT = 0

# Simple disk cache
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _verify_tls() -> bool:
    """Keep TLS verification enabled unless an explicit proxy escape hatch is set."""
    raw = os.environ.get("PUMPRADAR_BINANCE_VERIFY_TLS", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def fetch_klines(symbol: str, interval: str = "1h",
                 limit: int = 500, start_time: int = None,
                 end_time: int = None, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch OHLCV klines from Binance Futures.

    Returns DataFrame with columns:
        timestamp, open, high, low, close, volume
    """
    cache_key = f"{symbol}_{interval}_{limit}_{start_time}_{end_time}"
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    url = f"{config.BINANCE_FUTURES_BASE}/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time

    resp = requests.get(url, params=params, verify=_verify_tls(), timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict) and "error" in data:
        raise Exception(f"Binance API error for {symbol}: {data}")

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    if use_cache:
        _write_cache(cache_key, df)

    return df


def fetch_klines_range(symbol: str, interval: str,
                       start_ms: int, end_ms: int,
                       use_cache: bool = True) -> pd.DataFrame:
    """Fetch klines for a full date range (handles pagination)."""
    all_dfs = []
    current_start = start_ms

    while current_start < end_ms:
        print(f"  Fetching {symbol} {interval} from {pd.Timestamp(current_start, unit='ms'):%Y-%m-%d %H:%M}...", flush=True)
        df = fetch_klines(
            symbol, interval, limit=1500,
            start_time=current_start, end_time=end_ms,
            use_cache=use_cache
        )
        if df.empty:
            break

        all_dfs.append(df)
        # Move to next batch
        last_ts = int(df["timestamp"].iloc[-1].timestamp() * 1000)
        if last_ts <= current_start:
            break
        current_start = last_ts + 1

        time.sleep(0.15)  # rate limit

    if not all_dfs:
        return pd.DataFrame()

    result = pd.concat(all_dfs, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    return result.reset_index(drop=True)


def fetch_btc_trend(interval: str = "4h", lookback: int = 20) -> str:
    """
    Determine BTC trend: Uptrend, Downtrend, or Sideways.
    Uses EMA 9/21 crossover on 4H chart.
    """
    df = fetch_klines("BTCUSDT", interval, limit=lookback + 30)
    if df.empty:
        return "Sideways"

    from bot.indicators import calc_ema
    ema9 = calc_ema(df["close"], 9)
    ema21 = calc_ema(df["close"], 21)

    last_9 = ema9.iloc[-1]
    last_21 = ema21.iloc[-1]
    diff_pct = (last_9 - last_21) / last_21 * 100

    if diff_pct > 0.5:
        return "Uptrend"
    elif diff_pct < -0.5:
        return "Downtrend"
    else:
        return "Sideways"


def get_all_futures_symbols(min_volume: float = None) -> list[str]:
    """Get all USDT perpetual futures symbols from Binance."""
    url = f"{config.BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr"
    resp = requests.get(url, verify=_verify_tls(), timeout=15)
    resp.raise_for_status()
    tickers = resp.json()

    min_vol = min_volume or config.MIN_VOLUME_USDT
    symbols = []
    for t in tickers:
        sym = t["symbol"]
        if not sym.endswith("USDT"):
            continue
        if sym in config.EXCLUDED_PAIRS:
            continue
        vol = float(t.get("quoteVolume", 0))
        if vol >= min_vol:
            symbols.append(sym)

    return sorted(symbols)


def _cache_path(key: str) -> str:
    safe_key = key.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, f"{safe_key}.parquet")


def _read_cache(key: str):
    global CACHE_READ_ERROR_COUNT
    path = _cache_path(key)
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < 3600:  # 1 hour cache TTL
            try:
                return pd.read_parquet(path)
            except Exception:
                CACHE_READ_ERROR_COUNT += 1
                logger.exception("Failed to read cache key=%s path=%s", key, path)
                return None
    return None


def _write_cache(key: str, df: pd.DataFrame):
    global CACHE_WRITE_ERROR_COUNT
    try:
        df.to_parquet(_cache_path(key))
    except Exception:
        CACHE_WRITE_ERROR_COUNT += 1
        logger.exception(
            "Failed to write cache key=%s path=%s",
            key,
            _cache_path(key),
        )
