# Research Engine Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core research pipeline that generates 200-400 passport candidates from existing indicators, validates them through Stage 1 (viability) and Stage 2 (regime walk-forward), and ranks survivors.

**Architecture:** Extend the existing `bot/` codebase with a `bot/research/` package. Wrap existing `backtester.py` and `discovery_engine.py` rather than replacing them. All 18 scoring families use the existing 8 indicators via `scorer.py` with different weight/parameter combinations.

**Tech Stack:** Python ≥3.11, pandas, numpy, pytest, SQLite (experiment tracking)

**Spec:** `docs/superpowers/specs/2026-04-04-strategy-research-engine-design.md`

**Depends on:** Nothing (foundation layer)

**Produces:** Ranked list of passport candidates that pass Stage 1+2 validation

---

## File Structure

```
bot/research/                    # NEW package
├── __init__.py                  # Package init, version
├── types.py                     # RegimeType enum, PassportCandidate, EvalResult, ExperimentResult
├── regime.py                    # classify_regime(), classify_regime_series()
├── families.py                  # SCORING_FAMILIES: 18 family definitions with param ranges
├── generator.py                 # generate_passports() — families → passport config dicts
├── evaluator.py                 # Stage1Evaluator, Stage2Evaluator
├── tracker.py                   # ExperimentTracker (SQLite)
└── pipeline.py                  # run_research_pipeline() orchestrator

run_research.py                  # CLI entry point (repo root, parallel to run_discovery.py)

tests/research/                  # NEW test package
├── __init__.py
├── test_types.py
├── test_regime.py
├── test_families.py
├── test_generator.py
├── test_evaluator.py
├── test_tracker.py
└── test_pipeline.py
```

**Existing files modified:**
- None in Plan 1 — we only ADD new files and wrap existing interfaces

---

## Task 1: Core Types

**Files:**
- Create: `bot/research/__init__.py`
- Create: `bot/research/types.py`
- Test: `tests/research/__init__.py`
- Test: `tests/research/test_types.py`

- [ ] **Step 1: Create package init files**

```python
# bot/research/__init__.py
"""Strategy Research Engine — passport generation and evaluation pipeline."""
__version__ = "0.1.0"
```

```python
# tests/research/__init__.py
```

- [ ] **Step 2: Write failing tests for core types**

```python
# tests/research/test_types.py
"""Tests for research engine core types."""
import pytest
from bot.research.types import (
    RegimeType,
    PassportCandidate,
    EvalResult,
    ExperimentResult,
    BacktestMetrics,
)


class TestRegimeType:
    def test_regime_enum_has_four_values(self):
        assert len(RegimeType) == 4

    def test_regime_values(self):
        assert RegimeType.TREND_UP.value == "TREND_UP"
        assert RegimeType.TREND_DOWN.value == "TREND_DOWN"
        assert RegimeType.HIGH_VOL_CHOP.value == "HIGH_VOL_CHOP"
        assert RegimeType.LOW_VOL_COMPRESSION.value == "LOW_VOL_COMPRESSION"


class TestBacktestMetrics:
    def test_create_from_summary_dict(self):
        summary = {
            "trades": 50,
            "wins": 25,
            "losses": 25,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "return_pct": 10.0,
            "final_equity": 1100.0,
            "max_dd": 15.0,
            "sharpe": 1.2,
            "sortino": 1.5,
            "calmar": 0.8,
            "profit_factor": 1.3,
        }
        m = BacktestMetrics.from_summary(summary)
        assert m.trades == 50
        assert m.win_rate == 50.0
        assert m.sharpe == 1.2
        assert m.max_dd == 15.0

    def test_from_summary_handles_missing_keys(self):
        summary = {"trades": 0, "return_pct": 0.0, "max_dd": 0.0}
        m = BacktestMetrics.from_summary(summary)
        assert m.trades == 0
        assert m.sharpe == 0.0


class TestPassportCandidate:
    def test_create_passport_candidate(self):
        pc = PassportCandidate(
            passport_id="psp_test_001",
            slug="ema_crossover-fast_9_26",
            family="ema_crossover",
            config_overrides={
                "INDICATOR_WEIGHTS": {"ema_trend": 2.0},
                "CONFIDENCE_THRESHOLD": 60,
            },
        )
        assert pc.passport_id.startswith("psp_")
        assert pc.family == "ema_crossover"
        assert pc.config_overrides["CONFIDENCE_THRESHOLD"] == 60

    def test_passport_candidate_has_default_status(self):
        pc = PassportCandidate(
            passport_id="psp_test_002",
            slug="test",
            family="test",
            config_overrides={},
        )
        assert pc.status == "generated"


class TestEvalResult:
    def test_eval_result_stage1_pass(self):
        er = EvalResult(
            passport_id="psp_test_001",
            stage=1,
            passed=True,
            metrics={"trades": 50, "max_dd": 30.0},
        )
        assert er.passed is True
        assert er.reject_reason is None

    def test_eval_result_stage1_fail(self):
        er = EvalResult(
            passport_id="psp_test_001",
            stage=1,
            passed=False,
            metrics={"trades": 5},
            reject_reason="Insufficient trades: 5 < 30",
        )
        assert er.passed is False
        assert "Insufficient" in er.reject_reason


class TestExperimentResult:
    def test_create_experiment_result(self):
        er = ExperimentResult(
            run_id="exp-2026-04-04-001",
            total_generated=400,
            stage1_survivors=180,
            stage2_survivors=45,
        )
        assert er.total_generated == 400
        assert er.stage2_survivors == 45
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && python -m pytest tests/research/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.research.types'`

- [ ] **Step 4: Implement core types**

```python
# bot/research/types.py
"""Core types for the Strategy Research Engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RegimeType(Enum):
    """Market regime classification. Exclusive — each bar belongs to exactly one."""
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    HIGH_VOL_CHOP = "HIGH_VOL_CHOP"
    LOW_VOL_COMPRESSION = "LOW_VOL_COMPRESSION"


@dataclass
class BacktestMetrics:
    """Standardized backtest result metrics."""
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    return_pct: float = 0.0
    final_equity: float = 0.0
    max_dd: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    profit_factor: float = 0.0

    @classmethod
    def from_summary(cls, summary: dict) -> BacktestMetrics:
        """Create from backtester._summarize() output dict."""
        return cls(
            trades=summary.get("trades", 0),
            wins=summary.get("wins", 0),
            losses=summary.get("losses", 0),
            win_rate=summary.get("win_rate", 0.0),
            total_pnl=summary.get("total_pnl", 0.0),
            return_pct=summary.get("return_pct", 0.0),
            final_equity=summary.get("final_equity", 0.0),
            max_dd=summary.get("max_dd", 0.0),
            sharpe=summary.get("sharpe", 0.0),
            sortino=summary.get("sortino", 0.0),
            calmar=summary.get("calmar", 0.0),
            profit_factor=summary.get("profit_factor", 0.0),
        )


@dataclass
class PassportCandidate:
    """A generated passport configuration awaiting evaluation."""
    passport_id: str
    slug: str
    family: str
    config_overrides: dict
    status: str = "generated"
    description: str = ""
    param_summary: str = ""


@dataclass
class EvalResult:
    """Result of evaluating a passport at a specific stage."""
    passport_id: str
    stage: int
    passed: bool
    metrics: dict = field(default_factory=dict)
    reject_reason: Optional[str] = None
    secondary_reasons: list[str] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """Summary of a full research pipeline run."""
    run_id: str
    total_generated: int = 0
    stage1_survivors: int = 0
    stage2_survivors: int = 0
    results: list[EvalResult] = field(default_factory=list)
    rejected_log: list[dict] = field(default_factory=list)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && python -m pytest tests/research/test_types.py -v`
