"""
Scanner module for Phase B Live Trading.
Scans available Binance Futures pairs, fetches latest OHLCV, and scores confluence.
"""
import logging
import time
import pandas as pd
from typing import List, Dict, Optional

from bot import config
from bot.data_fetcher import get_all_futures_symbols, fetch_klines, fetch_btc_trend
from bot.scorer import score_confluence
from bot.signals import generate_signal, Signal


logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self, interval: str = "1h", limit: int = 100):
        self.interval = interval
        self.limit = limit
        self.symbols = []
        self.btc_trend = "Sideways"
        self.symbol_refresh_error_count = 0
        self.btc_trend_error_count = 0
        self.scan_error_count = 0

    def refresh_symbols(self):
        """Update list of tradable symbols based on volume filters."""
        print("[Scanner] Refreshing symbol list...")
        try:
            self.symbols = get_all_futures_symbols()
            print(f"[Scanner] Found {len(self.symbols)} tradable pairs.")
        except Exception as e:
            self.symbol_refresh_error_count += 1
            logger.exception("Failed to refresh Binance futures symbols")
            print(f"[Scanner] Error fetching symbols: {e}")

    def update_btc_trend(self):
        """Update BTC trend filter."""
        try:
            self.btc_trend = fetch_btc_trend()
            print(f"[Scanner] BTC Trend: {self.btc_trend}")
        except Exception as e:
            self.btc_trend_error_count += 1
            logger.exception("Failed to update BTC trend filter")
            print(f"[Scanner] Error fetching BTC trend: {e}")
            self.btc_trend = "Sideways"

    def scan_all(self) -> List[Signal]:
        """Scan all pairs and return generated signals."""
        signals = []
        for i, sym in enumerate(self.symbols):
            try:
                # Fetch recent candles for indicator calculation
                klines = fetch_klines(sym, self.interval, limit=self.limit, use_cache=False)
                if len(klines) < 60:
                    continue

                # Get current candle close price and timestamp
                last_candle = klines.iloc[-1]
                close_price = last_candle['close']
                timestamp = last_candle['timestamp']

                # Score
                result = score_confluence(klines, self.btc_trend)

                if result["go"]:
                    sig = generate_signal(sym, close_price, result, timestamp=timestamp)
                    if sig:
                        print(f"[Scanner] SIGNAL FOUND! {sig.symbol} {sig.direction} (Conf: %{sig.confidence})")
                        signals.append(sig)

            except Exception as e:
                self.scan_error_count += 1
                logger.exception(
                    "Failed to scan symbol=%s interval=%s btc_trend=%s index=%s",
                    sym,
                    self.interval,
                    self.btc_trend,
                    i,
                )
                
            # small sleep to avoid rate limits
            time.sleep(0.05)

        return signals
