# Full Passport Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port 8 extended indicators into production scorer via registry pattern, re-enable 17 disabled passports, promote 12 research families to paper trading, fork big-loss passports into enhanced variants, and deploy everything to VPS with fresh start.

**Architecture:** Refactor `bot/scorer.py` from hardcoded 10-indicator pipeline to a registry-based pattern (like `bot/research/extended_scorer.py`), importing all 13 research indicators from `bot/research/indicators.py`. The scorer will look up indicator functions by name from a registry dict, allowing any passport to use any of the 21 indicators via its `INDICATOR_WEIGHTS` dict. Production `scanner.py` and `backtester.py` use scorer unchanged — only the internal implementation changes.

**Tech Stack:** Python 3.12, pandas, numpy, SQLite (state.db), uv, pytest

**Baseline:** 697 tests passing, 30 skipped. HEAD: `7131632` on master.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `bot/scorer.py` | **Rewrite** | Registry-based scorer with 21 indicators |
| `bot/indicators.py` | **Keep** | Original 10 indicator functions (unchanged) |
| `bot/research/indicators.py` | **Keep** | 13 extended indicator functions (unchanged) |
| `bot/research/extended_scorer.py` | **Modify** | Thin wrapper → imports from new scorer registry |
| `bot/passport_runner.py` | **Modify** | Add new indicator keys to `_save_config()` |
| `tests/test_scorer_registry.py` | **Create** | Tests for registry pattern, all 21 indicators |
| `tests/test_extended_scorer_compat.py` | **Create** | Backward compatibility tests |
| `passports/pumpradar/*.json` | **Modify** | Re-enable all, update INDICATOR_WEIGHTS keys |
| `passports/cryptopass-research/*.json` | **Modify** | Re-enable all, add new research winners |
| `passports/cryptopass-research/research_gen2/*.json` | **Create** | 12 research winner passports |
| `passports/cryptopass-research/enhanced/*.json` | **Create** | Forked/enhanced variants of big-loss passports |
| `docs/FINDINGS.md` | **Modify** | Document all changes |
| `passports/VERSIONS.md` | **Modify** | Update version registry |

---

### Task 1: Refactor scorer.py to registry pattern

**Files:**
- Rewrite: `bot/scorer.py`
- Test: `tests/test_scorer_registry.py`

The core change: replace hardcoded indicator calls with a registry dict mapping indicator names to callables. This is exactly what `extended_scorer.py` already does — we're bringing that pattern to production.

- [ ] **Step 1: Write failing tests for registry-based scorer**

Create `tests/test_scorer_registry.py`:

```python
"""Tests for registry-based scorer with all 21 indicators."""
import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch

from bot import config
from bot.scorer import score_confluence, INDICATOR_REGISTRY


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config to defaults after each test."""
    orig = {
        'CONFIDENCE_CAP': getattr(config, 'CONFIDENCE_CAP', 100),
        'CONFIDENCE_THRESHOLD': config.CONFIDENCE_THRESHOLD,
        'BTC_TREND_WEIGHTS': config.BTC_TREND_WEIGHTS.copy(),
        'INDICATOR_WEIGHTS': config.INDICATOR_WEIGHTS.copy(),
    }
    yield
    for k, v in orig.items():
        setattr(config, k, v)


def _make_df(n=100):
    """Create a synthetic OHLCV DataFrame for testing."""
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        'open': close - np.random.rand(n) * 0.3,
        'high': close + np.random.rand(n) * 0.5,
        'low': close - np.random.rand(n) * 0.5,
        'close': close,
        'volume': np.random.rand(n) * 1000 + 500,
        'timestamp': pd.date_range('2026-01-01', periods=n, freq='1h'),
    })


class TestRegistryExists:
    def test_registry_has_original_8(self):
        original_8 = [
            'ema_trend', 'macd_signal', 'rsi_position', 'rsi_divergence',
            'bb_position', 'volume_spike', 'pressure', 'candle_direction',
        ]
        for name in original_8:
            assert name in INDICATOR_REGISTRY, f"Missing original indicator: {name}"

    def test_registry_has_production_10(self):
        """Production scorer also has donchian_signal and obv_signal."""
        assert 'donchian_signal' in INDICATOR_REGISTRY
        assert 'obv_signal' in INDICATOR_REGISTRY

    def test_registry_has_extended_13(self):
        extended = [
            'stochrsi', 'obv_trend', 'ichimoku', 'vwap_deviation',
            'keltner', 'donchian', 'heikin_ashi', 'williams_r',
            'cci', 'mfi', 'hull_ma', 'supertrend', 'pivot_points',
        ]
        for name in extended:
            assert name in INDICATOR_REGISTRY, f"Missing extended indicator: {name}"

    def test_registry_total_count(self):
        # 10 original/production + 13 extended = 23 total
        assert len(INDICATOR_REGISTRY) == 23


class TestRegistryScoring:
    def test_standard_weights_still_work(self):
        """Existing passports with standard 8 weights must produce identical results."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {
            'ema_trend': 1.0, 'macd_signal': 0.0, 'rsi_position': 0.0,
            'rsi_divergence': 0.0, 'bb_position': 1.0, 'volume_spike': 2.0,
            'pressure': 0.0, 'candle_direction': 0.0,
        }
        result = score_confluence(df, btc_trend="Sideways")
        assert 'confidence' in result
        assert 'direction' in result
        assert 'go' in result
        assert 'raw_confidence' in result

    def test_extended_indicator_weights(self):
        """Passports using extended indicators produce valid results."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {
            'rsi_position': 1.0, 'bb_position': 1.5, 'stochrsi': 2.5,
        }
        result = score_confluence(df, btc_trend="Sideways")
        assert 'confidence' in result
        assert isinstance(result['confidence'], (int, float))

    def test_mixed_standard_and_extended(self):
        """Passports mixing standard + extended indicators work."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {
            'ema_trend': 1.5, 'volume_spike': 1.0, 'keltner': 2.5,
        }
        result = score_confluence(df, btc_trend="Sideways")
        assert 'confidence' in result

    def test_unknown_indicator_ignored(self):
        """Unknown indicator names are silently skipped."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {
            'ema_trend': 1.0, 'nonexistent_indicator': 5.0, 'bb_position': 1.0,
        }
        result = score_confluence(df, btc_trend="Sideways")
        assert 'confidence' in result

    def test_zero_weight_skipped(self):
        """Indicators with weight 0 are not computed."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {
            'ema_trend': 1.0, 'stochrsi': 0.0, 'bb_position': 1.0,
        }
        result = score_confluence(df, btc_trend="Sideways")
        # stochrsi should not appear in signals if weight=0
        if result.get('signals'):
            assert 'stochrsi' not in result['signals']

    def test_confidence_cap_still_applied(self):
        """CONFIDENCE_CAP from config is respected."""
        df = _make_df(100)
        config.CONFIDENCE_CAP = 80
        config.INDICATOR_WEIGHTS = {'ema_trend': 1.0}
        result = score_confluence(df, btc_trend="Sideways")
        assert result['raw_confidence'] <= 80

    def test_btc_trend_weight_applied(self):
        """BTC trend weight multiplier is applied after cap."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {'ema_trend': 1.0}
        config.BTC_TREND_WEIGHTS = {"TREND_UP": 0.8, "Sideways": 1.0}
        result = score_confluence(df, btc_trend="Sideways")
        # With Sideways=1.0, confidence should equal raw_confidence
        if result['go']:
            assert result['confidence'] == result['raw_confidence']

    def test_counter_trend_penalty_applied(self):
        """CTP still works in registry scorer."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {'ema_trend': 1.0, 'bb_position': 1.0}
        result = score_confluence(df, btc_trend="Sideways")
        assert 'counter_trend_penalty' in result

    def test_atr_in_result(self):
        """ATR is still computed and included in result."""
        df = _make_df(100)
        config.INDICATOR_WEIGHTS = {'ema_trend': 1.0}
        result = score_confluence(df, btc_trend="Sideways")
        assert 'atr' in result

    def test_insufficient_data(self):
        """Short DataFrame returns no-signal."""
        df = _make_df(10)
        result = score_confluence(df, btc_trend="Sideways")
        assert result['go'] is False
        assert result['direction'] is None


class TestRegistryCallables:
    """Each registry entry must be callable and return (direction, value)."""

    def test_all_callables_return_tuple(self):
        df = _make_df(100)
        for name, fn in INDICATOR_REGISTRY.items():
            try:
                result = fn(df)
                assert isinstance(result, tuple), f"{name} did not return tuple"
                assert len(result) == 2, f"{name} returned tuple of length {len(result)}"
                direction, value = result
                assert direction in ("LONG", "SHORT", "NEUTRAL", None), \
                    f"{name} returned invalid direction: {direction}"
            except Exception as e:
                pytest.fail(f"Indicator {name} raised {type(e).__name__}: {e}")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scorer_registry.py -v`
