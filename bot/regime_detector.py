# bot/regime_detector.py
"""Cached, multi-timeframe regime detector for production use.

Primary: BTC 4H candles → classify_regime() (30d return + ADX + realized vol)
Confirmation: BTC 1H candles → EMA 9/21 crossover

1H confirmation only DOWNGRADES, never upgrades:
- 4H TREND_UP + 1H EMA9 < EMA21 → downgrade to HIGH_VOL_CHOP
- 4H TREND_DOWN + 1H EMA9 > EMA21 → downgrade to HIGH_VOL_CHOP
- All other cases: 4H regime stands
"""
import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from bot.data_fetcher import fetch_klines_range
from bot.indicators import calc_ema
from bot.research.regime import classify_regime, _calc_adx, _calc_realized_vol
from bot.research.types import RegimeType

logger = logging.getLogger(__name__)

SAFE_DEFAULT = "HIGH_VOL_CHOP"


class RegimeDetector:
    """Cached, multi-timeframe regime detector."""

    CACHE_TTL = 3600  # 1 hour

    def __init__(self):
        self._cache_regime: Optional[str] = None
        self._cache_metadata: Optional[dict] = None
        self._cache_time: float = 0
        self._last_valid_regime: Optional[str] = None

    def get_current_regime(self) -> str:
        """Return current market regime string, cached for CACHE_TTL seconds.

        Returns one of: TREND_UP, TREND_DOWN, HIGH_VOL_CHOP, LOW_VOL_COMPRESSION
        """
        now = time.time()
        if self._cache_regime and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache_regime

        try:
            regime, metadata = self._detect()
            self._cache_regime = regime
            self._cache_metadata = metadata
            self._cache_time = time.time()
            self._last_valid_regime = regime
            return regime
        except Exception:
            logger.exception("Failed to detect regime — using fallback")
            if self._last_valid_regime:
                return self._last_valid_regime
            return SAFE_DEFAULT

    def get_regime_metadata(self) -> dict:
        """Return raw data behind the regime decision."""
        if self._cache_metadata:
            return self._cache_metadata
        return {"regime": SAFE_DEFAULT, "timestamp": datetime.utcnow().isoformat()}

    def invalidate_cache(self):
        """Force re-fetch on next call."""
        self._cache_regime = None
        self._cache_time = 0

    def _detect(self) -> tuple[str, dict]:
        """Run full detection: 4H primary + 1H confirmation."""
        now_ms = int(time.time() * 1000)
        # Fetch BTC 4H (200 bars ≈ 33 days, enough for classify_regime's 30d lookback)
        start_4h = now_ms - (200 * 4 * 3600 * 1000)
        btc_4h = fetch_klines_range("BTCUSDT", "4h", start_4h, now_ms)

        # Fetch BTC 1H (50 bars for EMA 9/21 confirmation)
        start_1h = now_ms - (50 * 3600 * 1000)
        btc_1h = fetch_klines_range("BTCUSDT", "1h", start_1h, now_ms)

        # Primary: 4H regime
        primary = classify_regime(btc_4h)
        primary_str = primary.value

        # Metadata from 4H
        adx_series = _calc_adx(btc_4h)
        adx_val = float(adx_series.iloc[-1]) if len(adx_series) > 0 else 0.0
        close_4h = btc_4h["close"]
        lookback = min(180, len(close_4h) - 1)
        ret_30d = float((close_4h.iloc[-1] / close_4h.iloc[-lookback - 1] - 1) * 100)
        rvol_series = _calc_realized_vol(close_4h)
        rvol_val = float(rvol_series.iloc[-1]) if len(rvol_series) > 0 else 0.0

        # Confirmation: 1H EMA 9/21
        ema9 = calc_ema(btc_1h["close"], 9)
        ema21 = calc_ema(btc_1h["close"], 21)
        ema9_val = float(ema9.iloc[-1])
        ema21_val = float(ema21.iloc[-1])
        ema9_above_ema21 = ema9_val > ema21_val

        # Apply confirmation logic (downgrades only)
        confirmation_matched = True
        final_regime = primary_str

        if primary == RegimeType.TREND_UP and not ema9_above_ema21:
            final_regime = "HIGH_VOL_CHOP"
            confirmation_matched = False
        elif primary == RegimeType.TREND_DOWN and ema9_above_ema21:
            final_regime = "HIGH_VOL_CHOP"
            confirmation_matched = False

        metadata = {
            "regime": final_regime,
            "btc_price": float(close_4h.iloc[-1]),
            "adx": round(adx_val, 1),
            "ret_30d": round(ret_30d, 1),
            "realized_vol": round(rvol_val, 3),
            "ema9_1h": round(ema9_val, 2),
            "ema21_1h": round(ema21_val, 2),
            "confirmation_matched": confirmation_matched,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(
            "Regime detected: %s (4H=%s, 1H confirm=%s, ADX=%.1f, ret30d=%.1f%%)",
            final_regime, primary_str, confirmation_matched, adx_val, ret_30d,
        )

        return final_regime, metadata
