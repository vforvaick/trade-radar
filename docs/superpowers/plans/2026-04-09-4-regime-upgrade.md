# 4-Regime Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-regime EMA-based BTC trend detector with a 4-regime ADX+volatility classifier, add comprehensive regime data collection, and send daily Telegram regime digest.

**Architecture:** New `RegimeDetector` (cached, multi-TF) wraps existing `classify_regime()`. New `RegimeLogger` collects per-scan/per-signal/per-trade regime data to SQLite. Scanner delegates to RegimeDetector. PassportRunner wires RegimeLogger. Backtester uses same classify_regime() for parity.

**Tech Stack:** Python 3.14, pandas, numpy, SQLite (via state_store.py), pytest

**Spec:** `docs/superpowers/specs/2026-04-09-4-regime-upgrade-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `bot/regime_detector.py` | Cached, multi-TF regime detection with 1H confirmation |
| `bot/regime_logger.py` | SQLite regime data collection + Telegram daily digest |
| `tests/test_regime_detector.py` | Unit tests for RegimeDetector |
| `tests/test_regime_logger.py` | Unit tests for RegimeLogger |

### Modified Files
| File | Lines | Change |
|------|-------|--------|
| `bot/config.py` | 98-104 | BTC_TREND_WEIGHTS 3→4 keys |
| `bot/scanner.py` | 10-11, 19-49 | Import + use RegimeDetector |
| `bot/passport_runner.py` | 80-123, 189-273, 455-458 | Old-key warning, regime guardrails update, RegimeLogger |
| `bot/backtester.py` | 18-33 | determine_btc_trend_at() uses classify_regime() |
| `bot/main_multi.py` | ~148, ~167 | Pass regime data to RegimeLogger |
| `tests/test_passport_btc_weights.py` | all | Update for 4-key format |
| 5 passport JSONs | BTC_TREND_WEIGHTS | Migrate 3→4 keys |

---

### Task 1: RegimeDetector Module

**Files:**
- Create: `bot/regime_detector.py`
- Create: `tests/test_regime_detector.py`
- Read: `bot/research/regime.py`, `bot/research/types.py`, `bot/data_fetcher.py`, `bot/indicators.py`

- [ ] **Step 1: Write failing tests for RegimeDetector**

```python
# tests/test_regime_detector.py
"""Tests for RegimeDetector — cached, multi-TF regime detection."""
import time
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import pytest

from bot.research.types import RegimeType


def _make_btc_df(n=200, trend="up"):
    """Create synthetic BTC OHLCV data."""
    dates = pd.date_range("2025-01-01", periods=n, freq="4h")
    base = 80000.0
    if trend == "up":
        close = base + np.linspace(0, 15000, n) + np.random.normal(0, 200, n)
    elif trend == "down":
        close = base - np.linspace(0, 15000, n) + np.random.normal(0, 200, n)
    else:
        close = base + np.random.normal(0, 500, n)
    close = np.maximum(close, 1000)
    return pd.DataFrame({
        "timestamp": dates,
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.uniform(1000, 5000, n),
    })


class TestRegimeDetectorCache:
    """Cache TTL and invalidation tests."""

    def test_cache_returns_same_result_within_ttl(self):
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            r1 = detector.get_current_regime()

        # Second call should use cache (no fetch needed)
        r2 = detector.get_current_regime()
        assert r1 == r2

    def test_cache_invalidate_forces_refetch(self):
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]) as mock_fetch:
            detector.get_current_regime()
            assert mock_fetch.call_count == 2

        detector.invalidate_cache()

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]) as mock_fetch:
            detector.get_current_regime()
            assert mock_fetch.call_count == 2

    def test_cache_expires_after_ttl(self):
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()
        detector.CACHE_TTL = 0.1  # 100ms for test

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            detector.get_current_regime()

        time.sleep(0.15)

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]) as mock_fetch:
            detector.get_current_regime()
            assert mock_fetch.call_count == 2


class TestRegimeDetectorConfirmation:
    """1H confirmation downgrade logic."""

    def test_trend_up_confirmed_when_ema9_above_ema21(self):
        """4H=TREND_UP + 1H EMA9 > EMA21 → TREND_UP (confirmed)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                regime = detector.get_current_regime()
                assert regime == "TREND_UP"

    def test_trend_up_downgraded_when_ema9_below_ema21(self):
        """4H=TREND_UP + 1H EMA9 < EMA21 → HIGH_VOL_CHOP (downgraded)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "down")  # 1H contradicts

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                regime = detector.get_current_regime()
                assert regime == "HIGH_VOL_CHOP"

    def test_trend_down_confirmed(self):
        """4H=TREND_DOWN + 1H EMA9 < EMA21 → TREND_DOWN (confirmed)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "down")
        btc_1h = _make_btc_df(200, "down")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_DOWN):
                regime = detector.get_current_regime()
                assert regime == "TREND_DOWN"

    def test_trend_down_downgraded_when_1h_bouncing(self):
        """4H=TREND_DOWN + 1H EMA9 > EMA21 → HIGH_VOL_CHOP (downgraded)."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "down")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_DOWN):
                regime = detector.get_current_regime()
                assert regime == "HIGH_VOL_CHOP"

    def test_high_vol_chop_never_upgraded(self):
        """4H=HIGH_VOL_CHOP → stays HIGH_VOL_CHOP regardless of 1H."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "flat")
        btc_1h = _make_btc_df(200, "up")  # bullish 1H should NOT upgrade

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.HIGH_VOL_CHOP):
                regime = detector.get_current_regime()
                assert regime == "HIGH_VOL_CHOP"

    def test_low_vol_compression_never_upgraded(self):
        """4H=LOW_VOL_COMPRESSION → stays LOW_VOL_COMPRESSION regardless of 1H."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "flat")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.LOW_VOL_COMPRESSION):
                regime = detector.get_current_regime()
                assert regime == "LOW_VOL_COMPRESSION"