Expected: FAIL — `INDICATOR_REGISTRY` does not exist in `bot/scorer.py` yet.

- [ ] **Step 3: Rewrite scorer.py with registry pattern**

Rewrite `bot/scorer.py`. Key changes:
1. Import all indicators from both `bot.indicators` and `bot.research.indicators`
2. Build `INDICATOR_REGISTRY` dict mapping name → callable returning `(direction, value)`
3. Refactor `score_confluence()` to iterate registry instead of hardcoded calls
4. Preserve: ATR computation, REVERSAL_MODE, confidence cap, BTC weight, CTP, leverage tiers
5. Preserve: volume_spike as non-directional confirmation
6. Preserve: donchian_signal/obv_signal defaulting to weight=0 for backward compat

```python
"""
Confluence scoring engine — registry-based.
Takes OHLCV DataFrame → runs weighted indicators → produces confidence score + direction.

Supports 23 indicators: 10 production (from bot.indicators) + 13 extended (from bot.research.indicators).
Passports select which indicators to use via INDICATOR_WEIGHTS dict.
"""
from bot import config, indicators
from bot.research import indicators as ext_ind


# Registry: name → callable(df) → (direction, value)
# All callables MUST return (str|None, float) tuple.
INDICATOR_REGISTRY: dict[str, callable] = {
    # === Original 10 production indicators ===
    "ema_trend": lambda df: indicators.calc_ema_trend(df),
    "macd_signal": lambda df: indicators.calc_macd(df),
    "rsi_position": lambda df: indicators.calc_rsi_signal(df),
    "rsi_divergence": lambda df: (indicators.detect_rsi_divergence(df), 50.0),
    "bb_position": lambda df: indicators.calc_bollinger(df),
    "volume_spike": lambda df: (
        "LONG" if indicators.calc_volume_spike(df)[0] else None,
        indicators.calc_volume_spike(df)[1],
    ),
    "pressure": lambda df: indicators.calc_pressure(df),
    "candle_direction": lambda df: (indicators.calc_candle_direction(df), 50.0),
    "donchian_signal": lambda df: indicators.calc_donchian_channel(df),
    "obv_signal": lambda df: indicators.calc_obv_signal(df),
    # === 13 extended indicators from research ===
    "stochrsi": ext_ind.calc_stochrsi,
    "obv_trend": ext_ind.calc_obv_trend,
    "ichimoku": ext_ind.calc_ichimoku,
    "vwap_deviation": ext_ind.calc_vwap_deviation,
    "keltner": ext_ind.calc_keltner,
    "donchian": ext_ind.calc_donchian,
    "heikin_ashi": ext_ind.calc_heikin_ashi,
    "williams_r": ext_ind.calc_williams_r,
    "cci": ext_ind.calc_cci,
    "mfi": ext_ind.calc_mfi,
    "hull_ma": ext_ind.calc_hull_ma,
    "supertrend": ext_ind.calc_supertrend,
    "pivot_points": ext_ind.calc_pivot_points,
}

# Non-directional indicators — confirm dominant direction but don't vote independently
NON_DIRECTIONAL = {"volume_spike"}

# Indicators added after initial deployment — default weight=0 to avoid
# affecting existing passports that don't declare them in INDICATOR_WEIGHTS.
EXTENDED_INDICATOR_NAMES = {
    "donchian_signal", "obv_signal",
    "stochrsi", "obv_trend", "ichimoku", "vwap_deviation",
    "keltner", "donchian", "heikin_ashi", "williams_r",
    "cci", "mfi", "hull_ma", "supertrend", "pivot_points",
}


def score_confluence(df, btc_trend="Sideways"):
    """
    Run weighted indicator voting using the registry.

    Args:
        df: DataFrame with columns [open, high, low, close, volume]
        btc_trend: 'Sideways', 'Uptrend', 'Downtrend', 'TREND_UP', 'TREND_DOWN', etc.

    Returns:
        dict with keys: direction, confidence, leverage, risk_reward, signals, go,
                       btc_trend, raw_confidence, counter_trend_penalty, atr
    """
    if len(df) < 55:
        return _no_signal("Insufficient data")

    indicators.add_atr(df, period=14)

    active_weights = getattr(config, 'INDICATOR_WEIGHTS', {})
    is_reversal = active_weights.get('REVERSAL_MODE', False)

    # Compute all active indicators
    long_score = 0.0
    short_score = 0.0
    total_weight = 0.0
    signals_detail = {}
    dominant_volume = False

    for name, fn in INDICATOR_REGISTRY.items():
        # Determine weight for this indicator
        w = active_weights.get(name, 1.0)

        # Extended indicators default to 0 if not explicitly declared
        if name in EXTENDED_INDICATOR_NAMES and name not in active_weights:
            w = 0.0

        if w <= 0:
            continue

        # REVERSAL_MODE: suppress trend-following indicators
        if is_reversal and name in ("ema_trend", "macd_signal"):
            continue

        try:
            direction, value = fn(df)
        except Exception:
            direction, value = None, 0.0

        # REVERSAL_MODE: force RSI neutral if not directional
        if is_reversal and name == "rsi_position" and direction not in ("LONG", "SHORT"):
            direction = "NEUTRAL"

        signals_detail[name] = {"direction": direction, "value": value}

        # Non-directional: confirms dominant direction
        if name in NON_DIRECTIONAL:
            if direction is not None:
                dominant_volume = True
            continue

        total_weight += w
        if direction == "LONG":
            long_score += w
        elif direction == "SHORT":
            short_score += w

    # Volume spike confirms dominant direction
    if dominant_volume and "volume_spike" in active_weights:
        vol_w = active_weights.get("volume_spike", 1.0)
        if vol_w > 0:
            if long_score > short_score:
                total_weight += vol_w
                long_score += vol_w
            elif short_score > long_score:
                total_weight += vol_w
                short_score += vol_w

    if total_weight == 0:
        return _no_signal("Zero total weight")

    # Determine direction and raw confidence
    if long_score > short_score:
        direction = "LONG"
        raw_confidence = (long_score / total_weight) * 100
    elif short_score > long_score:
        direction = "SHORT"
        raw_confidence = (short_score / total_weight) * 100
    else:
        return _no_signal("No directional consensus")

    # Cap raw confidence to prevent late-entry false consensus
    confidence_cap = getattr(config, 'CONFIDENCE_CAP', 100)
    raw_confidence = min(raw_confidence, confidence_cap)

    # Apply BTC trend filter
    btc_weight = config.BTC_TREND_WEIGHTS.get(btc_trend, 1.0)
    confidence = raw_confidence * btc_weight

    # Apply counter-trend penalty
    ctp = getattr(config, 'COUNTER_TREND_PENALTY', {})
    ct_penalty = ctp.get(btc_trend, 1.0)
    is_counter = (
        (btc_trend == "TREND_UP" and direction == "SHORT") or
        (btc_trend == "TREND_DOWN" and direction == "LONG")
    )
    if is_counter:
        confidence *= ct_penalty

    # Determine leverage tier
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
    """Map confidence score to leverage and R:R."""
    for min_c, max_c, lev, rr in config.LEVERAGE_TIERS:
        if min_c <= confidence <= max_c:
            return lev, rr
    return config.LEVERAGE_TIERS[0][2], config.LEVERAGE_TIERS[0][3]


def _no_signal(reason=""):
    return {
        "direction": None,
        "confidence": 0,
        "leverage": 0,
        "risk_reward": 0,
        "signals": {},
        "go": False,
        "btc_trend": None,
        "raw_confidence": 0,
        "reason": reason,
    }
```