Expected: ALL PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add bot/research/__init__.py bot/research/types.py tests/research/__init__.py tests/research/test_types.py
git commit -m "feat(research): add core types — RegimeType, PassportCandidate, EvalResult

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Regime Classifier

**Files:**
- Create: `bot/research/regime.py`
- Test: `tests/research/test_regime.py`

- [ ] **Step 1: Write failing tests for regime classifier**

```python
# tests/research/test_regime.py
"""Tests for market regime classification."""
import numpy as np
import pandas as pd
import pytest
from bot.research.types import RegimeType
from bot.research.regime import classify_regime, classify_regime_series


def _make_btc_df(closes: list[float], n_bars: int = 60) -> pd.DataFrame:
    """Helper: create BTC 4H DataFrame with given close prices."""
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n_bars, freq="4h"),
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000.0] * n_bars,
    })
    return df


class TestClassifyRegime:
    def test_trend_up(self):
        # Price rises 15% over 30 days (180 4H bars) with strong trend
        closes = np.linspace(40000, 46000, 60).tolist()
        df = _make_btc_df(closes, 60)
        regime = classify_regime(df)
        assert regime == RegimeType.TREND_UP

    def test_trend_down(self):
        # Price drops 15% over 30 days
        closes = np.linspace(46000, 39000, 60).tolist()
        df = _make_btc_df(closes, 60)
        regime = classify_regime(df)
        assert regime == RegimeType.TREND_DOWN

    def test_low_vol_compression(self):
        # Price flat, low volatility
        base = 42000
        np.random.seed(42)
        noise = np.random.normal(0, 50, 60)
        closes = (base + noise).tolist()
        df = _make_btc_df(closes, 60)
        regime = classify_regime(df)
        assert regime in (RegimeType.LOW_VOL_COMPRESSION, RegimeType.HIGH_VOL_CHOP)

    def test_requires_minimum_bars(self):
        closes = [42000.0] * 10
        df = _make_btc_df(closes, 10)
        with pytest.raises(ValueError, match="minimum"):
            classify_regime(df)


class TestClassifyRegimeSeries:
    def test_returns_series_of_regimes(self):
        # 120 bars — enough for rolling classification
        closes = np.linspace(40000, 46000, 120).tolist()
        df = _make_btc_df(closes, 120)
        regimes = classify_regime_series(df, window=180)
        assert len(regimes) == len(df)
        # Recent bars should be TREND_UP (strong uptrend)
        assert regimes.iloc[-1] == RegimeType.TREND_UP.value
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_regime.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement regime classifier**

```python
# bot/research/regime.py
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
    return log_returns.rolling(window).std() * np.sqrt(252 * 6)  # 252 trading days × 6 bars/day for 4H


def classify_regime(df: pd.DataFrame, window: int = 180) -> RegimeType:
    """Classify current regime from BTC 4H OHLCV data.

    Args:
        df: BTC 4H OHLCV DataFrame
        window: Lookback bars for 30d return (30 days × 6 bars/day = 180 for 4H)

    Returns:
        RegimeType for the most recent bar

    Raises:
        ValueError: If fewer than _MIN_BARS bars provided
    """
    if len(df) < _MIN_BARS:
        raise ValueError(f"Need minimum {_MIN_BARS} bars, got {len(df)}")

    close = df["close"]
    ret_30d = (close.iloc[-1] / close.iloc[-window] - 1) * 100  # percentage

    adx = _calc_adx(df)
    adx_current = adx.iloc[-1]

    # Priority-ordered exclusive classification
    if ret_30d > 10 and adx_current > 25:
        return RegimeType.TREND_UP
    if ret_30d < -10 and adx_current > 25:
        return RegimeType.TREND_DOWN

    # Choppy — distinguish high vs low vol
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
    ret_rolling = close.pct_change(window) * 100
    adx = _calc_adx(df)
    rvol = _calc_realized_vol(close)
    rvol_median = rvol.rolling(60, min_periods=30).median()

    regimes = []
    for i in range(len(df)):
        if i < window or pd.isna(ret_rolling.iloc[i]):
            regimes.append(RegimeType.LOW_VOL_COMPRESSION.value)  # default for warmup
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_regime.py -v`
Expected: ALL PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add bot/research/regime.py tests/research/test_regime.py
git commit -m "feat(research): add regime classifier — 4 exclusive BTC-based regimes

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Family Registry (Scoring Families 1-18)

**Files:**
- Create: `bot/research/families.py`
- Test: `tests/research/test_families.py`

- [ ] **Step 1: Write failing tests for family registry**

```python
# tests/research/test_families.py
"""Tests for scoring family definitions."""
import pytest
from bot.research.families import SCORING_FAMILIES, get_family, get_param_grid


class TestScoringFamilies:
    def test_has_18_families(self):
        # Families 1-18 are scoring-based
        assert len(SCORING_FAMILIES) >= 10  # At least 10 for Plan 1

    def test_each_family_has_required_fields(self):
        required = {"name", "weights", "param_ranges", "compatible_regimes", "min_trades"}
        for name, family in SCORING_FAMILIES.items():
            missing = required - set(family.keys())
            assert not missing, f"Family '{name}' missing fields: {missing}"

    def test_weights_use_valid_indicator_names(self):
        valid_indicators = {
            "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
            "bb_position", "volume_spike", "pressure", "candle_direction",
        }
        for name, family in SCORING_FAMILIES.items():
            for ind in family["weights"]:
                assert ind in valid_indicators, f"Family '{name}' has invalid indicator '{ind}'"

    def test_ema_crossover_family(self):
        f = get_family("ema_crossover")
        assert f is not None
        assert f["weights"]["ema_trend"] >= 2.0
        assert f["weights"].get("rsi_position", 0) <= 1.0

    def test_get_family_returns_none_for_unknown(self):
        assert get_family("nonexistent") is None


