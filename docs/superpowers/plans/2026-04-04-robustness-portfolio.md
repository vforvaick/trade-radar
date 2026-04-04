# Robustness & Portfolio Construction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Stage 3 (parameter perturbation) and Stage 4 (orthogonality + portfolio construction) evaluators, 13 new indicators for families 6-18, Versioning v2 registry, and legacy passport adapter.

**Architecture:** Extends bot/research/ from Plan 1 with stage3.py (Monte Carlo perturbation), stage4.py (correlation + clustering + marginal utility), indicators.py (13 new indicators), extended_scorer.py (21-indicator scorer), registry.py (passport v2 lifecycle), legacy_adapter.py.

**Tech Stack:** Python 3.11+, numpy, pandas, scipy, sqlite3, uuid, pytest

**Depends on:** Plan 1 (Research Engine Core)

---

## File Map

| File | Responsibility |
|------|---------------|
| bot/research/indicators.py (CREATE) | 13 new indicator calculation functions |
| bot/research/extended_scorer.py (CREATE) | Extended scorer supporting 21 indicators |
| bot/research/families.py (MODIFY) | Add families 6-18 definitions |
| bot/research/stage3.py (CREATE) | Stage 3: Parameter perturbation evaluator |
| bot/research/stage4.py (CREATE) | Stage 4: Orthogonality and portfolio construction |
| bot/research/registry.py (CREATE) | Versioning v2: passport registry + lifecycle |
| bot/research/legacy_adapter.py (CREATE) | Convert v1 passports to v2 schema |
| bot/research/pipeline.py (MODIFY) | Add run_stage3(), run_stage4() |
| bot/research/types.py (MODIFY) | Add Stage3Result, Stage4Result, PortfolioSelection |

---

## Task 1: Extended Types

**Files:**
- Modify: `bot/research/types.py`
- Test: `tests/research/test_types.py` (extend)

- [ ] **Step 1: Write failing tests for new types**

Add to `tests/research/test_types.py`:

```python
def test_stage3_result_creation():
    from bot.research.types import Stage3Result
    r = Stage3Result(
        passport_id="psp_test", survival_rate=0.72,
        mean_perturbed_return=8.5, original_return=12.0,
        p5_return=-5.2, p95_return=22.0, iqr_return=10.5,
        passed=True, reject_reason=None, mc_iterations=50,
        perturbation_details=[],
    )
    assert r.passed is True
    assert r.survival_rate == 0.72

def test_stage4_result_creation():
    from bot.research.types import Stage4Result
    r = Stage4Result(
        selected_passport_ids=["psp_a", "psp_b"],
        portfolio_utility=2.35, portfolio_sharpe=1.2, portfolio_max_dd=15.0,
        family_counts={"ema_crossover": 2}, cluster_counts={0: 2},
        correlation_matrix={"psp_a|psp_b": 0.15}, rejection_log=[],
    )
    assert len(r.selected_passport_ids) == 2

def test_portfolio_selection():
    from bot.research.types import PortfolioSelection
    ps = PortfolioSelection(
        experiment_run_id="exp-001", selected=[], total_candidates=100,
        stage3_survivors=25, stage4_selected=12, composite_utility=3.1,
        selection_rationale="Top 12 by marginal utility",
    )
    assert ps.stage4_selected == 12
```

- [ ] **Step 2: Run tests — expected FAIL**

Run: `python -m pytest tests/research/test_types.py -v -k "stage3 or stage4 or portfolio_selection" --tb=short`

- [ ] **Step 3: Implement new types**

Add to `bot/research/types.py`:

```python
@dataclass
class Stage3Result:
    passport_id: str
    survival_rate: float
    mean_perturbed_return: float
    original_return: float
    p5_return: float
    p95_return: float
    iqr_return: float
    passed: bool
    reject_reason: Optional[str]
    mc_iterations: int
    perturbation_details: list[dict]

@dataclass
class Stage4Result:
    selected_passport_ids: list[str]
    portfolio_utility: float
    portfolio_sharpe: float
    portfolio_max_dd: float
    family_counts: dict[str, int]
    cluster_counts: dict[int, int]
    correlation_matrix: dict[str, float]
    rejection_log: list[dict]

@dataclass
class PortfolioSelection:
    experiment_run_id: str
    selected: list
    total_candidates: int
    stage3_survivors: int
    stage4_selected: int
    composite_utility: float
    selection_rationale: str
```

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/types.py tests/research/test_types.py
git commit -m "feat(research): add Stage3Result, Stage4Result, PortfolioSelection types"
```

---

## Task 2: New Indicator Module (13 indicators)

**Files:**
- Create: `bot/research/indicators.py`
- Create: `tests/research/test_indicators.py`

- [ ] **Step 1: Write failing tests**

Create `tests/research/test_indicators.py` with parametrized tests for all 13 indicators: `calc_stochrsi`, `calc_obv_trend`, `calc_ichimoku`, `calc_vwap_deviation`, `calc_keltner`, `calc_donchian`, `calc_heikin_ashi`, `calc_williams_r`, `calc_cci`, `calc_mfi`, `calc_hull_ma`, `calc_supertrend`, `calc_pivot_points`.

```python
import numpy as np
import pandas as pd
import pytest

def make_ohlcv(n=100, trend="up", seed=42):
    rng = np.random.RandomState(seed)
    if trend == "up":
        base = 100 + np.cumsum(rng.normal(0.3, 1.5, n))
    elif trend == "down":
        base = 100 + np.cumsum(rng.normal(-0.3, 1.5, n))
    else:
        base = 100 + np.cumsum(rng.normal(0, 1.0, n))
    base = np.maximum(base, 10)
    return pd.DataFrame({
        "open": base + rng.uniform(-0.5, 0.5, n),
        "high": base + rng.uniform(0.5, 2.0, n),
        "low": base - rng.uniform(0.5, 2.0, n),
        "close": base, "volume": rng.uniform(1e6, 5e6, n),
    })

ALL_INDICATORS = [
    "calc_stochrsi", "calc_obv_trend", "calc_ichimoku",
    "calc_vwap_deviation", "calc_keltner", "calc_donchian",
    "calc_heikin_ashi", "calc_williams_r", "calc_cci",
    "calc_mfi", "calc_hull_ma", "calc_supertrend", "calc_pivot_points",
]

@pytest.mark.parametrize("func_name", ALL_INDICATORS)
def test_indicator_returns_tuple(func_name):
    from bot.research import indicators as ind
    fn = getattr(ind, func_name)
    df = make_ohlcv(100)
    result = fn(df)
    assert isinstance(result, tuple) and len(result) == 2
    direction, value = result
    assert direction in ("LONG", "SHORT", None)

@pytest.mark.parametrize("func_name", ALL_INDICATORS)
def test_indicator_handles_insufficient_data(func_name):
    from bot.research import indicators as ind
    fn = getattr(ind, func_name)
    df = make_ohlcv(3)
    direction, value = fn(df)
    assert direction is None