- [ ] **Step 4: Run all tests to verify nothing is broken**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All 697+ existing tests pass, plus new registry tests pass.

- [ ] **Step 5: Commit**

```bash
git add bot/scorer.py tests/test_scorer_registry.py
git commit -m "refactor: scorer.py registry pattern with 23 indicators

Port 13 extended indicators from research into production scorer.
All passports can now use any of 23 indicators via INDICATOR_WEIGHTS.
Extended indicators default to weight=0 for backward compatibility.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Update extended_scorer.py to use shared registry

**Files:**
- Modify: `bot/research/extended_scorer.py`
- Test: `tests/test_extended_scorer_compat.py`

Now that production scorer has the registry, extended_scorer should import from it to avoid duplication.

- [ ] **Step 1: Write backward compatibility test**

Create `tests/test_extended_scorer_compat.py`:

```python
"""Verify extended_scorer still works after registry refactor."""
import pandas as pd
import numpy as np
import pytest
from bot import config
from bot.research.extended_scorer import score_extended, INDICATOR_REGISTRY as EXT_REGISTRY
from bot.scorer import INDICATOR_REGISTRY as PROD_REGISTRY


@pytest.fixture(autouse=True)
def reset_config():
    orig = {k: getattr(config, k) for k in ['CONFIDENCE_CAP', 'BTC_TREND_WEIGHTS', 'COUNTER_TREND_PENALTY']}
    yield
    for k, v in orig.items():
        setattr(config, k, v)


def _make_df(n=100):
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        'open': close - np.random.rand(n) * 0.3,
        'high': close + np.random.rand(n) * 0.5,
        'low': close - np.random.rand(n) * 0.5,
        'close': close,
        'volume': np.random.rand(n) * 1000 + 500,
        'timestamp': pd.date_range('2026-01-01', periods=n, freq='1h'),
    })


class TestExtendedScorerCompat:
    def test_extended_registry_superset_of_production(self):
        """Extended scorer's registry should contain all production indicators."""
        for name in PROD_REGISTRY:
            assert name in EXT_REGISTRY, f"Extended missing: {name}"

    def test_score_extended_still_works(self):
        """score_extended() still produces valid output."""
        df = _make_df()
        weights = {'ema_trend': 1.0, 'bb_position': 1.0, 'stochrsi': 2.0}
        result = score_extended(df, weights, btc_trend="Sideways")
        assert 'confidence' in result
        assert 'direction' in result
        assert 'go' in result

    def test_research_pipeline_weights_work(self):
        """Weights from actual research winners produce valid results."""
        df = _make_df()
        # rsi_bb_reversal winner config
        weights = {'rsi_position': 2.0, 'bb_position': 2.0, 'volume_spike': 1.0}
        result = score_extended(df, weights, btc_trend="Sideways")
        assert isinstance(result['confidence'], (int, float))