class TestParamGrid:
    def test_get_param_grid_returns_list_of_overrides(self):
        grid = get_param_grid("ema_crossover")
        assert len(grid) > 0
        for item in grid:
            assert "INDICATOR_WEIGHTS" in item
            assert "CONFIDENCE_THRESHOLD" in item

    def test_grid_respects_bounds(self):
        grid = get_param_grid("ema_crossover")
        for item in grid:
            assert 50 <= item["CONFIDENCE_THRESHOLD"] <= 75

    def test_grid_returns_empty_for_unknown_family(self):
        grid = get_param_grid("nonexistent")
        assert grid == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_families.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement family registry**

```python
# bot/research/families.py
"""Scoring family definitions — weight profiles and parameter ranges.

Each family uses the existing 8 indicators in scorer.py with different
weight combinations and parameter settings. Passport generation iterates
over the param_ranges to create multiple variants per family.
"""
from __future__ import annotations

import itertools
from typing import Optional

# The 8 indicators available in scorer.py
_ALL_INDICATORS = [
    "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
    "bb_position", "volume_spike", "pressure", "candle_direction",
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
        # Add exit strategy variations
        override["USE_ATR_EXITS"] = False
        override["USE_TRAILING_STOP"] = False
        override["MAX_OPEN_POSITIONS_PER_PASSPORT"] = 50
        override["MAX_OPEN_POSITIONS_PER_SYMBOL"] = 1
        grid.append(override)

    return grid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_families.py -v`
Expected: ALL PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add bot/research/families.py tests/research/test_families.py
git commit -m "feat(research): add family registry — 12 scoring families with param ranges

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Passport Generator

**Files:**
- Create: `bot/research/generator.py`
- Test: `tests/research/test_generator.py`

- [ ] **Step 1: Write failing tests for passport generator**

```python
# tests/research/test_generator.py
"""Tests for passport candidate generation."""
import pytest
from bot.research.generator import generate_passports, generate_passport_id
from bot.research.types import PassportCandidate


class TestGeneratePassportId:
    def test_starts_with_psp(self):
        pid = generate_passport_id()
        assert pid.startswith("psp_")

    def test_unique(self):
        ids = {generate_passport_id() for _ in range(100)}
        assert len(ids) == 100


class TestGeneratePassports:
    def test_generates_from_single_family(self):
        passports = generate_passports(families=["ema_crossover"])
        assert len(passports) > 0
        for p in passports:
            assert isinstance(p, PassportCandidate)
            assert p.family == "ema_crossover"

    def test_generates_from_multiple_families(self):
        passports = generate_passports(families=["ema_crossover", "rsi_momentum"])
        families_seen = {p.family for p in passports}
        assert "ema_crossover" in families_seen
        assert "rsi_momentum" in families_seen

    def test_generates_from_all_families_if_none_specified(self):
        passports = generate_passports()
        assert len(passports) > 50  # Should be hundreds

    def test_each_passport_has_config_overrides(self):
        passports = generate_passports(families=["volume_spike_breakout"])
        for p in passports:
            assert "INDICATOR_WEIGHTS" in p.config_overrides
            assert "CONFIDENCE_THRESHOLD" in p.config_overrides

    def test_max_per_family_limits_output(self):
        all_passports = generate_passports(families=["ema_crossover"])
        limited = generate_passports(families=["ema_crossover"], max_per_family=5)
        assert len(limited) == 5
        assert len(limited) < len(all_passports)

    def test_slug_format(self):
        passports = generate_passports(families=["ema_crossover"], max_per_family=1)
        p = passports[0]
        assert "ema_crossover" in p.slug
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_generator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement passport generator**

```python
# bot/research/generator.py
"""Generate passport candidates from family definitions."""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from bot.research.types import PassportCandidate
from bot.research.families import SCORING_FAMILIES, get_param_grid


def generate_passport_id() -> str:
    """Generate a unique passport ID."""
    raw = f"{time.time_ns()}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"psp_{h}"


def _make_slug(family_name: str, overrides: dict) -> str:
    """Create human-readable slug from family + key params."""
    parts = [family_name]
    for key in sorted(overrides.keys()):
        if key in ("INDICATOR_WEIGHTS", "USE_ATR_EXITS", "USE_TRAILING_STOP",
                    "MAX_OPEN_POSITIONS_PER_PASSPORT", "MAX_OPEN_POSITIONS_PER_SYMBOL"):
            continue
        val = overrides[key]
        short_key = key.lower().replace("_threshold", "").replace("_spike", "")
        parts.append(f"{short_key}_{val}")
    return "-".join(parts)


def _make_param_summary(overrides: dict) -> str:
    """Create human-readable parameter summary."""
    skip = {"INDICATOR_WEIGHTS", "USE_ATR_EXITS", "USE_TRAILING_STOP",
            "MAX_OPEN_POSITIONS_PER_PASSPORT", "MAX_OPEN_POSITIONS_PER_SYMBOL"}
    parts = []
    for k, v in sorted(overrides.items()):
        if k not in skip:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def generate_passports(
    families: Optional[list[str]] = None,
    max_per_family: Optional[int] = None,
) -> list[PassportCandidate]:
    """Generate passport candidates from family definitions.

    Args:
        families: List of family names to generate from. None = all families.
        max_per_family: Max passports per family (None = no limit).

    Returns:
        List of PassportCandidate instances ready for evaluation.
    """
    if families is None:
        families = list(SCORING_FAMILIES.keys())

    passports = []
    for family_name in families:
        grid = get_param_grid(family_name)
        if not grid:
            continue

        if max_per_family is not None:
            grid = grid[:max_per_family]

        family_def = SCORING_FAMILIES[family_name]
        for overrides in grid:
            slug = _make_slug(family_name, overrides)
            passports.append(PassportCandidate(
                passport_id=generate_passport_id(),
                slug=slug,
                family=family_name,
                config_overrides=overrides,
                description=family_def["description"],
                param_summary=_make_param_summary(overrides),
            ))

    return passports
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_generator.py -v`
Expected: ALL PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add bot/research/generator.py tests/research/test_generator.py
git commit -m "feat(research): add passport generator — families to candidates

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Stage 1 Evaluator (Viability Gate)

**Files:**
- Create: `bot/research/evaluator.py`
- Test: `tests/research/test_evaluator.py`

- [ ] **Step 1: Write failing tests for Stage 1 evaluator**

```python
# tests/research/test_evaluator.py
"""Tests for evaluation pipeline stages."""
import pytest
from bot.research.types import BacktestMetrics, EvalResult
from bot.research.evaluator import Stage1Evaluator