```

- [ ] **Step 2: Run tests — expected FAIL (module not found)**
- [ ] **Step 3: Implement all 13 indicators**

Create `bot/research/indicators.py`. Each function takes OHLCV DataFrame and returns `(direction, value)` where direction is `"LONG"`, `"SHORT"`, or `None`. Full implementations:

1. **calc_stochrsi(df, rsi_period=14, k_period=3, d_period=3)** — Stochastic RSI. LONG if %K crosses above %D from below 30. SHORT if crosses below from above 70. Min bars: rsi_period+k_period+d_period+5.

2. **calc_obv_trend(df, period=20)** — OBV linear regression slope. LONG if positive, SHORT if negative. Min bars: period+5.

3. **calc_ichimoku(df)** — Tenkan(9)/Kijun(26) cross + cloud position + span color. Counts 3 signals, majority wins. Min bars: 52.

4. **calc_vwap_deviation(df, period=20)** — Rolling VWAP z-score. LONG if z < -1.5, SHORT if z > 1.5. Min bars: period+5.

5. **calc_keltner(df, period=20, atr_mult=2.0)** — EMA +/- ATR*mult channel. LONG on upper breakout, SHORT on lower. Min bars: period+5.

6. **calc_donchian(df, period=20)** — Highest high / lowest low channel. LONG at new high, SHORT at new low. Uses previous bar channel (no look-ahead). Min bars: period+2.

7. **calc_heikin_ashi(df)** — HA candle persistence count. LONG if 3+ consecutive green HA, SHORT if 3+ red. Min bars: 10.

8. **calc_williams_r(df, period=14)** — Williams %R (-100 to 0). LONG if < -80, SHORT if > -20. Min bars: period+2.

9. **calc_cci(df, period=20)** — CCI with 0.015 MAD constant. LONG if > 100 or crossing up from -100. SHORT if < -100 or crossing down from 100. Min bars: period+5.

10. **calc_mfi(df, period=14)** — Volume-weighted RSI. LONG if < 20, SHORT if > 80. Min bars: period+5.

11. **calc_hull_ma(df, period=16)** — HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n)). LONG if rising, SHORT if falling. Min bars: period*2+5.

12. **calc_supertrend(df, period=10, multiplier=3.0)** — ATR-based trend with flip logic. LONG if close > supertrend level. Min bars: period+10.

13. **calc_pivot_points(df)** — Previous bar HLC pivot with S1/S2/R1/R2. LONG near support, SHORT near resistance (within 15pct of ATR). Min bars: 5.

All use `_safe(direction, value)` helper that validates direction is in allowed set.

*(Full implementation code: see Plan 1 Task 2 pattern — each function is 15-40 lines of numpy/pandas. The agentic worker must implement the complete mathematical formula for each indicator.)*

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/indicators.py tests/research/test_indicators.py
git commit -m "feat(research): add 13 new indicator functions for families 6-18"
```

---

## Task 3: Extended Scorer (21 indicators)

**Files:**
- Create: `bot/research/extended_scorer.py`
- Create: `tests/research/test_extended_scorer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/research/test_extended_scorer.py`:

```python
import numpy as np, pandas as pd, pytest

def make_ohlcv(n=200, seed=42):
    rng = np.random.RandomState(seed)
    base = 100 + np.cumsum(rng.normal(0.2, 1.5, n))
    base = np.maximum(base, 10)
    return pd.DataFrame({"open": base + rng.uniform(-0.5, 0.5, n),
        "high": base + rng.uniform(0.5, 2.0, n),
        "low": base - rng.uniform(0.5, 2.0, n),
        "close": base, "volume": rng.uniform(1e6, 5e6, n)})

def test_score_extended_returns_signal():
    from bot.research.extended_scorer import score_extended
    result = score_extended(make_ohlcv(200), weights={"ema_trend": 1.0, "rsi_position": 1.0})
    assert "direction" in result and "confidence" in result and "go" in result

def test_new_indicator_weights():
    from bot.research.extended_scorer import score_extended
    result = score_extended(make_ohlcv(200), weights={"stochrsi": 2.0, "obv_trend": 1.5})
    assert isinstance(result["confidence"], (int, float))

def test_empty_weights_no_signal():
    from bot.research.extended_scorer import score_extended
    assert score_extended(make_ohlcv(200), weights={})["direction"] is None

def test_all_21_indicators_registered():
    from bot.research.extended_scorer import INDICATOR_REGISTRY
    assert len(INDICATOR_REGISTRY) == 21
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement extended scorer**

Create `bot/research/extended_scorer.py`: INDICATOR_REGISTRY maps 8 original + 13 new indicator names to callables. `score_extended(df, weights, btc_trend, confidence_threshold)` runs weighted voting identical to `bot/scorer.py` but using the extended registry. Zero-weight indicators excluded. Volume is non-directional. Returns dict with direction, confidence, leverage, risk_reward, go, signals.

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/extended_scorer.py tests/research/test_extended_scorer.py
git commit -m "feat(research): add extended scorer with 21-indicator registry"
```

---