```

- [ ] **Step 2: Update extended_scorer.py to import from production registry**

Modify `bot/research/extended_scorer.py` — import `INDICATOR_REGISTRY` from `bot.scorer` and use it. Keep `score_extended()` function signature unchanged for research pipeline compatibility.

```python
"""Extended scorer for the Strategy Research Engine.

Thin wrapper around the production scorer's registry. Provides score_extended()
with the same interface the research pipeline expects.
"""
from __future__ import annotations

from typing import Optional

from bot import config
from bot.scorer import INDICATOR_REGISTRY


def score_extended(
    df,
    weights: dict[str, float],
    btc_trend: str = "Sideways",
    confidence_threshold: float = 50.0,
) -> dict:
    """Run weighted voting using the indicator registry.

    Args:
        df: OHLCV DataFrame
        weights: indicator_name → weight (0 = skip)
        btc_trend: "Sideways", "Uptrend", "Downtrend"
        confidence_threshold: minimum confidence to fire signal

    Returns:
        dict with direction, confidence, leverage, risk_reward, go, signals
    """
    if len(df) < 55:
        return _no_signal("Insufficient data")

    if not weights:
        return _no_signal("No weights provided")

    active = {k: v for k, v in weights.items() if v > 0 and k in INDICATOR_REGISTRY}
    if not active:
        return _no_signal("No active indicators")

    NON_DIRECTIONAL = {"volume_spike"}

    long_score = 0.0
    short_score = 0.0
    total_weight = 0.0
    signals_detail = {}
    dominant_volume = False

    for name, w in active.items():
        if name not in INDICATOR_REGISTRY:
            continue
        try:
            direction, value = INDICATOR_REGISTRY[name](df)
        except Exception:
            direction, value = None, 0.0

        signals_detail[name] = {"direction": direction, "value": value}

        if name in NON_DIRECTIONAL:
            if direction is not None:
                dominant_volume = True
            continue

        total_weight += w
        if direction == "LONG":
            long_score += w
        elif direction == "SHORT":
            short_score += w

    if dominant_volume and "volume_spike" in active:
        vol_w = active["volume_spike"]
        if long_score > short_score:
            total_weight += vol_w
            long_score += vol_w
        elif short_score > long_score:
            total_weight += vol_w
            short_score += vol_w

    if total_weight == 0:
        return _no_signal("Zero total weight")

    if long_score > short_score:
        direction = "LONG"
        raw_confidence = (long_score / total_weight) * 100
    elif short_score > long_score:
        direction = "SHORT"
        raw_confidence = (short_score / total_weight) * 100
    else:
        return _no_signal("No directional consensus")

    confidence_cap = getattr(config, 'CONFIDENCE_CAP', 100)
    raw_confidence = min(raw_confidence, confidence_cap)

    confidence = min(100.0, max(0.0, raw_confidence * config.BTC_TREND_WEIGHTS.get(btc_trend, 1.0)))

    ctp = getattr(config, 'COUNTER_TREND_PENALTY', {})
    ct_penalty = ctp.get(btc_trend, 1.0)
    is_counter = (
        (btc_trend == "TREND_UP" and direction == "SHORT") or
        (btc_trend == "TREND_DOWN" and direction == "LONG")
    )
    if is_counter:
        confidence *= ct_penalty

    go = confidence >= confidence_threshold

    return {
        "direction": direction if go else None,
        "confidence": round(confidence, 1),
        "leverage": _leverage_from_confidence(confidence),
        "risk_reward": _rr_from_confidence(confidence),
        "signals": signals_detail,
        "go": go,
        "btc_trend": btc_trend,
        "raw_confidence": round(raw_confidence, 1),
    }


def _leverage_from_confidence(confidence: float) -> int:
    if confidence >= 70:
        return 7
    if confidence >= 61:
        return 5
    if confidence >= 54:
        return 4
    return 1


def _rr_from_confidence(confidence: float) -> float:
    if confidence >= 80:
        return 3.0
    if confidence >= 70:
        return 2.5
    if confidence >= 60:
        return 2.0
    return 1.5


def _no_signal(reason: str = "") -> dict:
    return {
        "direction": None,
        "confidence": 0,
        "leverage": 0,
        "risk_reward": 0,
        "signals": {},
        "go": False,
        "btc_trend": None,
        "raw_confidence": 0,
        "reason": reason,
    }
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass including new compat tests.

- [ ] **Step 4: Commit**

```bash
git add bot/research/extended_scorer.py tests/test_extended_scorer_compat.py
git commit -m "refactor: extended_scorer imports from production registry

Eliminates duplicate indicator registry. Research pipeline now uses
the same INDICATOR_REGISTRY as production scorer.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Update passport_runner.py _save_config for new indicators

**Files:**
- Modify: `bot/passport_runner.py` (lines 505-520)

The `_save_config()` method snapshots config keys before applying passport overrides. Extended indicators may have config keys that need snapshotting (the override_keys param already handles this, but let's be explicit).

- [ ] **Step 1: Verify _save_config already handles dynamic keys**

Read `bot/passport_runner.py:505-520`. The `override_keys` param already adds any passport-specific keys to the snapshot list. No code change needed — the existing `all_override_keys = set(passport.config_overrides.keys()) | set(regime_overrides.keys())` at line 259 already captures all keys including new indicator params.

- [ ] **Step 2: Write a test to confirm extended indicator passports work end-to-end**

Add to `tests/test_scorer_registry.py`:

```python
class TestPassportRunnerIntegration:
    """Verify passport_runner can apply extended indicator weights."""

    def test_config_override_with_extended_weights(self):
        """Simulate passport_runner applying weights with extended indicators."""
        from bot import config
        original_weights = config.INDICATOR_WEIGHTS.copy()

        # Simulate passport override
        new_weights = {
            'rsi_position': 1.0, 'bb_position': 1.5, 'stochrsi': 2.5,
            'ema_trend': 0.0, 'macd_signal': 0.0, 'rsi_divergence': 0.0,
            'volume_spike': 0.0, 'pressure': 0.0, 'candle_direction': 0.0,
        }
        config.INDICATOR_WEIGHTS = new_weights

        df = _make_df(100)
        result = score_confluence(df, btc_trend="Sideways")
        assert 'confidence' in result

        # Restore
        config.INDICATOR_WEIGHTS = original_weights
