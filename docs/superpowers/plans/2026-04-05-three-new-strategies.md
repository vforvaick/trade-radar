# Three New Trading Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 new passport strategies (DualMA Crossover, Donchian Breakout, OBV Trend), backtest them on quality pairs, enable the profitable ones, deploy to VPS, and update all docs.

**Architecture:** Two strategies require new indicator functions in `bot/indicators.py` + new voting slots in `bot/scorer.py` (with `default=0.0` to not affect existing passports). One strategy is config-only using existing EMA infrastructure. All 3 get passport JSON configs in `pumpradar-passports/configs/`. New indicators default to weight=0.0 for backward compatibility — existing passports are unaffected.

**Tech Stack:** Python, pandas/numpy, existing `bot/indicators.py`, `bot/scorer.py`, `bot/backtester.py`, `scripts/run_new_passport_backtest.py`, `pumpradar-passports/configs/*.json`

> **Note on Pairs Trading**: Pairs trading is architecturally incompatible with the current single-asset scoring model (scanner loops one symbol at a time; no shared state across symbols). Replacing with OBV Trend — on-balance volume signal provides similar "accumulation vs distribution" thesis without requiring dual-asset plumbing.

---

## File Map

| File | Action | What it does |
|------|--------|--------------|
| `bot/indicators.py` | Modify | Add `calc_donchian_channel()`, `calc_obv_signal()` |
| `bot/scorer.py` | Modify | Add `donchian_signal`, `obv_signal` to votes + signals_detail; use `default=0.0` |
| `pumpradar-passports/configs/dual_ma.json` | Create | EMA(10/20/50) crossover, ema_trend=4.0, volume=2.0 |
| `pumpradar-passports/configs/donchian_breakout.json` | Create | Donchian(20) breakout, donchian_signal=3.0, vol=2.0, ema=1.0 |
| `pumpradar-passports/configs/obv_trend.json` | Create | OBV momentum, obv_signal=2.5, ema=1.5, vol=1.0 |
| `tests/test_new_indicators.py` | Create | Tests for calc_donchian_channel + calc_obv_signal |
| `pumpradar-passports/VERSIONS.md` | Modify | Add sections for 3 new passports |
| `docs/FINDINGS.md` | Modify | Add session findings and backtest results |
| `.github/copilot-instructions.md` | Modify | Update passport count, current status |

---

## Task 1: DualMA Crossover passport (config-only)

**Files:**
- Create: `pumpradar-passports/configs/dual_ma.json`

This is pure config — no code changes. Uses existing `calc_ema_trend()` with EMA_FAST=10, EMA_MID=20, EMA_SLOW=50. The crossover signal comes from EMA(10) vs EMA(20): when fast > mid > slow = strong LONG, fast < mid < slow = strong SHORT. Heavy weight on ema_trend (4.0) with volume confirmation (2.0) — all other indicators zeroed.

- [ ] **Step 1: Create `dual_ma.json`**

```bash
cat > pumpradar-passports/configs/dual_ma.json << 'EOF'
{
    "name": "DualMA Crossover",
    "enabled": false,
    "emoji": "📈",
    "version": "0.1",
    "changelog": [
        {
            "version": "0.1",
            "date": "2026-04-05",
            "description": "EMA(10/20) crossover with volume confirmation. Thesis: dual MA crossover captures trend shifts early; volume confirms breakout. All non-EMA indicators zeroed to avoid dilution. Modeled on 151-strategies S5 (MA-based trend).",
            "backtest_90d": null
        }
    ],
    "description": "Pure EMA(10/20) dual MA crossover + volume confirmation. Fast/Mid EMA alignment drives signal; slow EMA (50) provides trend context. All other indicators zeroed — selectivity is the edge.",
    "config_overrides": {
        "EMA_FAST": 10,
        "EMA_MID": 20,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 1.8,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 4.0,
            "macd_signal": 0.0,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 0.0,
            "volume_spike": 2.0,
            "pressure": 0.0,
            "candle_direction": 0.0
        },
        "CONFIDENCE_THRESHOLD": 58,
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 30,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
EOF
echo "Created dual_ma.json"
```