## Task 4: Extended Family Registry (Families 6-18)

**Files:**
- Modify: `bot/research/families.py`
- Modify: `tests/research/test_families.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/research/test_families.py`:

```python
def test_families_6_through_18_exist():
    from bot.research.families import SCORING_FAMILIES
    expected = ["stochastic_reversal", "obv_trend", "ichimoku_cloud",
        "vwap_deviation", "keltner_breakout", "donchian_breakout",
        "heikin_ashi_momentum", "williams_reversal", "cci_divergence",
        "mfi_flow", "hull_ma_crossover", "supertrend_follow", "pivot_bounce"]
    for name in expected:
        assert name in SCORING_FAMILIES, f"Missing: {name}"

def test_total_family_count_at_least_18():
    from bot.research.families import SCORING_FAMILIES
    assert len(SCORING_FAMILIES) >= 18
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Add 13 new family definitions**

Add to SCORING_FAMILIES dict in `bot/research/families.py`:

| Family | Core Indicators (weights) | Regime Affinity |
|--------|--------------------------|-----------------|
| stochastic_reversal | stochrsi:2.5, rsi:1.5, bb:1.0 | chop, compression |
| obv_trend | obv:2.5, ema:1.5, vol:1.0 | trend_up, trend_down |
| ichimoku_cloud | ichimoku:3.0, ema:1.0, macd:1.0 | trending |
| vwap_deviation | vwap:2.5, bb:1.5, rsi:1.0 | chop, compression |
| keltner_breakout | keltner:2.5, vol:2.0, ema:1.0 | all except compression |
| donchian_breakout | donchian:2.5, ema:1.5, vol:1.0 | trending |
| heikin_ashi_momentum | ha:2.0, ema:1.5, macd:1.0 | trending |
| williams_reversal | williams:2.5, rsi:1.5, bb:1.0 | chop, compression |
| cci_divergence | cci:2.0, macd:1.5, rsi:1.0 | all |
| mfi_flow | mfi:2.5, vol:1.5, pressure:1.0 | all |
| hull_ma_crossover | hull:2.5, ema:1.5, macd:1.0 | trending |
| supertrend_follow | supertrend:3.0, ema:1.5 | trending |
| pivot_bounce | pivot:2.0, bb:1.5, rsi:1.0 | chop, compression |

Each has param_ranges with CONFIDENCE_THRESHOLD: [55, 60, 65] (some add 70), and some add VOLUME_SPIKE_THRESHOLD: [1.5, 2.0].

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/families.py tests/research/test_families.py
git commit -m "feat(research): add families 6-18 using new indicators"
```

---

## Task 5: Stage 3 Evaluator (Parameter Perturbation)

**Files:**
- Create: `bot/research/stage3.py`
- Create: `tests/research/test_stage3.py`

- [ ] **Step 1: Write failing tests**

Create `tests/research/test_stage3.py`:

```python
import pytest, numpy as np

def test_perturb_int_param():
    from bot.research.stage3 import _perturb_value
    val = _perturb_value(100, "int", magnitude=0.15, rng=np.random.RandomState(42))
    assert isinstance(val, int) and 85 <= val <= 115

def test_perturb_float_param():
    from bot.research.stage3 import _perturb_value
    val = _perturb_value(1.0, "float", magnitude=0.15, rng=np.random.RandomState(42))
    assert isinstance(val, float) and 0.85 <= val <= 1.15

def test_perturb_bool_param():
    from bot.research.stage3 import _perturb_value
    val = _perturb_value(True, "bool", magnitude=0.15, rng=np.random.RandomState(42))
    assert isinstance(val, bool)

def test_stage3_pass():
    from bot.research.stage3 import Stage3Evaluator
    ev = Stage3Evaluator(mc_iterations=10)
    sums = [{"return_pct": 10.0, "max_dd": 15.0, "sharpe": 0.8, "profit_factor": 1.5, "trades": 30} for _ in range(10)]
    r = ev.evaluate_from_summaries("psp_test", 12.0, sums)
    assert r.passed is True and r.survival_rate >= 0.6

def test_stage3_fail_low_survival():
    from bot.research.stage3 import Stage3Evaluator
    ev = Stage3Evaluator(mc_iterations=10)
    bad = [{"return_pct": -20.0, "max_dd": 40.0, "sharpe": -0.5, "profit_factor": 0.5, "trades": 30} for _ in range(8)]
    good = [{"return_pct": 5.0, "max_dd": 10.0, "sharpe": 0.5, "profit_factor": 1.2, "trades": 30} for _ in range(2)]
    r = ev.evaluate_from_summaries("psp_test", 12.0, bad + good)
    assert r.passed is False and r.survival_rate < 0.6

def test_stage3_fail_cliff():
    from bot.research.stage3 import Stage3Evaluator
    ev = Stage3Evaluator(mc_iterations=10)
    sums = [{"return_pct": 1.0, "max_dd": 10.0, "sharpe": 0.3, "profit_factor": 1.1, "trades": 30} for _ in range(10)]
    r = ev.evaluate_from_summaries("psp_test", 20.0, sums)
    assert r.passed is False and "cliff" in (r.reject_reason or "").lower()
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement Stage 3**

Create `bot/research/stage3.py` with:

- `_perturb_value(value, param_type, magnitude, rng, bounds)` — perturbs int (+-15pct rounded), float (+-15pct), bool (flip)
- `perturb_config(config_overrides, param_types, magnitude, rng)` — perturbs all params
- `Stage3Evaluator(mc_iterations=50, perturbation_pct=0.15, survival_threshold=0.60, cliff_threshold=0.50, p5_floor=-30.0)`
  - `_is_surviving(summary)`: return_pct > 0 AND max_dd < 50 AND (sharpe > 0.1 OR profit_factor > 1.05)
  - `evaluate_from_summaries(passport_id, original_return, perturbed_summaries)` -> Stage3Result
  - Pass criteria: survival_rate >= 60pct, mean within 50pct of original, p5 > -30

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/stage3.py tests/research/test_stage3.py
git commit -m "feat(research): add Stage 3 parameter perturbation evaluator"
```

---

## Task 6: Stage 4 Evaluator (Orthogonality + Portfolio)

**Files:**
- Create: `bot/research/stage4.py`
- Create: `tests/research/test_stage4.py`

- [ ] **Step 1: Write failing tests**

Create `tests/research/test_stage4.py`:

```python
import numpy as np, pandas as pd, pytest

def test_equity_correlation():
    from bot.research.stage4 import calc_equity_correlation
    rng = np.random.RandomState(42)
    a = pd.Series(np.cumsum(rng.normal(0, 1, 100)))
    b = pd.Series(np.cumsum(rng.normal(0, 1, 100)))
    assert -1 <= calc_equity_correlation(a, b) <= 1

def test_trade_overlap_zero():
    from bot.research.stage4 import calc_trade_overlap
    a = [{"symbol": "BTC", "direction": "LONG", "entry_bar": 0, "exit_bar": 10}]
    b = [{"symbol": "ETH", "direction": "LONG", "entry_bar": 0, "exit_bar": 10}]
    assert calc_trade_overlap(a, b) == 0.0

def test_trade_overlap_full():
    from bot.research.stage4 import calc_trade_overlap
    t = [{"symbol": "BTC", "direction": "LONG", "entry_bar": 0, "exit_bar": 10}]
    assert calc_trade_overlap(t, t) == 1.0

def test_dd_coincidence():
    from bot.research.stage4 import calc_dd_coincidence
    dd_a = pd.Series([0, -5, -15, -12, -8, 0, 0, 0, 0, 0])
    dd_b = pd.Series([0, -3, -12, -14, -6, 0, 0, 0, 0, 0])
    assert calc_dd_coincidence(dd_a, dd_b, threshold=10, window=5) > 0

def test_composite_utility():
    from bot.research.stage4 import calc_composite_utility
    u = calc_composite_utility(sharpe=1.5, calmar=0.8, max_dd=20.0)
    assert abs(u - (1.5 + 0.8) / (20.0 / 30.0)) < 0.01

def test_select_portfolio():
    from bot.research.stage4 import Stage4Evaluator
    rng = np.random.RandomState(42)
    cands = [{"passport_id": f"psp_{i}", "family": f"fam_{i%3}",
              "sharpe": 0.8+i*0.1, "calmar": 0.5+i*0.05, "max_dd": 15.0+i,
              "equity_curve": list(np.cumsum(rng.normal(0.1, 1, 60))),
              "trades": [{"symbol": f"S{i}", "direction": "LONG", "entry_bar": i*10, "exit_bar": i*10+5}],
              "dd_series": list(rng.uniform(-20, 0, 60))} for i in range(5)]
    result = Stage4Evaluator(family_cap=3, cluster_cap=3).select_portfolio(cands)
    assert 0 < len(result.selected_passport_ids) <= 20
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement Stage 4**

Create `bot/research/stage4.py` with:

- `calc_equity_correlation(curve_a, curve_b)` — Pearson on daily returns
- `calc_trade_overlap(trades_a, trades_b)` — fraction overlapping in symbol+direction+time
- `calc_dd_coincidence(dd_a, dd_b, threshold=10, window=5)` — fraction of deep-DD bars coinciding
- `calc_composite_utility(sharpe, calmar, max_dd)` — (sharpe+calmar)/(max_dd/30)
- `calc_marginal_contribution(existing_utility, new_utility)` — delta
- `Stage4Evaluator(family_cap=3, cluster_cap=3, min_delta_utility=0.05, max_equity_corr=0.4, max_trade_overlap=0.2, max_dd_coincidence=0.3, target_min=10, target_max=20)`
  - `select_portfolio(candidates)` -> Stage4Result
  - Ranks by utility, applies family cap, triple overlap check, marginal contribution test

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/stage4.py tests/research/test_stage4.py
git commit -m "feat(research): add Stage 4 orthogonality + portfolio construction"
```

---

## Task 7: Versioning v2 Registry

**Files:**
- Create: `bot/research/registry.py`
- Create: `tests/research/test_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/research/test_registry.py`:

```python
import os, pytest, tempfile

@pytest.fixture
def registry_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d

def test_register_new(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="ema-fast", family="ema_crossover", version="1.0",
                       config={"INDICATOR_WEIGHTS": {"ema_trend": 2.0}})
    assert pid.startswith("psp_")
    assert reg.get(pid)["status"] == "generated"

def test_passport_file_created(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="t", family="t", version="1.0", config={})
    assert os.path.exists(os.path.join(registry_dir, "passports", f"{pid}.json"))

def test_status_lifecycle(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="t", family="t", version="1.0", config={})
    reg.update_status(pid, "backtested")
    assert reg.get(pid)["status"] == "backtested"
    reg.update_status(pid, "paper_live")
    assert reg.get(pid)["status"] == "paper_live"

def test_invalid_transition(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    pid = reg.register(slug="t", family="t", version="1.0", config={})
    with pytest.raises(ValueError):
        reg.update_status(pid, "production")

def test_lineage(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    parent = reg.register(slug="v1", family="ema", version="1.0", config={})
    child = reg.register(slug="v2", family="ema", version="1.1", config={},
                         parent_id=parent, lineage_type="param_tweak")
    e = reg.get(child)
    assert e["lineage"]["parent_passport_id"] == parent
    assert e["lineage"]["root_passport_id"] == parent

def test_list_by_family(registry_dir):
    from bot.research.registry import PassportRegistry
    reg = PassportRegistry(registry_dir)
    reg.register(slug="a", family="ema", version="1.0", config={})
    reg.register(slug="b", family="rsi", version="1.0", config={})
    reg.register(slug="c", family="ema", version="1.1", config={})
    assert len(reg.list_by_family("ema")) == 2
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement registry**

Create `bot/research/registry.py` with:

- `VALID_TRANSITIONS` dict defining allowed status changes
- `PassportRegistry(base_dir)` — manages passports_dir + registry.json
  - `register(slug, family, version, config, parent_id, lineage_type)` -> passport_id
  - `get(passport_id)` -> dict or None
  - `update_status(passport_id, new_status)` — validates transition
  - `list_by_family(family)`, `list_by_status(status)`, `list_all()`
- Passport files are immutable (written once to passports/psp_xxx.json)
- Registry.json holds mutable state (status, timestamps)
- Status lifecycle: generated -> backtested -> paper_live -> candidate -> production -> retired -> archived

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/registry.py tests/research/test_registry.py
git commit -m "feat(research): add Versioning v2 passport registry"
```