class TestRegimeDetectorApiFailure:
    """Error handling and safe defaults."""

    def test_api_failure_returns_cached(self):
        """On API failure, return last cached regime."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                detector.get_current_regime()

        detector.invalidate_cache()

        with patch("bot.regime_detector.fetch_klines_range", side_effect=Exception("timeout")):
            regime = detector.get_current_regime()
            assert regime == "TREND_UP"

    def test_no_cache_api_failure_returns_safe_default(self):
        """No cache + API failure → HIGH_VOL_CHOP safe default."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        with patch("bot.regime_detector.fetch_klines_range", side_effect=Exception("timeout")):
            regime = detector.get_current_regime()
            assert regime == "HIGH_VOL_CHOP"

    def test_get_regime_metadata_returns_dict(self):
        """get_regime_metadata() returns structured dict with expected keys."""
        from bot.regime_detector import RegimeDetector
        detector = RegimeDetector()

        btc_4h = _make_btc_df(200, "up")
        btc_1h = _make_btc_df(200, "up")

        with patch("bot.regime_detector.fetch_klines_range", side_effect=[btc_4h, btc_1h]):
            with patch("bot.regime_detector.classify_regime", return_value=RegimeType.TREND_UP):
                detector.get_current_regime()
                meta = detector.get_regime_metadata()

        assert "regime" in meta
        assert "btc_price" in meta
        assert "adx" in meta
        assert "ema9_1h" in meta
        assert "ema21_1h" in meta
        assert "confirmation_matched" in meta
        assert "timestamp" in meta
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_regime_detector.py -v --tb=short 2>&1 | head -40`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.regime_detector'`

- [ ] **Step 3: Implement RegimeDetector**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_regime_detector.py -v --tb=short`
Expected: 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/regime_detector.py tests/test_regime_detector.py
git commit -m "feat: add RegimeDetector with cached multi-TF detection

- 4H primary regime via classify_regime() (ADX + 30d return + vol)
- 1H EMA 9/21 confirmation (downgrades only, never upgrades)
- Cache TTL = 1 hour, safe default = HIGH_VOL_CHOP on API failure
- 11 unit tests covering cache, confirmation logic, error handling

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Config BTC_TREND_WEIGHTS Migration

**Files:**
- Modify: `bot/config.py:98-104`
- Modify: `tests/test_passport_btc_weights.py`

- [ ] **Step 1: Update config.py BTC_TREND_WEIGHTS**

In `bot/config.py`, replace lines 98-104:

```python
# OLD:
BTC_TREND_WEIGHTS = {
    "Sideways": 1.0,    # trade freely
    "Downtrend": 1.0,   # trade (75% WR historically)
    "Uptrend": 0.8,     # reduce confidence by 20% — requires raw ≥67.5% to pass threshold=54
    # NOTE: 0.5 was a bug — max raw confidence is 100%, so 100×0.5=50 < threshold=54 = never fires
    # 0.8 preserves selectivity: only high-conviction setups pass in bull markets
}

# NEW:
BTC_TREND_WEIGHTS = {
    "TREND_UP": 0.8,              # selective in bull — only high-conviction passes
    "TREND_DOWN": 1.0,            # trade freely in bear
    "HIGH_VOL_CHOP": 0.9,         # slight penalty — choppy = lower quality signals
    "LOW_VOL_COMPRESSION": 1.0,   # quiet market, trade freely
}
```

- [ ] **Step 2: Update existing BTC weight tests**

Replace `tests/test_passport_btc_weights.py` entirely:

```python
"""Tests for per-passport BTC_TREND_WEIGHTS snapshot/restore isolation (4-regime)."""
from bot import config


def test_btc_trend_weights_snapshot_restore():
    """BTC_TREND_WEIGHTS override is isolated per passport (snapshot-then-restore)."""
    original_weights = config.BTC_TREND_WEIGHTS.copy()
    original_trend_up = original_weights["TREND_UP"]

    # Simulate passport_runner applying a mean-reversion passport override
    snapshot = {"BTC_TREND_WEIGHTS": config.BTC_TREND_WEIGHTS}
    config.BTC_TREND_WEIGHTS = {
        "TREND_UP": 1.0, "TREND_DOWN": 1.0,
        "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
    }

    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == 1.0
    assert config.BTC_TREND_WEIGHTS["HIGH_VOL_CHOP"] == 1.0

    # Simulate restore
    config.BTC_TREND_WEIGHTS = snapshot["BTC_TREND_WEIGHTS"]

    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == original_trend_up
    assert config.BTC_TREND_WEIGHTS == original_weights


def test_btc_trend_weights_default_penalizes_trend_up():
    """Default BTC_TREND_WEIGHTS penalizes TREND_UP (0.8) for selectivity."""
    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == 0.8
    assert config.BTC_TREND_WEIGHTS["TREND_DOWN"] == 1.0
    assert config.BTC_TREND_WEIGHTS["HIGH_VOL_CHOP"] == 0.9
    assert config.BTC_TREND_WEIGHTS["LOW_VOL_COMPRESSION"] == 1.0