- [ ] **Step 2: Validate JSON is valid**

```bash
cd /path/to/crypto-signal
uv run python -c "import json; d=json.load(open('pumpradar-passports/configs/dual_ma.json')); print('valid:', d['name'])"
```
Expected output: `valid: DualMA Crossover`

- [ ] **Step 3: Verify passport loads without errors**

```bash
uv run python -c "
import json
from bot.passport_runner import Passport
d = json.load(open('pumpradar-passports/configs/dual_ma.json'))
p = Passport(d, 'pumpradar-passports/configs/dual_ma.json')
print('name:', p.name, '| enabled:', p.enabled, '| overrides:', list(p.config_overrides.keys()))
"
```
Expected output: `name: DualMA Crossover | enabled: False | overrides: [list including EMA_FAST, INDICATOR_WEIGHTS, ...]`

- [ ] **Step 4: Commit**

```bash
git add pumpradar-passports/configs/dual_ma.json
git commit -m "feat(passport): add DualMA Crossover v0.1 config (disabled pending backtest)"
```

---

## Task 2: Add `calc_donchian_channel` indicator

**Files:**
- Modify: `bot/indicators.py` (append after line ~249, before `add_atr`)
- Modify: `bot/scorer.py` (add donchian_signal to votes + signals_detail; call calc_donchian_channel at top)

Donchian Channel: N-period high/low range. LONG when current close breaks above the N-period rolling high (momentum breakout). SHORT when breaks below N-period rolling low. NEUTRAL when price is inside channel.

- [ ] **Step 1: Add `calc_donchian_channel` to `bot/indicators.py`**

Add after the `calc_candle_direction` function (around line 249) and before `add_atr`:

```python
def calc_donchian_channel(df: pd.DataFrame, period: int = 20):
    """
    Donchian Channel breakout signal.
    LONG: close breaks above N-period high (upside breakout).
    SHORT: close breaks below N-period low (downside breakout).
    NEUTRAL: price within channel.
    Returns: direction ('LONG', 'SHORT', 'NEUTRAL'), breakout_strength (0.0-1.0)
    """
    if len(df) < period + 1:
        return "NEUTRAL", 0.0

    high_channel = df['high'].rolling(period).max().shift(1)
    low_channel = df['low'].rolling(period).min().shift(1)
    close = df['close']

    last_close = close.iloc[-1]
    last_high = high_channel.iloc[-1]
    last_low = low_channel.iloc[-1]

    if pd.isna(last_high) or pd.isna(last_low):
        return "NEUTRAL", 0.0

    channel_width = last_high - last_low
    if channel_width <= 0:
        return "NEUTRAL", 0.0

    if last_close > last_high:
        # How far above the channel (normalized 0-1, capped at 1)
        strength = min((last_close - last_high) / channel_width, 1.0)
        return "LONG", strength
    elif last_close < last_low:
        strength = min((last_low - last_close) / channel_width, 1.0)
        return "SHORT", strength
    else:
        return "NEUTRAL", 0.0
```

- [ ] **Step 2: Wire `donchian_signal` into `bot/scorer.py`**

In `score_confluence()`, add the indicator call at the top (after `candle_dir = indicators.calc_candle_direction(df)`, before the `votes = {` dict):

```python
    donchian_dir, donchian_str = indicators.calc_donchian_channel(df)
```

Add to `votes` dict (after `"candle_direction": candle_dir,`):
```python
        "donchian_signal": donchian_dir,
```

Add to `signals_detail` dict (after `"candle_direction": {"direction": candle_dir},`):
```python
        "donchian_signal": {"direction": donchian_dir, "strength": donchian_str},
```

