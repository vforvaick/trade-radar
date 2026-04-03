# Advanced Optimization Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Historical drift note:** This is a planning artifact from 2026-03-31, not the current implementation source of truth. It may be superseded by live code and [`docs/crypto_signal_handover.md`](../../crypto_signal_handover.md). Treat the references below as historical context unless they are confirmed against current code.

**Goal:** Upgrade the backtesting engine to V2 (supporting weights, new indicators, ATR exits, 180-day walk-forward) and execute 3 massive grid searches to discover hidden gem strategy variants.

**Architecture:** Modifying the existing modular bot components (`indicators.py`, `scorer.py`, `position_manager.py`, `backtester.py`) to accept dynamic injected configurations rather than hardcoded rules, enabling complete programmatic combinatorics.

**Tech Stack:** Python 3, Pandas, Numpy, Binance Futures API.

**Current-state caveat:** Current code uses `score_confluence()` in [`bot/scorer.py`](/Users/faiqnau/fight/trading/crypto-signal/bot/scorer.py), `cfg_override` in [`bot/backtester.py`](/Users/faiqnau/fight/trading/crypto-signal/bot/backtester.py), fixed TP splitting in [`bot/position_manager.py`](/Users/faiqnau/fight/trading/crypto-signal/bot/position_manager.py), and JSON passport artifacts rather than this plan's imagined free-form overrides. Current ATR exits are `SL=2*ATR` and `TP1=4*ATR`; walk-forward verdicts are driven by Sharpe-delta thresholds, not the older 70% train/test heuristic. Local Binance revalidation can still fail with `57/57 fetch_error`; regenerate from an allowed egress host if you need fresh outputs.

---

### Task 1: Refactor `scorer.py` for Dynamic Indicator Weights

**Files:**
- Modify: `/Users/faiqnau/fight/trading/crypto-signal/bot/scorer.py`
- Modify: `/Users/faiqnau/fight/trading/crypto-signal/bot/config.py`

- [ ] **Step 1: Update `config.py` with default weights**
```python
# bot/config.py (add after existing thresholds)
INDICATOR_WEIGHTS = {
    'volume_spike': 1.0,
    'pressure': 1.0,
    'ema_trend': 1.0,
    'macd_signal': 1.0,
    'rsi_position': 1.0,
    'bb_position': 1.0,
    'rsi_divergence': 1.0,
    'candle_direction': 1.0
}
```

- [ ] **Step 2: Update `scorer.py` to use weights**
```python
# bot/scorer.py (replace the GO/NO-GO logic)
def score_confluence(df, btc_trend="Sideways"):
    # ... existing code ...
    weights = getattr(config, 'INDICATOR_WEIGHTS', {})
    
    total_weight = sum(weights.values())
    # Current code scores the canonical keys:
    # volume_spike, pressure, ema_trend, macd_signal, rsi_position,
    # bb_position, rsi_divergence, candle_direction
    # ... apply weighted voting with those keys ...
```

- [ ] **Step 3: Commit**
```bash
git add bot/config.py bot/scorer.py
git commit -m "feat: add dynamic indicator weighting to scorer"
```

### Task 2: Implement New Indicators (ATR, OBV, StochRSI)

**Files:**
- Modify: `/Users/faiqnau/fight/trading/crypto-signal/bot/indicators.py`

- [ ] **Step 1: Add ATR calculation**
```python
def add_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(period).mean()
    return df
```

- [ ] **Step 2: Add OBV calculation**
```python
def add_obv(df):
    obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    df['obv'] = obv
    df['obv_ema'] = obv.rolling(20).mean()
    return df
```

- [ ] **Step 3: Add StochRSI calculation**
```python
def add_stoch_rsi(df, period=14, smoothK=3, smoothD=3):
    if 'rsi' not in df.columns:
        df = add_rsi(df, period)
    rsi = df['rsi']
    stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min())
    df['stoch_k'] = stoch_rsi.rolling(smoothK).mean() * 100
    df['stoch_d'] = df['stoch_k'].rolling(smoothD).mean()
    return df
```

- [ ] **Step 4: Commit**
```bash
git add bot/indicators.py
git commit -m "feat: add ATR, OBV, and Stochastic RSI indicators"
```

### Task 3: Implement Dynamic ATR-Based Exits

**Files:**
- Modify: `/Users/faiqnau/fight/trading/crypto-signal/bot/signals.py`
- Modify: `/Users/faiqnau/fight/trading/crypto-signal/bot/position_manager.py`