def test_btc_trend_weights_has_all_four_regimes():
    """BTC_TREND_WEIGHTS must have all 4 regime keys."""
    required = {"TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}
    assert set(config.BTC_TREND_WEIGHTS.keys()) == required


def test_btc_trend_weights_no_cross_contamination():
    """Applying one passport's override doesn't bleed into the next passport's scan."""
    original = config.BTC_TREND_WEIGHTS.copy()

    # Passport A: mean-reversion, sets TREND_UP=1.0
    snapshot_a = {"BTC_TREND_WEIGHTS": config.BTC_TREND_WEIGHTS}
    config.BTC_TREND_WEIGHTS = {
        "TREND_UP": 1.0, "TREND_DOWN": 1.0,
        "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0,
    }
    config.BTC_TREND_WEIGHTS = snapshot_a["BTC_TREND_WEIGHTS"]  # restore

    # Passport B: trend-following, no override — should see default 0.8
    assert config.BTC_TREND_WEIGHTS["TREND_UP"] == original["TREND_UP"]
```

- [ ] **Step 3: Run updated tests**

Run: `uv run pytest tests/test_passport_btc_weights.py -v --tb=short`
Expected: 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add bot/config.py tests/test_passport_btc_weights.py
git commit -m "feat: migrate BTC_TREND_WEIGHTS from 3 to 4 regime keys

- TREND_UP=0.8, TREND_DOWN=1.0, HIGH_VOL_CHOP=0.9, LOW_VOL_COMPRESSION=1.0
- Replaces old Uptrend/Downtrend/Sideways keys
- Updated tests for 4-regime format

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Passport JSON Migration

**Files:**
- Modify: `passports/cryptopass-research/bb_mean_rev.json`
- Modify: `passports/cryptopass-research/macd_divergence.json`
- Modify: `passports/cryptopass-research/reversal_v2.json`
- Modify: `passports/cryptopass-research/rsi_contrarian.json`
- Modify: `passports/pumpradar/reversal.json`

Only 5 passports have explicit BTC_TREND_WEIGHTS overrides. The other 17 use config defaults (no migration needed).

- [ ] **Step 1: Migrate bb_mean_rev.json**

In `passports/cryptopass-research/bb_mean_rev.json`, replace:
```json
"BTC_TREND_WEIGHTS": {"Uptrend": 1.0, "Sideways": 1.0, "Downtrend": 1.0}
```
with:
```json
"BTC_TREND_WEIGHTS": {"TREND_UP": 1.0, "TREND_DOWN": 1.0, "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0}
```

- [ ] **Step 2: Migrate macd_divergence.json**

Same replacement in `passports/cryptopass-research/macd_divergence.json`.

- [ ] **Step 3: Migrate reversal_v2.json**

Same replacement in `passports/cryptopass-research/reversal_v2.json`.

- [ ] **Step 4: Migrate rsi_contrarian.json**

Same replacement in `passports/cryptopass-research/rsi_contrarian.json`.

- [ ] **Step 5: Migrate reversal.json (pumpradar)**

Same replacement in `passports/pumpradar/reversal.json`.

- [ ] **Step 6: Validate all passport JSONs parse correctly**

```bash
uv run python -c "
import json, glob
for f in sorted(glob.glob('passports/**/*.json', recursive=True)):
    d = json.load(open(f))
    w = d.get('config_overrides', {}).get('BTC_TREND_WEIGHTS')
    if w:
        required = {'TREND_UP', 'TREND_DOWN', 'HIGH_VOL_CHOP', 'LOW_VOL_COMPRESSION'}
        assert set(w.keys()) == required, f'{f}: got {set(w.keys())}'
        print(f'✅ {f}: {w}')
    else:
        print(f'⬜ {f}: uses config defaults')
print('All passports valid')
"
```

Expected: 5 ✅, 17 ⬜, "All passports valid"

- [ ] **Step 7: Commit**

```bash
git add passports/
git commit -m "feat: migrate 5 passport BTC_TREND_WEIGHTS to 4-regime keys

- bb_mean_rev, macd_divergence, reversal_v2, rsi_contrarian, reversal
- All mean-reversion passports: TREND_UP=1.0 (no penalty in any regime)
- 17 passports without override use new config defaults automatically

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

> **Note on `active_regimes`:** Per spec Section 5, passports support an optional `"active_regimes": null` field (Phase 1 = parsed but ignored). This is handled in Task 6 where PassportRunner logs a hypothetical skip. Adding the field to passport JSONs is deferred to Phase 2 — for now, absence of the key is equivalent to `null` (run in all regimes).

---

### Task 4: Scanner Integration

**Files:**
- Modify: `bot/scanner.py:10-11, 19-49`
- Create: `tests/test_scanner_regime.py`

- [ ] **Step 1: Write failing test for Scanner regime integration**

```python
# tests/test_scanner_regime.py
"""Tests for Scanner using RegimeDetector."""
from unittest.mock import patch, MagicMock
from bot.scanner import Scanner


def test_scanner_update_btc_trend_uses_regime_detector():
    """Scanner.update_btc_trend() delegates to RegimeDetector."""
    scanner = Scanner()

    with patch.object(scanner.regime_detector, 'get_current_regime', return_value="TREND_UP"):
        scanner.update_btc_trend()

    assert scanner.btc_trend == "TREND_UP"


def test_scanner_update_btc_trend_safe_default_on_error():
    """Scanner falls back to HIGH_VOL_CHOP on exception."""
    scanner = Scanner()

    with patch.object(scanner.regime_detector, 'get_current_regime', side_effect=Exception("boom")):
        scanner.update_btc_trend()

    assert scanner.btc_trend == "HIGH_VOL_CHOP"


def test_scanner_has_regime_detector_attribute():
    """Scanner creates a RegimeDetector on init."""
    scanner = Scanner()
    from bot.regime_detector import RegimeDetector
    assert isinstance(scanner.regime_detector, RegimeDetector)


def test_scanner_exposes_regime_metadata():
    """Scanner exposes regime metadata from detector."""
    scanner = Scanner()
    meta = {"regime": "TREND_UP", "adx": 30.5, "btc_price": 87000.0}

    with patch.object(scanner.regime_detector, 'get_current_regime', return_value="TREND_UP"):
        with patch.object(scanner.regime_detector, 'get_regime_metadata', return_value=meta):
            scanner.update_btc_trend()

    assert scanner.regime_metadata == meta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scanner_regime.py -v --tb=short`
Expected: FAIL — Scanner has no `regime_detector` attribute

- [ ] **Step 3: Update Scanner to use RegimeDetector**

In `bot/scanner.py`:

Replace import line 10:
```python
from bot.data_fetcher import get_all_futures_symbols, fetch_klines, fetch_btc_trend
```
with:
```python
from bot.data_fetcher import get_all_futures_symbols, fetch_klines
from bot.regime_detector import RegimeDetector
```

In `__init__` (after line 25), add:
```python
        self.regime_detector = RegimeDetector()
        self.regime_metadata = {}
```

Replace the `update_btc_trend` method (lines 40-49):
```python
    def update_btc_trend(self):
        """Update BTC regime via RegimeDetector (4-regime system)."""
        try:
            self.btc_trend = self.regime_detector.get_current_regime()
            self.regime_metadata = self.regime_detector.get_regime_metadata()
            adx = self.regime_metadata.get('adx', '?')
            print(f"[Scanner] BTC Regime: {self.btc_trend} (ADX: {adx})")
        except Exception as e:
            self.btc_trend_error_count += 1
            logger.exception("Failed to update BTC regime")
            print(f"[Scanner] Error fetching BTC regime: {e}")
            self.btc_trend = "HIGH_VOL_CHOP"
            self.regime_metadata = {}
```

- [ ] **Step 4: Run Scanner tests**

Run: `uv run pytest tests/test_scanner_regime.py -v --tb=short`
Expected: 4 tests PASS

- [ ] **Step 5: Run full test suite to check nothing broke**

Run: `uv run pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass (some old tests may need adjustments — fix if needed)

- [ ] **Step 6: Commit**

```bash
git add bot/scanner.py tests/test_scanner_regime.py
git commit -m "feat: scanner delegates to RegimeDetector for 4-regime classification

- Replaces fetch_btc_trend() with RegimeDetector.get_current_regime()
- Exposes regime_metadata for downstream logging
- Safe default HIGH_VOL_CHOP on errors

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Backtester Regime Parity

**Files:**
- Modify: `bot/backtester.py:1-3, 18-33`
- Test: `tests/test_backtester_regime.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/test_backtester_regime.py
"""Tests for backtester 4-regime parity."""
import pandas as pd
import numpy as np
from bot.backtester import determine_btc_trend_at


def _make_btc_df(n=200, trend="up"):
    """Create synthetic BTC OHLCV data."""
    dates = pd.date_range("2025-01-01", periods=n, freq="4h")
    base = 80000.0
    if trend == "up":
        close = base + np.linspace(0, 15000, n) + np.random.normal(0, 100, n)
    elif trend == "down":
        close = base - np.linspace(0, 15000, n) + np.random.normal(0, 100, n)
    else:
        close = base + np.random.normal(0, 200, n)
    close = np.maximum(close, 1000)
    return pd.DataFrame({
        "timestamp": dates,
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.uniform(1000, 5000, n),
    })


def test_determine_btc_trend_returns_4_regime_value():
    """determine_btc_trend_at() returns 4-regime string, not old 3-regime."""
    btc_df = _make_btc_df(200, "up")
    ts = btc_df["timestamp"].iloc[-1]
    result = determine_btc_trend_at(btc_df, ts)
    valid_regimes = {"TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}
    assert result in valid_regimes, f"Got '{result}', expected one of {valid_regimes}"


def test_determine_btc_trend_insufficient_data_returns_safe_default():
    """With too few bars, return HIGH_VOL_CHOP (safe default)."""
    btc_df = _make_btc_df(10, "up")
    ts = btc_df["timestamp"].iloc[-1]
    result = determine_btc_trend_at(btc_df, ts)
    assert result == "HIGH_VOL_CHOP"


def test_determine_btc_trend_uses_classify_regime():
    """Verify it calls classify_regime() from bot.research.regime."""
    from unittest.mock import patch
    from bot.research.types import RegimeType

    btc_df = _make_btc_df(200, "up")
    ts = btc_df["timestamp"].iloc[-1]

    with patch("bot.backtester.classify_regime", return_value=RegimeType.TREND_DOWN) as mock:
        result = determine_btc_trend_at(btc_df, ts)
        assert mock.called
        assert result == "TREND_DOWN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_backtester_regime.py -v --tb=short`
Expected: FAIL — returns "Uptrend" not in valid_regimes

- [ ] **Step 3: Update determine_btc_trend_at()**

In `bot/backtester.py`, add import near top (after line 6):
```python
from bot.research.regime import classify_regime
```

Replace `determine_btc_trend_at` function (lines 18-33):
```python
def determine_btc_trend_at(btc_df: pd.DataFrame, timestamp: pd.Timestamp) -> str:
    """Determine BTC regime at a specific point in time using 4-regime classifier.

    Uses the same classify_regime() as live RegimeDetector for backtest/live parity.
    Returns: 'TREND_UP', 'TREND_DOWN', 'HIGH_VOL_CHOP', or 'LOW_VOL_COMPRESSION'
    """
    mask = btc_df["timestamp"] <= timestamp
    subset = btc_df[mask]
    if len(subset) < 45:  # classify_regime needs minimum 45 bars
        return "HIGH_VOL_CHOP"

    try:
        regime = classify_regime(subset)
        return regime.value
    except Exception:
        return "HIGH_VOL_CHOP"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_backtester_regime.py -v --tb=short`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/backtester.py tests/test_backtester_regime.py
git commit -m "feat: backtester uses classify_regime() for 4-regime parity

- determine_btc_trend_at() now returns TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION
- Same classifier as live RegimeDetector ensures backtest/live consistency
- Safe default HIGH_VOL_CHOP on insufficient data

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: PassportRunner Old-Key Warning + Guardrails Update

**Files:**
- Modify: `bot/passport_runner.py:80-123, 455-458`

- [ ] **Step 1: Write failing test**

```python
# tests/test_passport_runner_regime.py
"""Tests for PassportRunner 4-regime integration."""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from bot import config


def test_old_btc_weights_warning(capsys):
    """PassportRunner warns about old 3-key BTC_TREND_WEIGHTS format."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestOld",
        "emoji": "🧪",
        "config_overrides": {
            "BTC_TREND_WEIGHTS": {"Uptrend": 1.0, "Sideways": 1.0, "Downtrend": 1.0},
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_old.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore"):
            runner = PassportRunner(tmpdir)

    captured = capsys.readouterr()
    assert "old 3-regime" in captured.out.lower() or "migrate" in captured.out.lower()


def test_regime_guardrails_uses_4_regime_names():
    """_apply_regime_guardrails checks for HIGH_VOL_CHOP instead of old Sideways."""
    from bot.passport_runner import PassportRunner, Passport

    passport_data = {
        "name": "TestReversal",
        "emoji": "🔄",
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 2.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0, "REVERSAL_MODE": True,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_reversal.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore"):
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    original_threshold = config.CONFIDENCE_THRESHOLD

    # Set btc_trend to HIGH_VOL_CHOP (new name for sideways-like)
    runner.scanner.btc_trend = "HIGH_VOL_CHOP"
    original_config = runner._save_config(passport.config_overrides.keys())
    runner._apply_overrides(passport.config_overrides)
    runner._apply_regime_guardrails(passport)

    assert config.CONFIDENCE_THRESHOLD >= config.REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD

    runner._restore_config(original_config)
    assert config.CONFIDENCE_THRESHOLD == original_threshold


def test_active_regimes_phase1_logs_hypothetical_skip(capsys):
    """Phase 1: active_regimes is parsed from JSON, logged but NOT enforced."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestActiveRegimes",
        "emoji": "🎯",
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_active.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore"):
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    assert passport.active_regimes == ["TREND_UP", "TREND_DOWN"]

    # Phase 1: passport still runs even when regime doesn't match active_regimes
    # (just logs a hypothetical skip)


def test_active_regimes_null_means_all(capsys):
    """active_regimes: null (or absent) means passport runs in all regimes."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestAllRegimes",
        "emoji": "🌍",
        "active_regimes": None,
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_all.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore"):
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    assert passport.active_regimes is None  # None = run in all regimes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_passport_runner_regime.py -v --tb=short`
Expected: FAIL

- [ ] **Step 3: Update PassportRunner**

In `bot/passport_runner.py`, add old-key warning in `_load_passports` method (after line 112, after `p = Passport(fpath)`):

```python
                # Warn about old 3-regime BTC_TREND_WEIGHTS format
                old_keys = {"Uptrend", "Downtrend", "Sideways"}
                btc_weights = p.config_overrides.get("BTC_TREND_WEIGHTS")
                if btc_weights and set(btc_weights.keys()) & old_keys:
                    stale = set(btc_weights.keys()) & old_keys
                    logger.warning(
                        "Passport %s has old 3-regime BTC_TREND_WEIGHTS keys %s — "
                        "migrate to 4-regime keys (TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION)",
                        p.name, stale,
                    )
                    print(
                        f"[PassportRunner] ⚠️ {p.name}: old 3-regime BTC_TREND_WEIGHTS {stale} — "
                        f"migrate to TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION",
                        flush=True,
                    )
```

Update `_apply_regime_guardrails` (line 457) — change `"Sideways"` to also check `"HIGH_VOL_CHOP"`:

```python
    def _apply_regime_guardrails(self, passport: Passport):
        """Apply tactical regime clamps for passports that need extra protection."""
        # Sideways/choppy regimes trigger reversal guardrails
        choppy_regimes = {"Sideways", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}
        if self.scanner.btc_trend not in choppy_regimes:
            return

        weights = passport.config_overrides.get("INDICATOR_WEIGHTS", {})
        is_reversal = (
            weights.get("REVERSAL_MODE") is True
            or "reversal" in passport.name.lower()
        )
        if not is_reversal:
            return

        config.CONFIDENCE_THRESHOLD = max(
            config.CONFIDENCE_THRESHOLD,
            config.REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD,
        )
        config.MAX_OPEN_POSITIONS_PER_PASSPORT = min(
            config.MAX_OPEN_POSITIONS_PER_PASSPORT,
            config.REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT,
        )
```

Also in `_load_passports`, add `active_regimes` parsing (after the old-key warning block):

```python
                # Parse active_regimes (Phase 1: log only, not enforced)
                p.active_regimes = data.get("active_regimes", None)
                if p.active_regimes is not None:
                    logger.info(
                        "Passport %s declares active_regimes=%s (Phase 1: logged only, not enforced)",
                        p.name, p.active_regimes,
                    )
```

In `run_scan_cycle()`, inside the per-passport loop, after `self._apply_regime_guardrails(passport)` (line 216), add Phase 1 hypothetical-skip logging:

```python
            # Phase 1: log if passport would have been skipped under active_regimes filtering
            active = getattr(passport, 'active_regimes', None)
            if active is not None and self.scanner.btc_trend not in active:
                logger.info(
                    "[Phase1] %s would skip regime %s (active_regimes=%s) — not enforced yet",
                    passport.name, self.scanner.btc_trend, active,
                )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_passport_runner_regime.py -v --tb=short`
Expected: 4 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short 2>&1 | tail -10`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add bot/passport_runner.py tests/test_passport_runner_regime.py
git commit -m "feat: PassportRunner warns on old BTC weights, guards on 4-regime names

- Old 3-key BTC_TREND_WEIGHTS triggers warning on passport load
- Regime guardrails now check HIGH_VOL_CHOP/LOW_VOL_COMPRESSION (not just Sideways)
- Phase 1: active_regimes field parsed and logged but not enforced

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: RegimeLogger Core

**Files:**
- Create: `bot/regime_logger.py`
- Create: `tests/test_regime_logger.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_regime_logger.py
"""Tests for RegimeLogger — SQLite data collection and daily digest."""
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from bot.state_store import StateStore


@pytest.fixture
def state_store():
    """Create a fresh StateStore with temp database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = StateStore(db_path=db_path)
    yield store
    os.unlink(db_path)


class TestRegimeLoggerSchema:
    """Table creation tests."""

    def test_creates_regime_snapshots_table(self, state_store):
        from bot.regime_logger import RegimeLogger
        logger = RegimeLogger(state_store)

        with sqlite3.connect(state_store.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        table_names = {t[0] for t in tables}
        assert "regime_snapshots" in table_names

    def test_creates_signal_regime_log_table(self, state_store):
        from bot.regime_logger import RegimeLogger
        logger = RegimeLogger(state_store)

        with sqlite3.connect(state_store.db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        table_names = {t[0] for t in tables}
        assert "signal_regime_log" in table_names


class TestRegimeLoggerLogScan:
    """Per-scan logging tests."""

    def test_log_scan_inserts_row(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        metadata = {
            "regime": "TREND_UP",
            "btc_price": 87000.0,
            "adx": 30.5,
            "ret_30d": 12.3,
            "realized_vol": 0.45,
            "ema9_1h": 87100.0,
            "ema21_1h": 86900.0,
            "confirmation_matched": True,
        }
        rl.log_scan("TREND_UP", metadata, total_signals=15, total_opened=3)

        with sqlite3.connect(state_store.db_path) as conn:
            rows = conn.execute("SELECT * FROM regime_snapshots").fetchall()
        assert len(rows) == 1

    def test_log_scan_stores_correct_values(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        metadata = {
            "regime": "HIGH_VOL_CHOP",
            "btc_price": 85000.0,
            "adx": 18.0,
            "ret_30d": -2.1,
            "realized_vol": 0.55,
            "ema9_1h": 84900.0,
            "ema21_1h": 85100.0,
            "confirmation_matched": False,
        }
        rl.log_scan("HIGH_VOL_CHOP", metadata, total_signals=5, total_opened=1)

        with sqlite3.connect(state_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM regime_snapshots").fetchone())
        assert row["regime"] == "HIGH_VOL_CHOP"
        assert row["btc_price"] == 85000.0
        assert row["adx"] == 18.0
        assert row["total_signals"] == 5
        assert row["total_opened"] == 1


class TestRegimeLoggerLogSignal:
    """Per-signal logging tests."""

    def test_log_signal_inserts_row(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.log_signal(
            regime="TREND_UP",
            passport_name="HiddenGem",
            symbol="ETHUSDT",
            direction="LONG",
            confidence_raw=78.5,
            confidence_adjusted=62.8,
            btc_weight=0.8,
            was_executed=True,
        )

        with sqlite3.connect(state_store.db_path) as conn:
            rows = conn.execute("SELECT * FROM signal_regime_log").fetchall()
        assert len(rows) == 1

    def test_log_signal_with_skip_reason(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.log_signal(
            regime="TREND_DOWN",
            passport_name="Sniper",
            symbol="BTCUSDT",
            direction="SHORT",
            confidence_raw=55.0,
            confidence_adjusted=55.0,
            btc_weight=1.0,
            was_executed=False,
            skip_reason="DIRECTION_BIAS=LONG_ONLY",
        )

        with sqlite3.connect(state_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM signal_regime_log").fetchone())
        assert row["was_executed"] == 0
        assert row["skip_reason"] == "DIRECTION_BIAS=LONG_ONLY"


class TestRegimeLoggerTradeTagging:
    """Trade regime tagging tests."""

    def test_tag_trade_open(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.tag_trade_regime("open", 42, "TREND_UP")

        with sqlite3.connect(state_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trade_regime_tags").fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["trade_id"] == 42
        assert row["event"] == "open"
        assert row["regime"] == "TREND_UP"

    def test_tag_trade_close(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        rl.tag_trade_regime("open", 42, "TREND_UP")
        rl.tag_trade_regime("close", 42, "HIGH_VOL_CHOP")

        with sqlite3.connect(state_store.db_path) as conn:
            rows = conn.execute("SELECT * FROM trade_regime_tags").fetchall()
        assert len(rows) == 2


class TestRegimeLoggerDailyDigest:
    """Daily digest generation tests."""

    def test_generate_daily_digest_returns_string(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        # Insert some test data
        rl.log_scan("TREND_UP", {
            "regime": "TREND_UP", "btc_price": 87000.0, "adx": 30.0,
            "ret_30d": 12.0, "realized_vol": 0.45, "ema9_1h": 87100.0,
            "ema21_1h": 86900.0, "confirmation_matched": True,
        }, total_signals=10, total_opened=2)

        digest = rl.generate_daily_digest()
        assert isinstance(digest, str)
        assert "Cryptopass" in digest or "Regime" in digest

    def test_generate_daily_digest_empty_data(self, state_store):
        from bot.regime_logger import RegimeLogger
        rl = RegimeLogger(state_store)

        digest = rl.generate_daily_digest()
        assert isinstance(digest, str)
        assert len(digest) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_regime_logger.py -v --tb=short 2>&1 | head -30`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.regime_logger'`

- [ ] **Step 3: Implement RegimeLogger**

```python
# bot/regime_logger.py
"""Regime data collection and daily digest reporting.

Collects per-scan regime snapshots, per-signal regime tags, and per-trade
regime tags into SQLite tables in state.db. Generates daily Telegram digest.
"""
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from bot.state_store import StateStore

logger = logging.getLogger(__name__)


class RegimeLogger:
    """Handles all regime data collection and reporting."""

    def __init__(self, state_store: StateStore):
        self.state_store = state_store
        self._ensure_tables()

    def _ensure_tables(self):
        """Create regime logging tables if they don't exist."""
        with sqlite3.connect(self.state_store.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS regime_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    regime TEXT NOT NULL,
                    btc_price REAL,
                    adx REAL,
                    ret_30d REAL,
                    realized_vol REAL,
                    ema9_1h REAL,
                    ema21_1h REAL,
                    confirmation_matched INTEGER,
                    total_signals INTEGER,
                    total_opened INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_regime_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    regime TEXT NOT NULL,
                    passport_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence_raw REAL,
                    confidence_adjusted REAL,
                    btc_weight_applied REAL,
                    was_executed INTEGER DEFAULT 0,
                    skip_reason TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_regime_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    trade_id INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    regime TEXT NOT NULL
                )
            """)

    def log_scan(self, regime: str, metadata: dict,
                 total_signals: int, total_opened: int):
        """Log per-scan regime snapshot."""
        with sqlite3.connect(self.state_store.db_path) as conn:
            conn.execute(
                """INSERT INTO regime_snapshots
                   (regime, btc_price, adx, ret_30d, realized_vol,
                    ema9_1h, ema21_1h, confirmation_matched,
                    total_signals, total_opened)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    regime,
                    metadata.get("btc_price"),
                    metadata.get("adx"),
                    metadata.get("ret_30d"),
                    metadata.get("realized_vol"),
                    metadata.get("ema9_1h"),
                    metadata.get("ema21_1h"),
                    1 if metadata.get("confirmation_matched") else 0,
                    total_signals,
                    total_opened,
                ),
            )

    def log_signal(self, regime: str, passport_name: str, symbol: str,
                   direction: str, confidence_raw: float, confidence_adjusted: float,
                   btc_weight: float, was_executed: bool,
                   skip_reason: Optional[str] = None):
        """Log per-signal regime tag."""
        with sqlite3.connect(self.state_store.db_path) as conn:
            conn.execute(
                """INSERT INTO signal_regime_log
                   (regime, passport_name, symbol, direction,
                    confidence_raw, confidence_adjusted, btc_weight_applied,
                    was_executed, skip_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    regime, passport_name, symbol, direction,
                    confidence_raw, confidence_adjusted, btc_weight,
                    1 if was_executed else 0, skip_reason,
                ),
            )

    def tag_trade_regime(self, event: str, trade_id: int, regime: str):
        """Tag a trade with current regime (event='open' or 'close')."""
        with sqlite3.connect(self.state_store.db_path) as conn:
            conn.execute(
                "INSERT INTO trade_regime_tags (trade_id, event, regime) VALUES (?, ?, ?)",
                (trade_id, event, regime),
            )

    def generate_daily_digest(self) -> str:
        """Generate daily regime report text for Telegram.

        Content:
        - Current regime + BTC price + ADX + 30d return
        - Regime distribution over last 24h
        - Signal generation stats
        """
        with sqlite3.connect(self.state_store.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Latest snapshot
            latest = conn.execute(
                "SELECT * FROM regime_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()

            # 24h regime distribution
            cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            dist_rows = conn.execute(
                "SELECT regime, COUNT(*) as cnt FROM regime_snapshots "
                "WHERE timestamp >= ? GROUP BY regime ORDER BY cnt DESC",
                (cutoff,),
            ).fetchall()

            # 24h signal stats
            sig_stats = conn.execute(
                "SELECT COUNT(*) as total, SUM(was_executed) as executed "
                "FROM signal_regime_log WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()

        lines = [
            "📊 Cryptopass Daily Regime Report",
            "━" * 32,
        ]

        if latest:
            latest = dict(latest)
            lines.append(f"🌍 Current: {latest.get('regime', 'Unknown')}")
            btc_price = latest.get("btc_price")
            adx = latest.get("adx")
            ret = latest.get("ret_30d")
            vol = latest.get("realized_vol")
            lines.append(
                f"📈 BTC: ${btc_price:,.0f} | ADX: {adx:.1f} | "
                f"30d: {ret:+.1f}% | Vol: {vol:.1%}"
                if btc_price else "📈 No BTC data yet"
            )
        else:
            lines.append("🌍 No regime data collected yet")

        lines.append("")
        lines.append("⏰ Regime Distribution (24h):")
        total_scans = sum(dict(r)["cnt"] for r in dist_rows) if dist_rows else 0
        if dist_rows:
            for row in dist_rows:
                row = dict(row)
                pct = row["cnt"] / total_scans * 100 if total_scans > 0 else 0
                lines.append(f"  {row['regime']}: {row['cnt']}/{total_scans} ({pct:.0f}%)")
        else:
            lines.append("  No data")

        lines.append("")
        if sig_stats:
            sig_stats = dict(sig_stats)
            total = sig_stats["total"] or 0
            executed = sig_stats["executed"] or 0
            rate = executed / total * 100 if total > 0 else 0
            lines.append(
                f"💡 Signals: {total} generated → {executed} executed ({rate:.0f}% rate)"
            )
        else:
            lines.append("💡 No signals generated")

        lines.append("━" * 32)
        return "\n".join(lines)

    def send_daily_digest(self, notifier):
        """Send daily digest to Telegram via notifier.send_update()."""
        text = self.generate_daily_digest()
        if notifier:
            notifier.send_update(text)
        else:
            print(text, flush=True)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_regime_logger.py -v --tb=short`
Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/regime_logger.py tests/test_regime_logger.py
git commit -m "feat: add RegimeLogger for SQLite data collection + daily digest

- 3 new tables: regime_snapshots, signal_regime_log, trade_regime_tags
- log_scan(): per-scan regime snapshot with metadata
- log_signal(): per-signal regime tag with execution status
- tag_trade_regime(): per-trade open/close regime tag
- generate_daily_digest(): formatted Telegram report
- 10 unit tests

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: PassportRunner + Main Loop RegimeLogger Integration

**Files:**
- Modify: `bot/passport_runner.py` (add RegimeLogger init, log_scan, log_signal calls)
- Modify: `bot/main_multi.py` (daily digest scheduling)

- [ ] **Step 1: Write integration test**

```python
# tests/test_regime_integration.py
"""Integration tests for 4-regime system end-to-end."""
import json
import os
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock
from datetime import datetime

from bot import config


def _make_passport_json(tmpdir, name="IntTest", enabled=True):
    """Create a minimal passport JSON for testing."""
    data = {
        "name": name,
        "emoji": "🧪",
        "enabled": enabled,
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }
    fpath = os.path.join(tmpdir, f"{name.lower()}.json")
    with open(fpath, "w") as f:
        json.dump(data, f)
    return fpath


def test_passport_runner_has_regime_logger():
    """PassportRunner creates a RegimeLogger on init."""
    from bot.passport_runner import PassportRunner
    from bot.regime_logger import RegimeLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        _make_passport_json(tmpdir)
        with patch("bot.passport_runner.StateStore") as MockStore:
            MockStore.return_value.load_open_positions.return_value = []
            MockStore.return_value.get_last_equity.return_value = None
            runner = PassportRunner(tmpdir)

    assert hasattr(runner, "regime_logger")
    assert isinstance(runner.regime_logger, RegimeLogger)


def test_scan_cycle_logs_regime_snapshot():
    """run_scan_cycle() calls regime_logger.log_scan() at end."""
    from bot.passport_runner import PassportRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        _make_passport_json(tmpdir)
        with patch("bot.passport_runner.StateStore") as MockStore:
            MockStore.return_value.load_open_positions.return_value = []
            MockStore.return_value.get_last_equity.return_value = None
            runner = PassportRunner(tmpdir)

    runner.regime_logger = MagicMock()
    runner.scanner.symbols = []  # empty scan (no symbols to scan)
    runner.scanner.btc_trend = "TREND_UP"
    runner.scanner.regime_metadata = {"regime": "TREND_UP", "adx": 30.0}

    with patch.object(runner.scanner, "update_btc_trend"):
        runner.run_scan_cycle()

    runner.regime_logger.log_scan.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_regime_integration.py -v --tb=short`
Expected: FAIL — runner has no `regime_logger`

- [ ] **Step 3: Add RegimeLogger to PassportRunner**

In `bot/passport_runner.py`, add import (after line 17):
```python
from bot.regime_logger import RegimeLogger
```

In `__init__` (after line 58, after `self.state_store = StateStore()`):
```python
        self.regime_logger = RegimeLogger(self.state_store)
        self._last_digest_date = None
```

In `run_scan_cycle()`, after `all_results = []` (line 196), add a signal counter:

```python
        cycle_signal_count = 0
```

Then inside the per-passport loop, after `signals = self.scanner.scan_all()` (line 229), add:

```python
                cycle_signal_count += len(signals)
```

At the end of `run_scan_cycle()`, before `return all_results` (after line 272, after the for loop's finally block), add:

```python
        # Log regime snapshot for this scan cycle
        try:
            self.regime_logger.log_scan(
                regime=self.scanner.btc_trend,
                metadata=getattr(self.scanner, 'regime_metadata', {}),
                total_signals=cycle_signal_count,
                total_opened=len(all_results),
            )
        except Exception:
            logger.exception("Failed to log regime snapshot")

        # Check daily digest
        self._check_daily_digest()

        return all_results
```

Add `_check_daily_digest` method (after `_restore_config`):

```python
    def _check_daily_digest(self):
        """Send daily regime digest at UTC midnight."""
        today = datetime.utcnow().date()
        if self._last_digest_date == today:
            return
        if datetime.utcnow().hour != 0:
            return
        try:
            self.regime_logger.send_daily_digest(None)
            self._last_digest_date = today
        except Exception:
            logger.exception("Failed to send daily digest")
```

- [ ] **Step 4: Run integration tests**

Run: `uv run pytest tests/test_regime_integration.py -v --tb=short`
Expected: 2 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short 2>&1 | tail -10`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add bot/passport_runner.py bot/main_multi.py tests/test_regime_integration.py
git commit -m "feat: wire RegimeLogger into PassportRunner scan cycle

- PassportRunner creates RegimeLogger on init
- log_scan() called at end of every scan cycle
- Daily digest scheduled at UTC midnight
- Integration tests verify wiring

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: Remove Deprecated fetch_btc_trend + Cleanup

**Files:**
- Modify: `bot/data_fetcher.py:113-136` (keep function but mark deprecated)
- Modify: `bot/research/regime.py:133-152` (remove map_to_live_regime, update map_regime_value_to_live)

- [ ] **Step 1: Mark fetch_btc_trend as deprecated**

In `bot/data_fetcher.py`, add deprecation warning to `fetch_btc_trend` (line 113):

```python
def fetch_btc_trend(interval: str = "4h", lookback: int = 20) -> str:
    """DEPRECATED: Use RegimeDetector.get_current_regime() instead.

    Kept for backward compatibility with any scripts that import this directly.
    Returns old 3-regime format: Uptrend/Downtrend/Sideways.
    """
    import warnings
    warnings.warn(
        "fetch_btc_trend() is deprecated. Use bot.regime_detector.RegimeDetector instead.",
        DeprecationWarning,
        stacklevel=2,
    )
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
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short 2>&1 | tail -10`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add bot/data_fetcher.py
git commit -m "refactor: deprecate fetch_btc_trend(), keep for backward compat

- Adds DeprecationWarning when called
- Live system now uses RegimeDetector (Scanner integration)
- Backtester uses classify_regime() directly

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 10: Full Test Suite + Docs Update

**Files:**
- Modify: `docs/FINDINGS.md` (add §18)
- Modify: `passports/VERSIONS.md`
- Modify: `docs/whats-next.md`

- [ ] **Step 1: Run complete test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ~308+ tests, all PASS

- [ ] **Step 2: Fix any broken tests**

If any tests fail due to the 3→4 regime migration:
- Tests checking for "Uptrend"/"Downtrend"/"Sideways" need updating to 4-regime values
- Tests using `fetch_btc_trend` directly need updating to mock `RegimeDetector`
- Fix each failing test

- [ ] **Step 3: Update FINDINGS.md with §18**

Add a new section to `docs/FINDINGS.md`:

```markdown
## §18 — 4-Regime Upgrade (Session 10)

**Change:** Replaced 3-regime EMA-based BTC trend detector with 4-regime ADX+vol classifier.

**Old system:** `fetch_btc_trend()` → EMA 9/21 crossover on 4H → "Uptrend"/"Downtrend"/"Sideways"
**New system:** `RegimeDetector.get_current_regime()` → 4H classify_regime() + 1H EMA confirmation → "TREND_UP"/"TREND_DOWN"/"HIGH_VOL_CHOP"/"LOW_VOL_COMPRESSION"

**Key design decisions:**
- 1H confirmation only DOWNGRADES trending regimes (never upgrades)
- Cache TTL = 1 hour, safe default = HIGH_VOL_CHOP
- Passive mode: log everything, don't auto-filter passports
- RegimeLogger collects per-scan, per-signal, per-trade regime data

**Passport migration:** 5 passports with explicit BTC_TREND_WEIGHTS migrated from 3→4 keys.
17 passports use config defaults (auto-migrated).

**Backtester parity:** determine_btc_trend_at() now uses same classify_regime() as live system.
```

- [ ] **Step 4: Update VERSIONS.md**

Bump version for all 5 migrated passports and add changelog entry.

- [ ] **Step 5: Update whats-next.md**

Mark "3-regime detector simplistic" as resolved in tech debt table.

- [ ] **Step 6: Final commit**

```bash
git add docs/FINDINGS.md passports/VERSIONS.md docs/whats-next.md
git commit -m "docs: §18 4-regime upgrade findings, version bumps, tech debt resolved

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

- [ ] **Step 7: Push to origin**

```bash
git push origin master
```

---

## Dependency Graph

```
Task 1 (RegimeDetector) ──┐
                          ├── Task 4 (Scanner) ──┐
Task 2 (Config migration) ┤                      │
                          ├── Task 5 (Backtester) │
                          ├── Task 6 (PassportRunner warning) ──┐
Task 3 (Passport JSONs) ──┘                      │              │
                                                  │              │
Task 7 (RegimeLogger) ───────────────────────────┼──────────────┤
                                                  │              │
                                                  └── Task 8 (Integration wire-up)
                                                                 │
Task 9 (Deprecate fetch_btc_trend) ──────────────────────────────┤
                                                                 │
                                                       Task 10 (Tests + Docs)
```

**Parallelizable:** Tasks 1, 2, 3, 7 have no dependencies and can run in parallel.
**Sequential:** Tasks 4-6 depend on Tasks 1-3. Task 8 depends on 4, 6, 7. Task 10 depends on all.