---

## Task 8: Legacy Passport Adapter

**Files:**
- Create: `bot/research/legacy_adapter.py`
- Create: `tests/research/test_legacy_adapter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/research/test_legacy_adapter.py`:

```python
import os, pytest

def test_convert_v1():
    from bot.research.legacy_adapter import convert_v1_to_v2
    v1 = {"name": "OG", "version": "0.1",
          "indicator_weights": {"ema_trend": 1.0}, "confidence_threshold": 54}
    v2 = convert_v1_to_v2(v1)
    assert v2["schema_version"] == 2
    assert v2["lineage"]["lineage_type"] == "migration"

def test_scan_and_convert():
    from bot.research.legacy_adapter import scan_and_convert
    d = "pumpradar-passports/configs"
    if not os.path.exists(d):
        pytest.skip("No legacy passports")
    results = scan_and_convert(d)
    assert len(results) > 0
    assert all(r["schema_version"] == 2 for r in results)
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/research/legacy_adapter.py` with:

- `FAMILY_MAP` dict mapping legacy names to family names (og->balanced_all, hiddengem->hidden_gem_variant, etc.)
- `convert_v1_to_v2(v1_config)` -> v2 passport dict (schema_version=2, lineage_type="migration")
- `scan_and_convert(passport_dir)` -> list of v2 dicts

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/legacy_adapter.py tests/research/test_legacy_adapter.py
git commit -m "feat(research): add legacy v1-to-v2 passport adapter"
```

---

## Task 9: Pipeline Extension (Stage 3 + Stage 4)

**Files:**
- Modify: `bot/research/pipeline.py`
- Create: `tests/research/test_pipeline_extended.py`

- [ ] **Step 1: Write failing tests**

```python
def test_pipeline_has_run_stage3():
    from bot.research.pipeline import ResearchPipeline
    assert hasattr(ResearchPipeline, "run_stage3")

def test_pipeline_has_run_stage4():
    from bot.research.pipeline import ResearchPipeline
    assert hasattr(ResearchPipeline, "run_stage4")

def test_pipeline_has_run_full_4stage():
    from bot.research.pipeline import ResearchPipeline
    assert hasattr(ResearchPipeline, "run_full_4stage")
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Extend pipeline**

Add to `bot/research/pipeline.py`:

- Import Stage3Evaluator, perturb_config, Stage4Evaluator, EvalResult
- `run_stage3(candidates, mc_iterations=50)` — for each candidate: run MC perturbations via perturb_config + run_backtest, then evaluate_from_summaries. Returns survivors list.
- `run_stage4(candidates)` — build candidate dicts with metrics from run_backtest, call Stage4Evaluator.select_portfolio(). Returns Stage4Result.
- `run_full_4stage(families, max_per_family, mc_iterations)` — generate -> S1 -> S2 -> S3 -> S4. Returns portfolio.

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/research/pipeline.py tests/research/test_pipeline_extended.py
git commit -m "feat(research): extend pipeline with Stage 3 + 4 evaluation"
```

---

## Task 10: Full Test Suite Verification

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Fix any failures**

- [ ] **Step 3: Verify import chain**

Run: `python -c "from bot.research.stage3 import Stage3Evaluator; from bot.research.stage4 import Stage4Evaluator; from bot.research.registry import PassportRegistry; from bot.research.legacy_adapter import scan_and_convert; print('All Plan 2 modules OK')"`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test(research): full Plan 2 test suite verified"
```