```

- [ ] **Step 3: Run tests and commit**

Run: `uv run pytest tests/test_scorer_registry.py -v`

```bash
git add tests/test_scorer_registry.py
git commit -m "test: passport_runner integration with extended indicators

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Re-enable all 17 disabled passports

**Files:**
- Modify: All 17 disabled passport JSON files

Set `"enabled": true` in every disabled passport. Also bump version to indicate re-enable with confidence cap protection.

- [ ] **Step 1: Re-enable all disabled passports via script**

```python
# Run this Python script:
import json, glob

disabled_files = []
for f in sorted(glob.glob('passports/**/*.json', recursive=True)):
    with open(f) as fh:
        data = json.load(fh)
    if data.get('enabled') is False:
        data['enabled'] = True
        # Bump version
        ver = data.get('version', '0.1')
        parts = ver.split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        data['version'] = '.'.join(parts)
        # Add changelog entry
        if 'changelog' not in data:
            data['changelog'] = []
        data['changelog'].append({
            'version': data['version'],
            'date': '2026-04-14',
            'description': 'Re-enabled with confidence cap (80) + regime gating protection. Fresh start $500 equity.'
        })
        with open(f, 'w') as fh:
            json.dump(data, fh, indent=2)
            fh.write('\n')
        disabled_files.append(f)
        print(f"Re-enabled: {data['name']} → v{data['version']}")

print(f"\nTotal re-enabled: {len(disabled_files)}")
```

- [ ] **Step 2: Ensure all passports have valid INDICATOR_WEIGHTS with all required keys**

For passports using standard indicators, ensure all 8 original keys are present (missing keys cause KeyError). Extended indicator keys don't need to be present — they default to 0.

```python
import json, glob

REQUIRED_KEYS = [
    'ema_trend', 'macd_signal', 'rsi_position', 'rsi_divergence',
    'bb_position', 'volume_spike', 'pressure', 'candle_direction',
]

for f in sorted(glob.glob('passports/**/*.json', recursive=True)):
    with open(f) as fh:
        data = json.load(fh)
    weights = data.get('config_overrides', {}).get('INDICATOR_WEIGHTS', {})
    if not weights:
        continue
    missing = [k for k in REQUIRED_KEYS if k not in weights]
    if missing:
        for k in missing:
            weights[k] = 0.0
        data['config_overrides']['INDICATOR_WEIGHTS'] = weights
        with open(f, 'w') as fh:
            json.dump(data, fh, indent=2)
            fh.write('\n')
        print(f"Fixed {data['name']}: added {missing}")
```

- [ ] **Step 3: Run existing passport schema tests**

Run: `uv run pytest tests/test_regime_gating_integration.py -v --tb=short`
Expected: All 104 parametrized tests pass.

- [ ] **Step 4: Commit**

```bash
git add passports/
git commit -m "feat: re-enable all 17 disabled passports

Protected by confidence cap (80), regime gating, and CTP.
Fresh start will reset equity to $500/passport.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Create 12 research winner passports

**Files:**
- Create: 12 new JSON files in `passports/cryptopass-research/`

Create one passport per profitable research family, using the best-performing config from each.

The 12 families and their configs (from research_experiments.db):

| # | Name | File | Conf | Active Indicators | Extra Config |
|---|------|------|------|-------------------|-------------|
| 1 | RSIMomentumGen2 | rsi_momentum_gen2.json | 65 | ema_trend=0.5, rsi_position=2.0, rsi_divergence=1.5 | RSI_PERIOD=10, VOL_THRESH=1.5 |
| 2 | PressureFlowShort | pressure_flow_short.json | 65 | ema_trend=1.0, pressure=2.5, candle_direction=1.5 | DIRECTION_BIAS=SHORT_ONLY, VOL_THRESH=2.0 |
| 3 | RSIBBReversal | rsi_bb_reversal.json | 60 | rsi_position=2.0, bb_position=2.0, volume_spike=1.0 | RSI_PERIOD=10, BB_PERIOD=15, BB_STD=1.5 |
| 4 | HiddenGemGen2 | hidden_gem_gen2.json | 70 | ema_trend=1.0, bb_position=1.0, volume_spike=2.0 | EMA_FAST=8, EMA_SLOW=45, BB_PERIOD=18, VOL_THRESH=1.5 |
| 5 | PivotBounce | pivot_bounce.json | 65 | rsi_position=1.0, bb_position=1.5, pivot_points=2.0 | — |
| 6 | StochReversal | stoch_reversal.json | 65 | rsi_position=1.5, bb_position=1.0, stochrsi=2.5 | — |
| 7 | VWAPDeviation | vwap_deviation.json | 65 | rsi_position=1.0, bb_position=1.5, vwap_deviation=2.5 | — |
| 8 | WilliamsReversal | williams_reversal.json | 65 | rsi_position=1.5, bb_position=1.0, williams_r=2.5 | — |
| 9 | SupertrendFollow | supertrend_follow.json | 55 | ema_trend=1.5, supertrend=3.0 | — |
| 10 | DonchianBreakoutGen2 | donchian_breakout_gen2.json | 60 | ema_trend=1.5, volume_spike=1.0, donchian=2.5 | — |
| 11 | KeltnerBreakout | keltner_breakout.json | 60 | ema_trend=1.0, volume_spike=2.0, keltner=2.5 | VOL_THRESH=1.5 |
| 12 | OBVTrendGen2 | obv_trend_gen2.json | 55 | ema_trend=1.5, volume_spike=1.0, obv_trend=2.5 | — |

- [ ] **Step 1: Create all 12 passport JSON files**

Use a script to generate them with consistent format. Each passport:
- `enabled: true`
- `version: "1.0"` (first production version of research winner)
- `changelog` with research backtest metrics
- All 8 standard indicator keys in INDICATOR_WEIGHTS (zeroed if unused) + extended keys
- `active_regimes: null` (trade in all regimes initially)
- `regime_params: {}` (no regime-specific tuning yet)
- Research family passports that use DIRECTION_BIAS get it at top level in config_overrides

```python
import json, os