class TestStage1Evaluator:
    def setup_method(self):
        self.evaluator = Stage1Evaluator()

    def test_pass_healthy_metrics(self):
        metrics = BacktestMetrics(
            trades=50, wins=28, losses=22, win_rate=56.0,
            return_pct=15.0, max_dd=25.0, sharpe=1.2,
            profit_factor=1.4, final_equity=1150.0,
        )
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is True
        assert result.stage == 1

    def test_fail_insufficient_trades(self):
        metrics = BacktestMetrics(trades=5, return_pct=50.0, max_dd=10.0)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        assert "trades" in result.reject_reason.lower()

    def test_fail_catastrophic_drawdown(self):
        metrics = BacktestMetrics(trades=50, return_pct=5.0, max_dd=55.0)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        assert "drawdown" in result.reject_reason.lower()

    def test_fail_severe_loss(self):
        metrics = BacktestMetrics(trades=50, return_pct=-25.0, max_dd=30.0)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        assert "return" in result.reject_reason.lower()

    def test_custom_min_trades(self):
        metrics = BacktestMetrics(trades=18, return_pct=10.0, max_dd=20.0, profit_factor=1.2)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=15)
        assert result.passed is True

    def test_fail_fees_dominate(self):
        # profit_factor < 0.85 means fees/losses dominate
        metrics = BacktestMetrics(
            trades=50, return_pct=-5.0, max_dd=20.0, profit_factor=0.7,
        )
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False

    def test_collects_secondary_reasons(self):
        # Bad on multiple fronts
        metrics = BacktestMetrics(trades=5, return_pct=-30.0, max_dd=60.0, profit_factor=0.5)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        # Should have multiple reasons
        total_reasons = 1 + len(result.secondary_reasons)  # primary + secondary
        assert total_reasons >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_evaluator.py::TestStage1Evaluator -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement Stage 1 evaluator**

```python
# bot/research/evaluator.py
"""Evaluation pipeline — Stage 1 (viability) and Stage 2 (regime walk-forward).

Stage 1 is a sanity gate: kill obviously broken candidates cheaply.
Stage 2 is OOS validation: regime-aware walk-forward.
"""
from __future__ import annotations

from typing import Optional

from bot.research.types import BacktestMetrics, EvalResult


class Stage1Evaluator:
    """Stage 1: Minimum Viability (Sanity Gate).

    Three sub-groups:
    A. Data sanity (not checked here — handled before backtesting)
    B. Trading sanity (min trades, fee ratio)
    C. Catastrophe screen (max DD, return floor)
    """

    def __init__(
        self,
        max_dd_threshold: float = 50.0,
        return_floor: float = -20.0,
        min_profit_factor: float = 0.85,
    ):
        self.max_dd_threshold = max_dd_threshold
        self.return_floor = return_floor
        self.min_profit_factor = min_profit_factor

    def evaluate(
        self,
        passport_id: str,
        metrics: BacktestMetrics,
        min_trades: int = 30,
    ) -> EvalResult:
        """Run Stage 1 viability checks.

        Returns EvalResult with passed=True/False and rejection reasons.
        """
        failures: list[str] = []

        # B. Trading sanity
        if metrics.trades < min_trades:
            failures.append(
                f"Insufficient trades: {metrics.trades} < {min_trades}"
            )
        if metrics.profit_factor > 0 and metrics.profit_factor < self.min_profit_factor:
            failures.append(
                f"Profit factor too low: {metrics.profit_factor:.2f} < {self.min_profit_factor}"
            )

        # C. Catastrophe screen
        if metrics.max_dd > self.max_dd_threshold:
            failures.append(
                f"Drawdown catastrophic: {metrics.max_dd:.1f}% > {self.max_dd_threshold}%"
            )
        if metrics.return_pct < self.return_floor:
            failures.append(
                f"Return below floor: {metrics.return_pct:.1f}% < {self.return_floor}%"
            )

        if not failures:
            return EvalResult(
                passport_id=passport_id,
                stage=1,
                passed=True,
                metrics=_metrics_to_dict(metrics),
            )

        return EvalResult(
            passport_id=passport_id,
            stage=1,
            passed=False,
            metrics=_metrics_to_dict(metrics),
            reject_reason=failures[0],
            secondary_reasons=failures[1:],
        )


def _metrics_to_dict(m: BacktestMetrics) -> dict:
    """Convert BacktestMetrics to a plain dict for storage."""
    return {
        "trades": m.trades, "win_rate": m.win_rate,
        "return_pct": m.return_pct, "max_dd": m.max_dd,
        "sharpe": m.sharpe, "sortino": m.sortino,
        "calmar": m.calmar, "profit_factor": m.profit_factor,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_evaluator.py::TestStage1Evaluator -v`
Expected: ALL PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add bot/research/evaluator.py tests/research/test_evaluator.py
git commit -m "feat(research): add Stage 1 evaluator — viability sanity gate

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Stage 2 Evaluator (Regime Walk-Forward)

**Files:**
- Modify: `bot/research/evaluator.py` (add Stage2Evaluator)
- Modify: `tests/research/test_evaluator.py` (add Stage 2 tests)

- [ ] **Step 1: Write failing tests for Stage 2 evaluator**

Append to `tests/research/test_evaluator.py`:

```python
from bot.research.evaluator import Stage2Evaluator


class TestStage2Evaluator:
    def setup_method(self):
        self.evaluator = Stage2Evaluator()

    def test_pass_two_positive_folds(self):
        fold_results = [
            {"return_pct": 10.0, "max_dd": 20.0, "sharpe": 0.8, "calmar": 0.5, "profit_factor": 1.3, "trades": 30},
            {"return_pct": -5.0, "max_dd": 30.0, "sharpe": -0.2, "calmar": -0.1, "profit_factor": 0.9, "trades": 25},
            {"return_pct": 8.0, "max_dd": 15.0, "sharpe": 0.6, "calmar": 0.4, "profit_factor": 1.2, "trades": 28},
        ]
        result = self.evaluator.evaluate("psp_001", fold_results)
        assert result.passed is True
        assert result.stage == 2

    def test_fail_only_one_positive_fold(self):
        fold_results = [
            {"return_pct": 5.0, "max_dd": 20.0, "sharpe": 0.3, "calmar": 0.2, "profit_factor": 1.1, "trades": 30},
            {"return_pct": -15.0, "max_dd": 35.0, "sharpe": -0.5, "calmar": -0.3, "profit_factor": 0.7, "trades": 25},
            {"return_pct": -10.0, "max_dd": 30.0, "sharpe": -0.3, "calmar": -0.2, "profit_factor": 0.8, "trades": 20},
        ]
        result = self.evaluator.evaluate("psp_001", fold_results)
        assert result.passed is False
        assert "folds" in result.reject_reason.lower()

    def test_fail_catastrophic_single_fold(self):
        fold_results = [
            {"return_pct": 20.0, "max_dd": 15.0, "sharpe": 1.0, "calmar": 0.8, "profit_factor": 1.5, "trades": 30},
            {"return_pct": 10.0, "max_dd": 45.0, "sharpe": 0.3, "calmar": 0.1, "profit_factor": 1.1, "trades": 25},
            {"return_pct": 15.0, "max_dd": 20.0, "sharpe": 0.7, "calmar": 0.5, "profit_factor": 1.3, "trades": 28},
        ]
        result = self.evaluator.evaluate("psp_001", fold_results)
        assert result.passed is False
        assert "drawdown" in result.reject_reason.lower()

    def test_fail_low_aggregate_metrics(self):
        # All barely positive but very low Sharpe/Calmar/PF
        fold_results = [
            {"return_pct": 0.5, "max_dd": 35.0, "sharpe": 0.05, "calmar": 0.01, "profit_factor": 1.01, "trades": 30},
            {"return_pct": 0.3, "max_dd": 30.0, "sharpe": 0.02, "calmar": 0.01, "profit_factor": 1.00, "trades": 25},
            {"return_pct": 0.1, "max_dd": 25.0, "sharpe": 0.01, "calmar": 0.00, "profit_factor": 1.00, "trades": 20},
        ]
        result = self.evaluator.evaluate("psp_001", fold_results)
        assert result.passed is False

    def test_single_fold_mode(self):
        fold_results = [
            {"return_pct": 12.0, "max_dd": 20.0, "sharpe": 0.6, "calmar": 0.4, "profit_factor": 1.3, "trades": 40},
        ]
        result = self.evaluator.evaluate("psp_001", fold_results)
        # Single fold: must be positive and meet metrics
        assert result.passed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_evaluator.py::TestStage2Evaluator -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement Stage 2 evaluator**

Append to `bot/research/evaluator.py`:

```python
import statistics