In the weight loop, the existing `active_weights.get(indicator, 1.0)` will be called for `donchian_signal`. To ensure backward compatibility for existing passports (which don't set this key), we need to **add a special case** in the weight lookup. The cleanest fix: after `w = active_weights.get(indicator, 1.0)`, add:

```python
        # New indicators (added after initial deployment) default to 0 to
        # not affect existing passports that don't declare them.
        if indicator in ("donchian_signal", "obv_signal") and indicator not in active_weights:
            w = 0.0
```

- [ ] **Step 3: Run smoke test — scorer still produces signals**

```bash
cd /path/to/crypto-signal
uv run python -c "
from bot import indicators, scorer, config
import pandas as pd, numpy as np
np.random.seed(42)
n = 100
df = pd.DataFrame({'open': np.random.uniform(100,110,n), 'high': np.random.uniform(110,120,n), 'low': np.random.uniform(90,100,n), 'close': np.random.uniform(100,110,n), 'volume': np.random.uniform(1000,5000,n)})
result = scorer.score_confluence(df)
print('direction:', result['direction'], '| confidence:', round(result['confidence'],1), '| go:', result['go'])
print('donchian in signals:', 'donchian_signal' in result['signals'])
"
```
Expected: no exception, `donchian_signal` in result['signals']

- [ ] **Step 4: Commit**

```bash
git add bot/indicators.py bot/scorer.py
git commit -m "feat(indicators): add calc_donchian_channel + wire donchian_signal into scorer (default weight=0)"
```

---

## Task 3: Add `calc_obv_signal` indicator

**Files:**
- Modify: `bot/indicators.py` (add `calc_obv_signal` after existing `add_obv`)
- Modify: `bot/scorer.py` (add `obv_signal` to votes + signals_detail + call at top)

OBV (On-Balance Volume): cumulative volume direction proxy. OBV rising = buying pressure. We signal directionally by comparing OBV to its 20-period EMA: OBV > OBV_EMA = LONG accumulation, OBV < OBV_EMA = SHORT distribution.

- [ ] **Step 1: Add `calc_obv_signal` to `bot/indicators.py`**

Add directly after `add_obv` (currently lines ~262-269):

```python
def calc_obv_signal(df: pd.DataFrame, period: int = 20):
    """
    OBV directional signal — buying vs selling pressure via cumulative volume.
    OBV > its EMA(period): LONG (accumulation/buying pressure).
    OBV < its EMA(period): SHORT (distribution/selling pressure).
    Returns: direction ('LONG', 'SHORT', 'NEUTRAL'), strength (0.0-1.0)
    """
    if len(df) < period + 2:
        return "NEUTRAL", 0.0

    obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    obv_ema = obv.ewm(span=period, adjust=False).mean()

    last_obv = obv.iloc[-1]
    last_ema = obv_ema.iloc[-1]
    prev_obv = obv.iloc[-2]
    prev_ema = obv_ema.iloc[-2]

    if last_ema == 0:
        return "NEUTRAL", 0.0

    # Normalized distance from EMA (0-1 capped)
    gap_pct = abs(last_obv - last_ema) / (abs(last_ema) + 1e-10)
    strength = min(gap_pct, 1.0)

    if last_obv > last_ema and prev_obv >= prev_ema:
        return "LONG", strength
    elif last_obv < last_ema and prev_obv <= prev_ema:
        return "SHORT", strength
    else:
        return "NEUTRAL", 0.0
```

- [ ] **Step 2: Wire `obv_signal` into `bot/scorer.py`**

Add indicator call at top of `score_confluence()` (after `donchian_dir, donchian_str = ...`):
```python
    obv_dir, obv_str = indicators.calc_obv_signal(df)
```

Add to `votes` dict:
```python
        "obv_signal": obv_dir,
```

Add to `signals_detail` dict:
```python
        "obv_signal": {"direction": obv_dir, "strength": obv_str},
```

The backward-compat guard from Task 2 already covers `obv_signal`:
```python
        if indicator in ("donchian_signal", "obv_signal") and indicator not in active_weights:
            w = 0.0
```

- [ ] **Step 3: Run smoke test**

```bash
uv run python -c "
from bot import indicators, scorer, config
import pandas as pd, numpy as np
np.random.seed(42)
n = 100
close = 100 + np.cumsum(np.random.randn(n)*0.5)
df = pd.DataFrame({'open': close-0.5, 'high': close+1, 'low': close-1, 'close': close, 'volume': np.random.uniform(1000,5000,n)})
result = scorer.score_confluence(df)
print('obv in signals:', 'obv_signal' in result['signals'])
print('donchian in signals:', 'donchian_signal' in result['signals'])
print('obv dir:', result['signals']['obv_signal']['direction'])
print('donchian dir:', result['signals']['donchian_signal']['direction'])
"
```
Expected: no exception, both keys present

- [ ] **Step 4: Commit**

```bash
git add bot/indicators.py bot/scorer.py
git commit -m "feat(indicators): add calc_obv_signal + wire obv_signal into scorer (default weight=0)"
```

---

## Task 4: Tests for new indicators

**Files:**
- Create: `tests/test_new_indicators.py`

- [ ] **Step 1: Create test file**

```python
# tests/test_new_indicators.py
"""Tests for calc_donchian_channel and calc_obv_signal."""
import numpy as np
import pandas as pd
import pytest
from bot.indicators import calc_donchian_channel, calc_obv_signal


def _make_df(closes, highs=None, lows=None, volumes=None, n=50):
    """Build a minimal OHLCV DataFrame padded to n rows."""
    arr = np.array(closes, dtype=float)
    if highs is None:
        highs = arr + 1.0
    if lows is None:
        lows = arr - 1.0
    if volumes is None:
        volumes = np.ones(len(arr)) * 1000.0
    df = pd.DataFrame({
        "open": arr - 0.5,
        "high": np.array(highs, dtype=float),
        "low": np.array(lows, dtype=float),
        "close": arr,
        "volume": np.array(volumes, dtype=float),
    })
    return df


# ── Donchian Channel ─────────────────────────────────────────────────

class TestCalcDonchianChannel:
    def test_upside_breakout_returns_long(self):
        # Price stays flat at 100 for 25 bars, then breaks to 115 (above 20-period high of ~101)
        closes = [100.0] * 25 + [115.0]
        highs  = [101.0] * 25 + [116.0]
        lows   = [99.0]  * 25 + [114.0]
        df = _make_df(closes, highs=highs, lows=lows)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "LONG"
        assert 0.0 < strength <= 1.0

    def test_downside_breakout_returns_short(self):
        closes = [100.0] * 25 + [85.0]
        highs  = [101.0] * 25 + [86.0]
        lows   = [99.0]  * 25 + [84.0]
        df = _make_df(closes, highs=highs, lows=lows)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "SHORT"
        assert 0.0 < strength <= 1.0

    def test_inside_channel_returns_neutral(self):
        closes = [100.0] * 25 + [100.5]
        highs  = [101.0] * 25 + [101.5]
        lows   = [99.0]  * 25 + [99.5]
        df = _make_df(closes, highs=highs, lows=lows)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "NEUTRAL"

    def test_insufficient_data_returns_neutral(self):
        df = _make_df([100.0] * 10)
        direction, strength = calc_donchian_channel(df, period=20)
        assert direction == "NEUTRAL"
        assert strength == 0.0

    def test_strength_capped_at_1(self):
        # Massive breakout — strength should cap at 1.0
        closes = [100.0] * 25 + [1000.0]
        highs  = [101.0] * 25 + [1001.0]
        lows   = [99.0]  * 25 + [999.0]
        df = _make_df(closes, highs=highs, lows=lows)
        _, strength = calc_donchian_channel(df, period=20)
        assert strength <= 1.0


# ── OBV Signal ───────────────────────────────────────────────────────

class TestCalcObvSignal:
    def test_rising_price_volume_returns_long(self):
        # Consistently rising closes with high volume → OBV rises → above EMA
        n = 40
        closes = np.linspace(100, 110, n)
        volumes = np.ones(n) * 2000.0
        df = _make_df(closes, volumes=volumes)
        direction, strength = calc_obv_signal(df, period=10)
        assert direction == "LONG"
        assert 0.0 < strength <= 1.0

    def test_falling_price_volume_returns_short(self):
        n = 40
        closes = np.linspace(110, 100, n)
        volumes = np.ones(n) * 2000.0
        df = _make_df(closes, volumes=volumes)
        direction, strength = calc_obv_signal(df, period=10)
        assert direction == "SHORT"
        assert 0.0 < strength <= 1.0

    def test_flat_price_returns_neutral_or_directional(self):
        # Flat price → OBV near zero → direction may vary, but no exception
        n = 40
        closes = np.ones(n) * 100.0
        volumes = np.ones(n) * 1000.0
        df = _make_df(closes, volumes=volumes)
        direction, strength = calc_obv_signal(df, period=10)
        assert direction in ("LONG", "SHORT", "NEUTRAL")
        assert 0.0 <= strength <= 1.0

    def test_insufficient_data_returns_neutral(self):
        df = _make_df([100.0] * 5)
        direction, strength = calc_obv_signal(df, period=20)
        assert direction == "NEUTRAL"
        assert strength == 0.0

    def test_strength_bounded_0_to_1(self):
        n = 50
        closes = np.linspace(100, 200, n)
        volumes = np.ones(n) * 9999.0
        df = _make_df(closes, volumes=volumes)
        _, strength = calc_obv_signal(df, period=5)
        assert 0.0 <= strength <= 1.0
```

- [ ] **Step 2: Run tests — expect all PASS**

```bash
uv run pytest tests/test_new_indicators.py -v
```
Expected: `10 passed`

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all pre-existing tests still pass (currently 206 passing)

- [ ] **Step 4: Commit**

```bash
git add tests/test_new_indicators.py
git commit -m "test: add tests for calc_donchian_channel and calc_obv_signal"
```

---

## Task 5: Donchian Breakout passport config

**Files:**
- Create: `pumpradar-passports/configs/donchian_breakout.json`

Strategy: Donchian(20) breakout as primary signal (weight=3.0), EMA trend as directional gate (weight=1.0), volume spike as confirmation (weight=2.0). All other indicators = 0. CONFIDENCE_THRESHOLD=58.

- [ ] **Step 1: Create `donchian_breakout.json`**

```bash
cat > pumpradar-passports/configs/donchian_breakout.json << 'EOF'
{
    "name": "Donchian Breakout",
    "enabled": false,
    "emoji": "🔔",
    "version": "0.1",
    "changelog": [
        {
            "version": "0.1",
            "date": "2026-04-05",
            "description": "Donchian(20) channel breakout with EMA trend gate and volume confirmation. Thesis: price breaking 20-period high/low is a genuine breakout signal; EMA alignment filters false breakouts in ranging markets. Modeled on 151-strategies S8 (Donchian breakout).",
            "backtest_90d": null
        }
    ],
    "description": "20-period Donchian channel breakout. Price above 20-day high = LONG, below 20-day low = SHORT. EMA trend gate (weight=1) filters choppy breakouts. Volume spike confirms conviction.",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 1.8,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.0,
            "macd_signal": 0.0,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 0.0,
            "volume_spike": 2.0,
            "pressure": 0.0,
            "candle_direction": 0.0,
            "donchian_signal": 3.0,
            "obv_signal": 0.0
        },
        "CONFIDENCE_THRESHOLD": 58,
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 25,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
EOF
echo "Created donchian_breakout.json"
```

- [ ] **Step 2: Validate JSON + passport loads**

```bash
uv run python -c "
import json
from bot.passport_runner import Passport
d = json.load(open('pumpradar-passports/configs/donchian_breakout.json'))
p = Passport(d, 'pumpradar-passports/configs/donchian_breakout.json')
print('name:', p.name, '| enabled:', p.enabled)
w = p.config_overrides.get('INDICATOR_WEIGHTS', {})
print('donchian weight:', w.get('donchian_signal'), '| obv weight:', w.get('obv_signal'))
"
```
Expected: `donchian weight: 3.0 | obv weight: 0.0`

- [ ] **Step 3: Commit**

```bash
git add pumpradar-passports/configs/donchian_breakout.json
git commit -m "feat(passport): add Donchian Breakout v0.1 config (disabled pending backtest)"
```

---

## Task 6: OBV Trend passport config

**Files:**
- Create: `pumpradar-passports/configs/obv_trend.json`

Strategy: OBV momentum (weight=2.5) as primary accumulation/distribution signal, EMA trend as directional gate (weight=1.5), volume spike as confirmation (weight=1.0). CONFIDENCE_THRESHOLD=55 (slightly lower since OBV signals can be subtle).

- [ ] **Step 1: Create `obv_trend.json`**

```bash
cat > pumpradar-passports/configs/obv_trend.json << 'EOF'
{
    "name": "OBV Trend",
    "enabled": false,
    "emoji": "🌊",
    "version": "0.1",
    "changelog": [
        {
            "version": "0.1",
            "date": "2026-04-05",
            "description": "On-Balance Volume trend signal with EMA directional gate. Thesis: OBV captures smart-money accumulation/distribution before price moves; EMA alignment confirms direction. Replaces Pairs Trading (incompatible with single-asset architecture). Modeled on 151-strategies volume-flow section.",
            "backtest_90d": null
        }
    ],
    "description": "OBV-primary trend passport. OBV > EMA(20) = buying pressure (LONG), OBV < EMA(20) = selling pressure (SHORT). EMA trend confirms direction. No RSI/MACD dilution.",
    "config_overrides": {
        "EMA_FAST": 9,
        "EMA_MID": 21,
        "EMA_SLOW": 50,
        "VOLUME_SPIKE_THRESHOLD": 1.5,
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.5,
            "macd_signal": 0.0,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 0.0,
            "volume_spike": 1.0,
            "pressure": 0.0,
            "candle_direction": 0.0,
            "donchian_signal": 0.0,
            "obv_signal": 2.5
        },
        "CONFIDENCE_THRESHOLD": 55,
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 25,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
EOF
echo "Created obv_trend.json"
```

- [ ] **Step 2: Validate JSON + passport loads**

```bash
uv run python -c "
import json
from bot.passport_runner import Passport
d = json.load(open('pumpradar-passports/configs/obv_trend.json'))
p = Passport(d, 'pumpradar-passports/configs/obv_trend.json')
print('name:', p.name, '| enabled:', p.enabled)
w = p.config_overrides.get('INDICATOR_WEIGHTS', {})
print('obv weight:', w.get('obv_signal'), '| donchian weight:', w.get('donchian_signal'))
"
```
Expected: `obv weight: 2.5 | donchian weight: 0.0`

- [ ] **Step 3: Commit**

```bash
git add pumpradar-passports/configs/obv_trend.json
git commit -m "feat(passport): add OBV Trend v0.1 config (disabled pending backtest)"
```

---

## Task 7: Backtest all 3 new passports

**Files:**
- Run: `scripts/run_new_passport_backtest.py` — but add the 3 new configs to its list

The backtest script needs to include the 3 new passport files. Edit the script's `NEW_PASSPORT_FILES` list, then run it against 90d quality pairs.

- [ ] **Step 1: Add 3 new passports to backtest script**

In `scripts/run_new_passport_backtest.py`, find the `NEW_PASSPORT_FILES` list and add:
```python
    "dual_ma.json",
    "donchian_breakout.json",
    "obv_trend.json",
```

- [ ] **Step 2: Run backtest on quality pairs (90 days)**

```bash
uv run python scripts/run_new_passport_backtest.py --days 90 --pairs 10 2>&1 | tee logs/new3_passports_$(date +%Y%m%d_%H%M%S).log | tail -40
```

Quality pairs auto-selected by the script are BTC/ETH/SOL/BNBUSDT/AAVEUSDT/ADAUSDT/DOTUSDT/LINKUSDT/AVAXUSDT/MATICUSDT.

Expected output: ranked table with return_pct, win_rate, profit_factor for each.

- [ ] **Step 3: Record results in each passport's changelog**

For each of the 3 passports, update `backtest_90d` in their JSON changelog entry with actual results from Step 2. For example, if DualMA returned +5.2% with WR=38%, PF=1.22, 145 trades:

```json
"backtest_90d": {
    "return_pct": 5.2,
    "win_rate": 38.0,
    "trades": 145,
    "profit_factor": 1.22,
    "note": "90d quality pairs (BTC/ETH/SOL/AAVE/BNB/ADA/DOT/LINK/AVAX/MATIC)"
}
```

- [ ] **Step 4: Enable passports that pass the bar (PF >= 1.0)**

For any passport with `profit_factor >= 1.0`, change `"enabled": false` to `"enabled": true` in its JSON config.

- [ ] **Step 5: Commit**

```bash
git add pumpradar-passports/configs/dual_ma.json pumpradar-passports/configs/donchian_breakout.json pumpradar-passports/configs/obv_trend.json scripts/run_new_passport_backtest.py
git commit -m "feat(passport): backtest 3 new strategies, enable profitable ones (DualMA/Donchian/OBV)"
```

---

## Task 8: Update documentation

**Files:**
- Modify: `pumpradar-passports/VERSIONS.md`
- Modify: `docs/FINDINGS.md`
- Modify: `.github/copilot-instructions.md`

- [ ] **Step 1: Add 3 new sections to `VERSIONS.md`**

Append to `pumpradar-passports/VERSIONS.md` after the BBMeanRev section:

```markdown
### 📈 DualMA Crossover (`dual_ma.json`)

| Version | Date | Description |
|---------|------|-------------|
| v0.1 | 2026-04-05 | EMA(10/20) crossover, volume confirmation, all non-EMA zeroed. Thesis: pure MA crossover with volume. Backtest 90d: [fill from results] |

### 🔔 Donchian Breakout (`donchian_breakout.json`)

| Version | Date | Description |
|---------|------|-------------|
| v0.1 | 2026-04-05 | 20-period Donchian channel breakout + EMA gate + volume. Thesis: channel breakout = genuine momentum. Requires new donchian_signal indicator. Backtest 90d: [fill from results] |

### 🌊 OBV Trend (`obv_trend.json`)

| Version | Date | Description |
|---------|------|-------------|
| v0.1 | 2026-04-05 | OBV > EMA(20) = accumulation (LONG), OBV < EMA(20) = distribution (SHORT). Replaces Pairs Trading (incompatible with single-asset arch). Backtest 90d: [fill from results] |
```

Also update the **Version Comparison Quick Reference** table with the 3 new passport rows.

- [ ] **Step 2: Add session findings to `docs/FINDINGS.md`**

Append a new section `## 13. Session 6 — New Indicators + 3 New Passports (Apr 5, 2026)`:

```markdown
## 13. Session 6 — New Indicators + 3 New Passports (Apr 5, 2026)

### Pairs Trading: Architecturally Infeasible
- Pairs Trading requires scanning TWO symbols simultaneously + shared spread state
- Current architecture: scanner loops one symbol at a time, no cross-symbol state
- Decision: replaced with OBV Trend (same "smart money" thesis, single-asset compatible)

### New Indicators Added
- `calc_donchian_channel(df, period=20)`: 20-period channel breakout signal
- `calc_obv_signal(df, period=20)`: OBV vs EMA(20) accumulation signal
- Both default to weight=0.0 for all existing passports (backward compat guard in scorer.py)

### 3 New Passports
| Passport | Thesis | Key Signals | Status |
|----------|--------|-------------|--------|
| DualMA Crossover | Trend-following | EMA(10/20)×4.0 + Vol×2.0 | [backtest result] |
| Donchian Breakout | Channel breakout | Donchian×3.0 + EMA×1.0 + Vol×2.0 | [backtest result] |
| OBV Trend | Accumulation | OBV×2.5 + EMA×1.5 + Vol×1.0 | [backtest result] |

### Design Principle Reinforced
- Fewer indicators = higher signal quality (dilution principle confirmed again)
- All 3 new passports: 2-3 indicators, all others=0
- OBV signal: passive accumulation without needing explicit volume threshold

### Research Engine (Apr 5 overnight)
- 103 candidates generated, Stage 1 running on VPS
- Expected: top 5 ranked by Sharpe ratio
- Action when done: compare against 3 new passports, pick best for Phase 2
```

- [ ] **Step 3: Update `.github/copilot-instructions.md` passport count + status**

Find the line that says something like `19 passports` and update to `22 passports (19 original + 3 new: DualMA, Donchian, OBV)`. Update Current Status to reflect Session 6 additions.

- [ ] **Step 4: Commit docs**

```bash
git add pumpradar-passports/VERSIONS.md docs/FINDINGS.md .github/copilot-instructions.md
git commit -m "docs: update VERSIONS.md, FINDINGS.md, copilot-instructions for 3 new strategies"
```

---

## Task 9: Push to master + deploy to VPS

**Files:**
- Remote: `origin/master`
- VPS: `fight-tres:~/pumpradar-bot`

- [ ] **Step 1: Push all commits to master**

```bash
git push origin master
```

Expected: all 7 commits pushed successfully

- [ ] **Step 2: Deploy to VPS via deploy.sh**

```bash
ssh fight-tres "bash ~/deploy.sh"
```

Expected output: `Fast-forward` git pull + service status showing `active (running)`

- [ ] **Step 3: Verify 3 new passports loaded (even if disabled)**

```bash
ssh fight-tres "sudo journalctl -u pumpradar.service -n 50 --no-pager | grep -E '(DualMA|Donchian|OBV|disabled|enabled|passports loaded)' | head -20"
```

Expected: All 3 new passports appear in logs (disabled or enabled depending on backtest results)

- [ ] **Step 4: Verify no errors**

```bash
ssh fight-tres "sudo journalctl -u pumpradar.service -n 20 --no-pager | grep -E '(ERROR|CRITICAL|Traceback)'"
```

Expected: empty output (no errors)

- [ ] **Step 5: Final status check**

```bash
ssh fight-tres "sudo journalctl -u pumpradar.service -n 5 --no-pager -o short-iso"
```

Expected: bot scanning normally with passport list

---

## Success Criteria

- [ ] All 206+ existing tests pass (no regressions from new indicators)
- [ ] 10 new tests for `calc_donchian_channel` + `calc_obv_signal` pass
- [ ] 3 new passport configs created and valid JSON
- [ ] Existing passports unaffected: `donchian_signal` and `obv_signal` default to weight=0 for them
- [ ] At least 1 of 3 new passports has PF >= 1.0 (worthy of paper trading)
- [ ] VPS running master with 3 new passports loaded
- [ ] VERSIONS.md + FINDINGS.md updated with backtest results
- [ ] No errors in VPS service logs after deploy

---

## Rollback Plan

If new indicators break scorer:
```bash
git revert HEAD~2  # revert indicators.py + scorer.py changes
git push origin master
ssh fight-tres "bash ~/deploy.sh"
```

Passport configs are safe to leave — they'll just be ignored by the old scorer.