PASSPORTS = [
    {
        "name": "RSIMomentumGen2", "emoji": "📈", "file": "rsi_momentum_gen2.json",
        "description": "RSI momentum with EMA context. Research winner: +6.6% median return, PF=1.51, Sharpe=1.52. Uses RSI position + RSI divergence as primary with EMA trend as lightweight context.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 65, "RSI_PERIOD": 10, "VOLUME_SPIKE_THRESHOLD": 1.5,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.5, "macd_signal": 0.0, "rsi_position": 2.0,
                "rsi_divergence": 1.5, "bb_position": 0.0, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        },
        "backtest": {"median_return": 6.6, "profit_factor": 1.51, "sharpe": 1.52, "folds": [10.2, 3.0]},
    },
    {
        "name": "PressureFlowShort", "emoji": "🔻", "file": "pressure_flow_short.json",
        "description": "SHORT-only pressure flow. Research winner: +4.1% median return, PF=1.92. Uses pressure + candle direction with EMA context. SHORT_ONLY direction bias.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 65, "VOLUME_SPIKE_THRESHOLD": 2.0,
            "DIRECTION_BIAS": "SHORT_ONLY",
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 0.0,
                "pressure": 2.5, "candle_direction": 1.5,
            }
        },
        "backtest": {"median_return": 4.1, "profit_factor": 1.92, "sharpe": 0.75, "folds": [-1.1, 9.3]},
    },
    {
        "name": "RSIBBReversal", "emoji": "🔄", "file": "rsi_bb_reversal.json",
        "description": "RSI + Bollinger reversal strategy. Research winner: +3.8% median return, PF=1.33. Mean-reversion using RSI oversold/overbought at BB extremes with volume confirmation.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60, "RSI_PERIOD": 10, "BB_PERIOD": 15, "BB_STD": 1.5,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 2.0,
                "rsi_divergence": 0.0, "bb_position": 2.0, "volume_spike": 1.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        },
        "backtest": {"median_return": 3.8, "profit_factor": 1.33, "sharpe": 0.96, "folds": [3.4, 4.2]},
    },
    {
        "name": "HiddenGemGen2", "emoji": "💎", "file": "hidden_gem_gen2.json",
        "description": "Enhanced HiddenGem variant. Research winner: +3.0% median return. Tuned EMA (8/45) + BB (18) + Volume (1.5x) — tighter parameters than original HiddenGem.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 70, "EMA_FAST": 8, "EMA_SLOW": 45,
            "BB_PERIOD": 18, "VOLUME_SPIKE_THRESHOLD": 1.5,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        },
        "backtest": {"median_return": 3.0, "profit_factor": 1.11, "sharpe": 1.36, "folds": [-4.0, 10.0]},
    },
    {
        "name": "PivotBounce", "emoji": "📍", "file": "pivot_bounce.json",
        "description": "Pivot point bounce strategy. Research winner: +2.3% median return, PF=2.06. Enters near S1/S2 (LONG) or R1/R2 (SHORT) pivot levels with RSI + BB confirmation.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 65,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 1.0,
                "rsi_divergence": 0.0, "bb_position": 1.5, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "pivot_points": 2.0,
            }
        },
        "backtest": {"median_return": 2.3, "profit_factor": 2.06, "sharpe": 1.28, "folds": [-1.7, 6.4]},
    },
    {
        "name": "StochReversal", "emoji": "🌀", "file": "stoch_reversal.json",
        "description": "Stochastic RSI reversal. Research winner: +2.3% median return, PF=2.06, Sharpe=1.28. Uses StochRSI crossover from oversold/overbought with RSI + BB confirmation.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 65,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 1.5,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "stochrsi": 2.5,
            }
        },
        "backtest": {"median_return": 2.3, "profit_factor": 2.06, "sharpe": 1.28, "folds": [-1.7, 6.4]},
    },
    {
        "name": "VWAPDeviation", "emoji": "📊", "file": "vwap_deviation_strat.json",
        "description": "VWAP z-score mean reversion. Research winner: +2.3% median return, PF=2.06. Enters when price deviates >1.5σ from rolling VWAP with RSI + BB confirmation.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 65,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 1.0,
                "rsi_divergence": 0.0, "bb_position": 1.5, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "vwap_deviation": 2.5,
            }
        },
        "backtest": {"median_return": 2.3, "profit_factor": 2.06, "sharpe": 1.28, "folds": [-1.7, 6.4]},
    },
    {
        "name": "WilliamsReversal", "emoji": "📉", "file": "williams_reversal.json",
        "description": "Williams %R reversal. Research winner: +2.3% median return, PF=2.06. Enters at Williams %R extremes (<-80 LONG, >-20 SHORT) with RSI + BB confirmation.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 65,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 1.5,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "williams_r": 2.5,
            }
        },
        "backtest": {"median_return": 2.3, "profit_factor": 2.06, "sharpe": 1.28, "folds": [-1.7, 6.4]},
    },
    {
        "name": "SupertrendFollow", "emoji": "🚀", "file": "supertrend_follow.json",
        "description": "ATR-based Supertrend follower. Research winner: +0.9% median return, Sharpe=2.06. Follows ATR supertrend direction with EMA context. Low return but high Sharpe — very consistent.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 55,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "supertrend": 3.0,
            }
        },
        "backtest": {"median_return": 0.9, "profit_factor": 1.02, "sharpe": 2.06, "folds": [-2.5, 4.3]},
    },
    {
        "name": "DonchianBreakoutGen2", "emoji": "🔔", "file": "donchian_breakout_gen2.json",
        "description": "Enhanced Donchian channel breakout using research donchian indicator. Research winner: +0.6% return, Sharpe=2.30. Uses EMA + volume spike + donchian channel.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 1.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "donchian": 2.5,
            }
        },
        "backtest": {"median_return": 0.6, "profit_factor": 1.01, "sharpe": 2.30, "folds": [-3.8, 4.9]},
    },
    {
        "name": "KeltnerBreakout", "emoji": "📐", "file": "keltner_breakout.json",
        "description": "Keltner channel breakout. Research winner: +0.6% return, Sharpe=2.30. Enters on upper/lower Keltner band breakouts with EMA + volume confirmation.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60, "VOLUME_SPIKE_THRESHOLD": 1.5,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "keltner": 2.5,
            }
        },
        "backtest": {"median_return": 0.6, "profit_factor": 1.01, "sharpe": 2.30, "folds": [-3.8, 4.9]},
    },
    {
        "name": "OBVTrendGen2", "emoji": "📶", "file": "obv_trend_gen2.json",
        "description": "OBV linear regression trend. Research winner: +0.0% median return (breakeven), Sharpe=2.21. Uses OBV slope for accumulation/distribution detection. Experimental — needs regime tuning.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 55,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 1.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "obv_trend": 2.5,
            }
        },
        "backtest": {"median_return": 0.0, "profit_factor": 1.00, "sharpe": 2.21, "folds": [-4.4, 4.4]},
    },
]