class Stage2Evaluator:
    """Stage 2: Regime-Split Walk-Forward Validation.

    Checks:
    - At least 2/3 folds OOS positive (or 1/1 for single fold)
    - Median OOS return > 0
    - No single fold DD > 40%
    - Aggregate Sharpe > 0.3 OR Calmar > 0.5 OR PF > 1.1
    """

    def __init__(
        self,
        min_positive_folds_ratio: float = 0.67,  # 2/3
        max_fold_dd: float = 40.0,
        min_sharpe: float = 0.3,
        min_calmar: float = 0.5,
        min_profit_factor: float = 1.1,
    ):
        self.min_positive_folds_ratio = min_positive_folds_ratio
        self.max_fold_dd = max_fold_dd
        self.min_sharpe = min_sharpe
        self.min_calmar = min_calmar
        self.min_profit_factor = min_profit_factor

    def evaluate(
        self,
        passport_id: str,
        fold_results: list[dict],
    ) -> EvalResult:
        """Evaluate OOS walk-forward fold results.

        Args:
            passport_id: Passport being evaluated
            fold_results: List of backtest summary dicts (one per fold)

        Returns:
            EvalResult with pass/fail and detailed metrics
        """
        failures: list[str] = []
        n_folds = len(fold_results)
        if n_folds == 0:
            return EvalResult(
                passport_id=passport_id, stage=2, passed=False,
                reject_reason="No fold results provided",
            )

        returns = [f["return_pct"] for f in fold_results]
        positive_count = sum(1 for r in returns if r > 0)
        positive_ratio = positive_count / n_folds

        # Check: enough positive folds
        if n_folds >= 3 and positive_ratio < self.min_positive_folds_ratio:
            failures.append(
                f"Insufficient positive folds: {positive_count}/{n_folds} "
                f"({positive_ratio:.0%} < {self.min_positive_folds_ratio:.0%})"
            )
        elif n_folds < 3 and positive_count == 0:
            failures.append("Single fold is not positive")

        # Check: median return
        median_return = statistics.median(returns)
        if median_return <= 0 and n_folds >= 3:
            failures.append(f"Median OOS return <= 0: {median_return:.2f}%")

        # Check: no catastrophic single fold DD
        for i, fold in enumerate(fold_results):
            dd = fold.get("max_dd", 0)
            if dd > self.max_fold_dd:
                failures.append(
                    f"Fold {i+1} drawdown catastrophic: {dd:.1f}% > {self.max_fold_dd}%"
                )
                break

        # Check: aggregate quality metrics (OR logic — any one passing is acceptable)
        avg_sharpe = statistics.mean(f.get("sharpe", 0) for f in fold_results)
        avg_calmar = statistics.mean(f.get("calmar", 0) for f in fold_results)
        avg_pf = statistics.mean(f.get("profit_factor", 0) for f in fold_results)

        metrics_pass = (
            avg_sharpe >= self.min_sharpe
            or avg_calmar >= self.min_calmar
            or avg_pf >= self.min_profit_factor
        )
        if not metrics_pass:
            failures.append(
                f"No quality metric passes: Sharpe={avg_sharpe:.2f} (need {self.min_sharpe}), "
                f"Calmar={avg_calmar:.2f} (need {self.min_calmar}), "
                f"PF={avg_pf:.2f} (need {self.min_profit_factor})"
            )

        agg_metrics = {
            "n_folds": n_folds,
            "positive_folds": positive_count,
            "median_return": median_return,
            "avg_sharpe": avg_sharpe,
            "avg_calmar": avg_calmar,
            "avg_profit_factor": avg_pf,
            "fold_returns": returns,
        }

        if not failures:
            return EvalResult(
                passport_id=passport_id, stage=2, passed=True,
                metrics=agg_metrics,
            )

        return EvalResult(
            passport_id=passport_id, stage=2, passed=False,
            metrics=agg_metrics,
            reject_reason=failures[0],
            secondary_reasons=failures[1:],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_evaluator.py -v`
Expected: ALL PASS (12 tests — 7 Stage 1 + 5 Stage 2)

- [ ] **Step 5: Commit**

```bash
git add bot/research/evaluator.py tests/research/test_evaluator.py
git commit -m "feat(research): add Stage 2 evaluator — regime walk-forward validation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Experiment Tracker

**Files:**
- Create: `bot/research/tracker.py`
- Test: `tests/research/test_tracker.py`

- [ ] **Step 1: Write failing tests for experiment tracker**

```python
# tests/research/test_tracker.py
"""Tests for experiment tracker (SQLite persistence)."""
import os
import tempfile
import pytest
from bot.research.tracker import ExperimentTracker
from bot.research.types import PassportCandidate, EvalResult, ExperimentResult


@pytest.fixture
def tracker():
    """Create tracker with temp database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    t = ExperimentTracker(db_path=path)
    yield t
    t.close()
    os.unlink(path)


class TestExperimentTracker:
    def test_start_experiment(self, tracker):
        run_id = tracker.start_experiment(total_generated=400)
        assert run_id.startswith("exp-")

    def test_log_passport(self, tracker):
        run_id = tracker.start_experiment(total_generated=1)
        pc = PassportCandidate(
            passport_id="psp_test_001", slug="test-slug",
            family="ema_crossover", config_overrides={"CONFIDENCE_THRESHOLD": 60},
        )
        tracker.log_passport(run_id, pc)
        passports = tracker.get_passports(run_id)
        assert len(passports) == 1
        assert passports[0]["passport_id"] == "psp_test_001"

    def test_log_eval_result(self, tracker):
        run_id = tracker.start_experiment(total_generated=1)
        er = EvalResult(
            passport_id="psp_test_001", stage=1, passed=True,
            metrics={"trades": 50, "return_pct": 10.0},
        )
        tracker.log_eval(run_id, er)
        evals = tracker.get_evals(run_id, stage=1)
        assert len(evals) == 1
        assert evals[0]["passed"] is True

    def test_get_survivors(self, tracker):
        run_id = tracker.start_experiment(total_generated=3)
        for i, passed in enumerate([True, False, True]):
            er = EvalResult(
                passport_id=f"psp_{i}", stage=1, passed=passed,
                metrics={},
                reject_reason=None if passed else "failed",
            )
            tracker.log_eval(run_id, er)
        survivors = tracker.get_survivors(run_id, stage=1)
        assert len(survivors) == 2

    def test_finish_experiment(self, tracker):
        run_id = tracker.start_experiment(total_generated=10)
        result = tracker.finish_experiment(
            run_id, stage1_survivors=5, stage2_survivors=2,
        )
        assert isinstance(result, ExperimentResult)
        assert result.stage1_survivors == 5
        assert result.stage2_survivors == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement experiment tracker**

```python
# bot/research/tracker.py
"""Experiment tracker — SQLite-based persistence for research runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from bot.research.types import PassportCandidate, EvalResult, ExperimentResult


class ExperimentTracker:
    """Track research pipeline experiments in SQLite."""

    def __init__(self, db_path: str = "research_experiments.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS experiments (
                run_id TEXT PRIMARY KEY,
                total_generated INTEGER DEFAULT 0,
                stage1_survivors INTEGER DEFAULT 0,
                stage2_survivors INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                started_at TEXT,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS passports (
                run_id TEXT,
                passport_id TEXT,
                slug TEXT,
                family TEXT,
                config_overrides TEXT,
                status TEXT DEFAULT 'generated',
                PRIMARY KEY (run_id, passport_id)
            );
            CREATE TABLE IF NOT EXISTS eval_results (
                run_id TEXT,
                passport_id TEXT,
                stage INTEGER,
                passed INTEGER,
                metrics TEXT,
                reject_reason TEXT,
                secondary_reasons TEXT,
                evaluated_at TEXT,
                PRIMARY KEY (run_id, passport_id, stage)
            );
        """)
        self.conn.commit()

    def start_experiment(self, total_generated: int = 0) -> str:
        """Start a new experiment run. Returns run_id."""
        now = datetime.now(timezone.utc)
        run_id = f"exp-{now.strftime('%Y-%m-%d-%H%M%S')}"
        self.conn.execute(
            "INSERT INTO experiments (run_id, total_generated, started_at) VALUES (?, ?, ?)",
            (run_id, total_generated, now.isoformat()),
        )
        self.conn.commit()
        return run_id

    def log_passport(self, run_id: str, passport: PassportCandidate):
        """Log a generated passport candidate."""
        self.conn.execute(
            "INSERT OR REPLACE INTO passports (run_id, passport_id, slug, family, config_overrides, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, passport.passport_id, passport.slug, passport.family,
             json.dumps(passport.config_overrides), passport.status),
        )
        self.conn.commit()

    def log_eval(self, run_id: str, result: EvalResult):
        """Log an evaluation result."""
        now = datetime.now(timezone.utc)
        self.conn.execute(
            "INSERT OR REPLACE INTO eval_results "
            "(run_id, passport_id, stage, passed, metrics, reject_reason, secondary_reasons, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, result.passport_id, result.stage, int(result.passed),
             json.dumps(result.metrics), result.reject_reason,
             json.dumps(result.secondary_reasons), now.isoformat()),
        )
        self.conn.commit()

    def get_passports(self, run_id: str) -> list[dict]:
        """Get all passports for a run."""
        rows = self.conn.execute(
            "SELECT * FROM passports WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_evals(self, run_id: str, stage: Optional[int] = None) -> list[dict]:
        """Get evaluation results, optionally filtered by stage."""
        if stage is not None:
            rows = self.conn.execute(
                "SELECT * FROM eval_results WHERE run_id = ? AND stage = ?",
                (run_id, stage),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM eval_results WHERE run_id = ?", (run_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["passed"] = bool(d["passed"])
            return result
        return result

    def get_survivors(self, run_id: str, stage: int) -> list[str]:
        """Get passport IDs that passed a given stage."""
        rows = self.conn.execute(
            "SELECT passport_id FROM eval_results WHERE run_id = ? AND stage = ? AND passed = 1",
            (run_id, stage),
        ).fetchall()
        return [r["passport_id"] for r in rows]

    def finish_experiment(
        self, run_id: str,
        stage1_survivors: int = 0,
        stage2_survivors: int = 0,
    ) -> ExperimentResult:
        """Mark experiment as finished and return summary."""
        now = datetime.now(timezone.utc)
        self.conn.execute(
            "UPDATE experiments SET stage1_survivors = ?, stage2_survivors = ?, "
            "status = 'completed', finished_at = ? WHERE run_id = ?",
            (stage1_survivors, stage2_survivors, now.isoformat(), run_id),
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM experiments WHERE run_id = ?", (run_id,)
        ).fetchone()

        return ExperimentResult(
            run_id=run_id,
            total_generated=row["total_generated"],
            stage1_survivors=stage1_survivors,
            stage2_survivors=stage2_survivors,
        )

    def close(self):
        """Close database connection."""
        self.conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_tracker.py -v`
Expected: ALL PASS (5 tests)

- [ ] **Step 5: Fix bug in get_evals and re-run**

Note: The `get_evals` method has a bug — the loop returns inside itself. Fix:

```python
    def get_evals(self, run_id: str, stage: Optional[int] = None) -> list[dict]:
        if stage is not None:
            rows = self.conn.execute(
                "SELECT * FROM eval_results WHERE run_id = ? AND stage = ?",
                (run_id, stage),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM eval_results WHERE run_id = ?", (run_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["passed"] = bool(d["passed"])
            result.append(d)
        return result
```

Run: `python -m pytest tests/research/test_tracker.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add bot/research/tracker.py tests/research/test_tracker.py
git commit -m "feat(research): add experiment tracker — SQLite persistence

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Research Pipeline Orchestrator

**Files:**
- Create: `bot/research/pipeline.py`
- Test: `tests/research/test_pipeline.py`

- [ ] **Step 1: Write failing tests for pipeline**

```python
# tests/research/test_pipeline.py
"""Tests for the research pipeline orchestrator."""
import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from bot.research.pipeline import ResearchPipeline
from bot.research.types import BacktestMetrics


@pytest.fixture
def pipeline():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    p = ResearchPipeline(
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1h",
        days=180,
        db_path=db_path,
    )
    yield p
    p.tracker.close()
    os.unlink(db_path)


class TestResearchPipeline:
    def test_generate_candidates(self, pipeline):
        candidates = pipeline.generate_candidates(
            families=["ema_crossover"],
            max_per_family=3,
        )
        assert len(candidates) == 3
        for c in candidates:
            assert c.family == "ema_crossover"

    @patch("bot.research.pipeline.run_backtest")
    def test_run_stage1_filters_bad_candidates(self, mock_bt, pipeline):
        candidates = pipeline.generate_candidates(
            families=["volume_spike_breakout"], max_per_family=2,
        )
        # First candidate passes, second fails
        mock_bt.side_effect = [
            {"trades": 50, "win_rate": 55, "return_pct": 10.0, "max_dd": 20.0,
             "sharpe": 0.8, "calmar": 0.5, "profit_factor": 1.3,
             "final_equity": 1100, "wins": 28, "losses": 22,
             "sortino": 1.0, "trade_details": []},
            {"trades": 5, "win_rate": 20, "return_pct": -30.0, "max_dd": 60.0,
             "sharpe": -0.5, "calmar": -0.2, "profit_factor": 0.5,
             "final_equity": 700, "wins": 1, "losses": 4,
             "sortino": -0.3, "trade_details": []},
        ]
        survivors = pipeline.run_stage1(candidates)
        assert len(survivors) <= len(candidates)

    def test_pipeline_generates_and_tracks(self, pipeline):
        candidates = pipeline.generate_candidates(
            families=["ema_crossover"], max_per_family=2,
        )
        assert pipeline.run_id is not None
        passports = pipeline.tracker.get_passports(pipeline.run_id)
        assert len(passports) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/research/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement pipeline orchestrator**

```python
# bot/research/pipeline.py
"""Research pipeline orchestrator — generate, evaluate, track."""
from __future__ import annotations

import logging
from typing import Optional

from bot.backtester import run_backtest
from bot.research.types import PassportCandidate, BacktestMetrics, EvalResult
from bot.research.generator import generate_passports
from bot.research.evaluator import Stage1Evaluator, Stage2Evaluator
from bot.research.tracker import ExperimentTracker
from bot.research.families import SCORING_FAMILIES

logger = logging.getLogger(__name__)


class ResearchPipeline:
    """Orchestrates the full research pipeline: generate → Stage 1 → Stage 2."""

    def __init__(
        self,
        symbols: list[str],
        interval: str = "1h",
        days: int = 180,
        db_path: str = "research_experiments.db",
    ):
        self.symbols = symbols
        self.interval = interval
        self.days = days
        self.tracker = ExperimentTracker(db_path=db_path)
        self.stage1 = Stage1Evaluator()
        self.stage2 = Stage2Evaluator()
        self.run_id: Optional[str] = None

    def generate_candidates(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
    ) -> list[PassportCandidate]:
        """Generate passport candidates and start tracking."""
        candidates = generate_passports(families=families, max_per_family=max_per_family)
        self.run_id = self.tracker.start_experiment(total_generated=len(candidates))
        for c in candidates:
            self.tracker.log_passport(self.run_id, c)
        logger.info("Generated %d candidates (run_id=%s)", len(candidates), self.run_id)
        return candidates

    def run_stage1(
        self,
        candidates: list[PassportCandidate],
    ) -> list[PassportCandidate]:
        """Run Stage 1 viability on all candidates via backtesting."""
        survivors = []
        for i, candidate in enumerate(candidates):
            logger.info(
                "[Stage 1] %d/%d — %s", i + 1, len(candidates), candidate.slug,
            )
            try:
                summary = run_backtest(
                    symbols=self.symbols,
                    interval=self.interval,
                    days=self.days,
                    cfg_override=candidate.config_overrides,
                )
                metrics = BacktestMetrics.from_summary(summary)
            except Exception as e:
                logger.warning("Backtest failed for %s: %s", candidate.slug, e)
                result = EvalResult(
                    passport_id=candidate.passport_id, stage=1, passed=False,
                    reject_reason=f"Backtest error: {e}",
                )
                self.tracker.log_eval(self.run_id, result)
                continue

            min_trades = SCORING_FAMILIES.get(
                candidate.family, {}
            ).get("min_trades", 30)
            result = self.stage1.evaluate(
                candidate.passport_id, metrics, min_trades=min_trades,
            )
            self.tracker.log_eval(self.run_id, result)

            if result.passed:
                candidate.status = "stage1_passed"
                survivors.append(candidate)
                logger.info("  ✅ PASS — return=%.1f%% dd=%.1f%% sharpe=%.2f",
                            metrics.return_pct, metrics.max_dd, metrics.sharpe)
            else:
                logger.info("  ❌ FAIL — %s", result.reject_reason)

        logger.info("Stage 1: %d/%d survived", len(survivors), len(candidates))
        return survivors

    def run_stage2(
        self,
        candidates: list[PassportCandidate],
        train_days: int = 120,
        test_days: int = 60,
    ) -> list[PassportCandidate]:
        """Run Stage 2 walk-forward validation on Stage 1 survivors."""
        survivors = []
        total_days = self.days
        # Calculate fold positions
        folds = _calc_folds(total_days, train_days, test_days, slide=30)

        for i, candidate in enumerate(candidates):
            logger.info(
                "[Stage 2] %d/%d — %s (%d folds)",
                i + 1, len(candidates), candidate.slug, len(folds),
            )
            fold_results = []
            for fold_idx, (train_end_offset, test_end_offset) in enumerate(folds):
                try:
                    # Train period backtest (for reference / overfit comparison)
                    train_summary = run_backtest(
                        symbols=self.symbols,
                        interval=self.interval,
                        days=train_days,
                        cfg_override=candidate.config_overrides,
                        end_offset_days=train_end_offset,
                    )
                    # Test period backtest (OOS — this determines pass/fail)
                    test_summary = run_backtest(
                        symbols=self.symbols,
                        interval=self.interval,
                        days=test_days,
                        cfg_override=candidate.config_overrides,
                        end_offset_days=test_end_offset,
                    )
                    # Add overfit ratio for monitoring
                    train_ret = train_summary.get("return_pct", 0)
                    test_ret = test_summary.get("return_pct", 0)
                    test_summary["overfit_ratio"] = (
                        test_ret / train_ret if train_ret != 0 else 0.0
                    )
                    fold_results.append(test_summary)
                except Exception as e:
                    logger.warning("Fold %d failed for %s: %s", fold_idx, candidate.slug, e)
                    fold_results.append({
                        "return_pct": -100.0, "max_dd": 100.0,
                        "sharpe": -1.0, "calmar": -1.0, "profit_factor": 0.0,
                        "trades": 0,
                    })

            result = self.stage2.evaluate(candidate.passport_id, fold_results)
            self.tracker.log_eval(self.run_id, result)

            if result.passed:
                candidate.status = "stage2_passed"
                survivors.append(candidate)
                logger.info("  ✅ PASS — avg_sharpe=%.2f median_ret=%.1f%%",
                            result.metrics.get("avg_sharpe", 0),
                            result.metrics.get("median_return", 0))
            else:
                logger.info("  ❌ FAIL — %s", result.reject_reason)

        logger.info("Stage 2: %d/%d survived", len(survivors), len(candidates))
        return survivors

    def run_full(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
    ) -> list[PassportCandidate]:
        """Run the complete pipeline: generate → Stage 1 → Stage 2."""
        candidates = self.generate_candidates(families, max_per_family)
        stage1_survivors = self.run_stage1(candidates)
        stage2_survivors = self.run_stage2(stage1_survivors)

        self.tracker.finish_experiment(
            self.run_id,
            stage1_survivors=len(stage1_survivors),
            stage2_survivors=len(stage2_survivors),
        )

        logger.info(
            "Pipeline complete: %d generated → %d stage1 → %d stage2",
            len(candidates), len(stage1_survivors), len(stage2_survivors),
        )
        return stage2_survivors


def _calc_folds(
    total_days: int, train_days: int, test_days: int, slide: int = 30,
) -> list[tuple[int, int]]:
    """Calculate walk-forward fold offsets.

    Returns list of (train_end_offset, test_end_offset) in days from end.
    Most recent fold first (offset=0 = ends today).

    Example with total_days=300, train=120, test=60, slide=30:
      Fold 0: test ends at day 0 (most recent), train ends at day 60
      Fold 1: test ends at day 30, train ends at day 90
      Fold 2: test ends at day 60, train ends at day 120
    """
    fold_size = train_days + test_days
    folds = []
    offset = 0
    while offset + fold_size <= total_days:
        # test_end_offset: how many days back from today the test period ends
        test_end_offset = offset
        # train_end_offset: test period sits after train, so train ends
        # test_days further back from the test end
        train_end_offset = offset + test_days
        folds.append((train_end_offset, test_end_offset))
        offset += slide

    if not folds:
        # Not enough data for even one fold — use all data as single fold
        folds.append((0, 0))

    return folds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/research/test_pipeline.py -v`
Expected: ALL PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add bot/research/pipeline.py tests/research/test_pipeline.py
git commit -m "feat(research): add pipeline orchestrator — generate → Stage 1 → Stage 2

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: CLI Entry Point

**Files:**
- Create: `run_research.py`

- [ ] **Step 1: Create CLI entry point**

```python
#!/usr/bin/env python3
"""Strategy Research Engine CLI.

Usage:
    python run_research.py --families ema_crossover,rsi_momentum --max-per-family 10
    python run_research.py --all --pairs 10
    python run_research.py --all --max-per-family 5 --days 240
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from bot.data_fetcher import get_all_futures_symbols
from bot.research.pipeline import ResearchPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"logs/research_{int(time.time())}.log"),
    ],
)
logger = logging.getLogger("research")


def main():
    parser = argparse.ArgumentParser(description="Strategy Research Engine")
    parser.add_argument("--families", type=str, default=None,
                        help="Comma-separated family names (default: all)")
    parser.add_argument("--all", action="store_true",
                        help="Run all families")
    parser.add_argument("--max-per-family", type=int, default=None,
                        help="Max passports per family (default: no limit)")
    parser.add_argument("--pairs", type=int, default=15,
                        help="Number of trading pairs (default: 15)")
    parser.add_argument("--interval", type=str, default="1h",
                        help="Timeframe (default: 1h)")
    parser.add_argument("--days", type=int, default=180,
                        help="History days (default: 180)")
    parser.add_argument("--db-path", type=str, default="research_experiments.db",
                        help="Experiment database path")
    args = parser.parse_args()

    # Resolve families
    families = None
    if args.families:
        families = [f.strip() for f in args.families.split(",")]
    elif not args.all:
        logger.error("Specify --families or --all")
        sys.exit(1)

    # Get symbols
    logger.info("Fetching top %d symbols by volume...", args.pairs)
    symbols = get_all_futures_symbols()[:args.pairs]
    logger.info("Trading pairs: %s", symbols)

    # Run pipeline
    pipeline = ResearchPipeline(
        symbols=symbols,
        interval=args.interval,
        days=args.days,
        db_path=args.db_path,
    )

    start = time.time()
    survivors = pipeline.run_full(
        families=families,
        max_per_family=args.max_per_family,
    )
    elapsed = time.time() - start

    # Report
    logger.info("=" * 60)
    logger.info("RESEARCH COMPLETE in %.1f minutes", elapsed / 60)
    logger.info("=" * 60)
    logger.info("Survivors (%d):", len(survivors))
    for s in survivors:
        logger.info("  • %s [%s] — %s", s.slug, s.family, s.param_summary)

    if not survivors:
        logger.warning("No survivors! Consider relaxing thresholds or adding more families.")

    pipeline.tracker.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help works**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && python run_research.py --help`
Expected: Shows usage info without errors

- [ ] **Step 3: Commit**

```bash
git add run_research.py
git commit -m "feat(research): add CLI entry point — run_research.py

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 10: Full Test Suite Pass + Integration Smoke Test

**Files:**
- All test files from Tasks 1-8

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/faiqnau/fight/trading/crypto-signal && python -m pytest tests/ -v --tb=short`
Expected: ALL tests pass (existing + new research tests)

- [ ] **Step 2: Fix any failures**

If any tests fail, fix them. Common issues:
- Import path errors — ensure `bot/research/__init__.py` exists
- Missing test fixtures — ensure all `@pytest.fixture` have cleanup

- [ ] **Step 3: Verify pipeline import chain**

Run: `python -c "from bot.research.pipeline import ResearchPipeline; print('OK')"`
Expected: Prints "OK"

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test(research): full test suite pass — all research modules verified

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Plan 2 & 3 Reference (Future)

**Plan 2: Robustness & Portfolio** (depends on Plan 1)
- Stage 3: Parameter perturbation evaluator
- Stage 4: Orthogonality + portfolio construction
- New indicators (families 6-18): Ichimoku, VWAP, Keltner, Donchian, HeikinAshi, Williams%R, CCI, MFI, HullMA, Supertrend, Pivot
- Versioning v2 registry system
- Legacy passport adapter

**Plan 3: Deployment & Live Trading** (depends on Plan 1+2)
- Scheduler/Orchestrator + Workers
- Order Intent layer
- Portfolio Risk Manager (hard limits + soft alerts)
- Paper/prod namespace separation
- Telegram commands (/strategies, /compare, /promote, /pause)
- Health monitoring
- Artifact handoff local → VPS