- [ ] **Step 1: Add ATR targets generation to `signals.py`**
```python
def generate_signal(entry_price, direction, confidence, btc_trend, atr_value=None, use_atr=False):
    # ... existing risk mapping ...
    
    if use_atr and atr_value:
        # ATR-based dynamic distances
        sl_price = entry_price - (atr_value * 1.5) if direction == 'LONG' else entry_price + (atr_value * 1.5)
        tp1 = entry_price + (atr_value * 2.0) if direction == 'LONG' else entry_price - (atr_value * 2.0)
        tp2 = entry_price + (atr_value * 3.5) if direction == 'LONG' else entry_price - (atr_value * 3.5)
        tp3 = entry_price + (atr_value * 5.0) if direction == 'LONG' else entry_price - (atr_value * 5.0)
    else:
        # Existing fixed % logic...
```

- [ ] **Step 2: Add Trailing Stop logic to `position_manager.py`**
```python
# In update_positions loop:
if pos['status'] == 'TP1_HIT' and config_overrides.get('USE_TRAILING_STOP', False):
    # Trail SL by 1.5 ATR behind current price
    trail_dist = current_row['atr'] * 1.5
    if direction == 'LONG':
        new_sl = current_price - trail_dist
        if new_sl > pos['sl']: pos['sl'] = new_sl
    else:
        new_sl = current_price + trail_dist
        if new_sl < pos['sl']: pos['sl'] = new_sl
```

- [ ] **Step 3: Commit**
```bash
git add bot/signals.py bot/position_manager.py
git commit -m "feat: add ATR-based dynamic exits and trailing stops"
```

### Task 4: Upgrade Backtester for 180-Day Data & Run Phase 1 (Fix Exits)

**Files:**
- Modify: `/Users/faiqnau/fight/trading/crypto-signal/bot/backtester.py`
- Create: `/Users/faiqnau/fight/trading/crypto-signal/scripts/run_exit_opt.py`

- [ ] **Step 1: Update Backtester `fetch_data` chunking for 180 days**
Increase historical fetch window limit in `run_backtest` to properly paginate 6 months of 1H data safely without binance API limits.

- [ ] **Step 2: Write `scripts/run_exit_opt.py`**
```python
import pandas as pd
from bot.backtester import run_backtest
from bot.config import SYMBOLS

combos = [
    # Option 1: Base
    {'USE_ATR_EXITS': False, 'USE_TRAILING_STOP': False, 'TP_SPLIT': (0.7, 0.2, 0.1)},
    # Option 2: ATR Exits
    {'USE_ATR_EXITS': True, 'USE_TRAILING_STOP': False, 'TP_SPLIT': (0.7, 0.2, 0.1)},
    # Option 3: Trailing Stops
    {'USE_ATR_EXITS': False, 'USE_TRAILING_STOP': True, 'TP_SPLIT': (0.5, 0.3, 0.2)},
    # Option 4: Full Dynamic
    {'USE_ATR_EXITS': True, 'USE_TRAILING_STOP': True, 'TP_SPLIT': (0.5, 0.3, 0.2)}
]

# Run 180 day grid
for i, combo in enumerate(combos):
    res = run_backtest(days=180, cfg_override=combo)
    print(f"Grid {i}: {res}")
```

Historical note: current position management keeps the TP split fixed in `bot/position_manager.py`; do not treat `TP_SPLIT` as a live runtime API even though this plan used it for exploration.

- [ ] **Step 3: Commit**
```bash
git add bot/backtester.py scripts/run_exit_opt.py
git commit -m "feat: expand backtester duration and create exit optimization script"
```

### Task 5: Run Phase 2 (Indicator Lab) & Phase 3 (Twin Bots)

**Files:**
- Create: `/Users/faiqnau/fight/trading/crypto-signal/scripts/run_indicator_lab.py`
- Create: `/Users/faiqnau/fight/trading/crypto-signal/scripts/run_twin_bots.py`

- [ ] **Step 1: Write `scripts/run_indicator_lab.py`**
Script runs 10-20 loops randomizing the current `INDICATOR_WEIGHTS` keys (`volume_spike`, `ema_trend`, etc.) and turning elements on/off to mathematically isolate signal from noise over 180 days.

- [ ] **Step 2: Write `scripts/run_twin_bots.py`**
Script forces `REVERSAL_MODE=True` (buy when RSI < 30 and BB touches lower band, ignoring EMAs). Runs strict comparison against standard momentum mode.

- [ ] **Step 3: Commit**
```bash
git add scripts/run_indicator_lab.py scripts/run_twin_bots.py
git commit -m "feat: script runners for massive parameter grid searches"
```