os.makedirs('passports/cryptopass-research', exist_ok=True)

for p in PASSPORTS:
    passport_data = {
        "name": p["name"],
        "emoji": p["emoji"],
        "enabled": True,
        "version": "1.0",
        "changelog": [{
            "version": "1.0",
            "date": "2026-04-14",
            "description": f"Research Phase 4 winner promoted to paper trading. 180d walk-forward: {p['backtest']['median_return']:+.1f}% median return, PF={p['backtest']['profit_factor']:.2f}, Sharpe={p['backtest']['sharpe']:.2f}. Folds: {p['backtest']['folds']}.",
        }],
        "description": p["description"],
        "config_overrides": p["config_overrides"],
        "active_regimes": None,
        "regime_params": {},
    }

    filepath = f"passports/cryptopass-research/{p['file']}"
    with open(filepath, 'w') as f:
        json.dump(passport_data, f, indent=2)
        f.write('\n')
    print(f"Created: {filepath} — {p['name']}")
```

- [ ] **Step 2: Validate all new passports pass schema tests**

Run: `uv run pytest tests/test_regime_gating_integration.py -v --tb=short`

- [ ] **Step 3: Commit**

```bash
git add passports/cryptopass-research/
git commit -m "feat: promote 12 research Phase 4 winners to paper trading

Research families promoted (180d walk-forward validated):
- RSIMomentumGen2 (+6.6%, PF=1.51) — top performer
- PressureFlowShort (+4.1%, PF=1.92) — SHORT-only bear strategy
- RSIBBReversal (+3.8%, PF=1.33) — mean-reversion
- HiddenGemGen2 (+3.0%) — tuned variant of HiddenGem lineage
- PivotBounce, StochReversal, VWAPDeviation, WilliamsReversal (+2.3%, PF=2.06)
- SupertrendFollow (+0.9%, Sharpe=2.06) — high consistency
- DonchianBreakoutGen2, KeltnerBreakout (+0.6%, Sharpe=2.30)
- OBVTrendGen2 (breakeven, Sharpe=2.21) — experimental

8 use extended indicators (stochrsi, pivot_points, vwap_deviation,
williams_r, supertrend, donchian, keltner, obv_trend) now available
via registry-based scorer.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Fork big-loss passports into enhanced variants

**Files:**
- Create: Enhanced variant JSON files in `passports/cryptopass-research/`

For each disabled passport that was losing money, create an enhanced "Gen2" variant that inherits from the original but applies lessons learned (selectivity principle, regime gating, confidence cap). This tracks lineage — we know how far we've researched each family.

Big-loss passports and their enhancement thesis:

| Original | Problem | Enhanced Approach |
|----------|---------|-------------------|
| Pumpradar Dynamic | All 8 indicators active = diluted confidence | Strip to 3 best (ema+bb+vol), add regime gating |
| Pumpradar Momentum | Same dilution problem | Strip to ema+rsi+pressure, regime gate |
| BollingerBreakout v1/v2/v3 | 3 variants all lost | Keep bb+vol+pressure, raise confidence threshold |
| TrendMomentum | ema+macd+rsi too noisy | Pure ema+rsi only, raise threshold |
| DualMA Crossover | Only 2 indicators, too few signals | Add BB for context |
| MinimalEdge | Only ema+vol, no edge | Add candle_direction for timing |
| PureTrend | Only ema, zero selectivity | Add supertrend for confirmation |

- [ ] **Step 1: Create enhanced variant passports**

Script to create 7 enhanced variants (one per big-loss family):

```python
import json, os

ENHANCED = [
    {
        "name": "DynamicGen2", "emoji": "⚡", "file": "dynamic_gen2.json",
        "parent": "Pumpradar Dynamic",
        "description": "Enhanced Dynamic: stripped from 8→3 indicators (selectivity principle). Parent had all 8 active = diluted confidence = low WR. Gen2 uses ema+bb+volume only.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.5, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        },
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "regime_params": {
            "TREND_UP": {"DIRECTION_BIAS": "LONG_ONLY"},
            "TREND_DOWN": {"DIRECTION_BIAS": "SHORT_ONLY", "CONFIDENCE_THRESHOLD": 65},
        },
    },
    {
        "name": "MomentumGen2", "emoji": "💨", "file": "momentum_gen2.json",
        "parent": "Pumpradar Momentum",
        "description": "Enhanced Momentum: 8→3 indicators. Uses ema+rsi+pressure (momentum + flow). Parent diluted with all 8. Regime-gated with direction bias.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 2.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 0.0,
                "pressure": 1.5, "candle_direction": 0.0,
            }
        },
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "regime_params": {
            "TREND_UP": {"DIRECTION_BIAS": "LONG_ONLY"},
            "TREND_DOWN": {"DIRECTION_BIAS": "SHORT_ONLY"},
        },
    },
    {
        "name": "BollingerBreakoutGen4", "emoji": "🎯", "file": "bollinger_breakout_gen4.json",
        "parent": "BollingerBreakout v1/v2/v3",
        "description": "Enhanced BB Breakout: 3 prior versions all negative. Gen4 raises threshold to 65 and adds regime gating. BB+vol+pressure is a sound combo — problem was low confidence threshold letting noise through.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 65, "BB_PERIOD": 20, "BB_STD": 2.0,
            "VOLUME_SPIKE_THRESHOLD": 2.0,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 2.0, "volume_spike": 1.5,
                "pressure": 1.5, "candle_direction": 0.0,
            }
        },
        "active_regimes": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP"],
        "regime_params": {
            "TREND_UP": {"DIRECTION_BIAS": "LONG_ONLY"},
            "TREND_DOWN": {"DIRECTION_BIAS": "SHORT_ONLY"},
            "HIGH_VOL_CHOP": {"CONFIDENCE_THRESHOLD": 70},
        },
    },
    {
        "name": "TrendMomentumGen2", "emoji": "🌊", "file": "trend_momentum_gen2.json",
        "parent": "TrendMomentum",
        "description": "Enhanced TrendMomentum: dropped MACD (noisy), kept ema+rsi only. Cleaner momentum signal with regime gating. Parent used ema+macd+rsi — MACD added noise.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 2.0, "macd_signal": 0.0, "rsi_position": 2.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        },
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "regime_params": {
            "TREND_UP": {"DIRECTION_BIAS": "LONG_ONLY"},
            "TREND_DOWN": {"DIRECTION_BIAS": "SHORT_ONLY"},
        },
    },
    {
        "name": "DualMAGen2", "emoji": "✌️", "file": "dual_ma_gen2.json",
        "parent": "DualMA Crossover",
        "description": "Enhanced DualMA: original had only ema+vol (too few signals). Gen2 adds BB for mean-reversion context, creating ema+vol+bb combo.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 1.5,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        },
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "regime_params": {
            "TREND_UP": {"DIRECTION_BIAS": "LONG_ONLY"},
            "TREND_DOWN": {"DIRECTION_BIAS": "SHORT_ONLY"},
        },
    },
    {
        "name": "MinimalEdgeGen2", "emoji": "🎲", "file": "minimal_edge_gen2.json",
        "parent": "MinimalEdge",
        "description": "Enhanced MinimalEdge: original had only ema+vol. Gen2 adds candle_direction for entry timing. Minimal but intentional — tests whether 3 indicators with timing can beat 2 without.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 60,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 1.5,
                "pressure": 0.0, "candle_direction": 1.0,
            }
        },
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "regime_params": {
            "TREND_UP": {"DIRECTION_BIAS": "LONG_ONLY"},
            "TREND_DOWN": {"DIRECTION_BIAS": "SHORT_ONLY"},
        },
    },
    {
        "name": "PureTrendGen2", "emoji": "🎋", "file": "pure_trend_gen2.json",
        "parent": "PureTrend",
        "description": "Enhanced PureTrend: original used only EMA (zero selectivity). Gen2 adds supertrend (ATR-based) for confirmation. EMA determines direction, supertrend confirms momentum.",
        "config_overrides": {
            "CONFIDENCE_THRESHOLD": 55,
            "USE_ATR_EXITS": False, "USE_TRAILING_STOP": False,
            "MAX_OPEN_POSITIONS_PER_PASSPORT": 50, "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.5, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 0.0,
                "pressure": 0.0, "candle_direction": 0.0,
                "supertrend": 2.5,
            }
        },
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "regime_params": {
            "TREND_UP": {"DIRECTION_BIAS": "LONG_ONLY"},
            "TREND_DOWN": {"DIRECTION_BIAS": "SHORT_ONLY"},
        },
    },
]

for p in ENHANCED:
    passport_data = {
        "name": p["name"],
        "emoji": p["emoji"],
        "enabled": True,
        "version": "1.0",
        "changelog": [{
            "version": "1.0",
            "date": "2026-04-14",
            "description": f"Enhanced fork of {p['parent']}. Applied selectivity principle + regime gating. Inherits family lineage for research tracking.",
        }],
        "description": p["description"],
        "lineage": {"parent": p["parent"], "generation": 2},
        "config_overrides": p["config_overrides"],
        "active_regimes": p.get("active_regimes"),
        "regime_params": p.get("regime_params", {}),
    }

    filepath = f"passports/cryptopass-research/{p['file']}"
    with open(filepath, 'w') as f:
        json.dump(passport_data, f, indent=2)
        f.write('\n')
    print(f"Created: {filepath} — {p['name']} (fork of {p['parent']})")
```

- [ ] **Step 2: Validate and commit**

Run: `uv run pytest tests/ -v --tb=short -q`

```bash
git add passports/cryptopass-research/
git commit -m "feat: fork 7 big-loss passports into enhanced Gen2 variants

Lineage tracking: each variant inherits from its parent strategy.
Applied selectivity principle (strip to 2-3 indicators) + regime
gating (direction bias per BTC trend).

- DynamicGen2 ← Pumpradar Dynamic (8→3 indicators)
- MomentumGen2 ← Pumpradar Momentum (8→3)
- BollingerBreakoutGen4 ← BB v1/v2/v3 (raised threshold)
- TrendMomentumGen2 ← TrendMomentum (dropped MACD)
- DualMAGen2 ← DualMA (added BB)
- MinimalEdgeGen2 ← MinimalEdge (added candle)
- PureTrendGen2 ← PureTrend (added supertrend)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Update FINDINGS.md and VERSIONS.md

**Files:**
- Modify: `docs/FINDINGS.md`
- Modify: `passports/VERSIONS.md`

- [ ] **Step 1: Update FINDINGS.md**

Add new section documenting:
- Scorer registry refactor (10→23 indicators)
- Research Phase 4 results (50 Stage 2 survivors, 32 profitable, 12 families)
- 12 research winners promoted
- 7 big-loss passports forked into Gen2 variants
- Total passport count and strategy coverage per regime

- [ ] **Step 2: Update VERSIONS.md**

Add entries for all new/re-enabled passports with version numbers.

- [ ] **Step 3: Commit docs**

```bash
git add docs/FINDINGS.md passports/VERSIONS.md
git commit -m "docs: update FINDINGS.md and VERSIONS.md for passport expansion

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: Run full test suite + deploy to VPS

**Files:**
- No code changes — deployment only

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```
Expected: All tests pass (700+).

- [ ] **Step 2: Push to origin**

```bash
git push origin master
```

- [ ] **Step 3: Deploy to VPS**

```bash
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && systemctl restart cryptopass.service"
```

- [ ] **Step 4: Run fresh start on VPS**

```bash
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && python scripts/fresh_start.py --confirm"
ssh fight-tres "systemctl restart cryptopass.service"
```

- [ ] **Step 5: Validate VPS deployment (runbook checklist)**

```bash
# 1. Service running
ssh fight-tres "systemctl status cryptopass.service --no-pager"
# 2. Check loaded passports count (should be ~38)
ssh fight-tres "journalctl -u cryptopass.service -n 50 --no-pager" | grep -i "passport\|loaded"
# 3. Verify extended indicators available
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && python -c 'from bot.scorer import INDICATOR_REGISTRY; print(len(INDICATOR_REGISTRY), \"indicators\")'"
# 4. Wait for first scan cycle, check for signals
ssh fight-tres "journalctl -u cryptopass.service -n 200 --no-pager -f" # watch for 5 min
```

- [ ] **Step 6: Commit deployment marker**

No code change — just verify everything is live and healthy.
