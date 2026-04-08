# Session 9 — Research Quality Pairs + New Passports + ATR Fix

> Date: 2026-04-08  
> Status: Approved for implementation  
> Branch target: `feat/session9-research-passports-atr`

---

## Problem Statement

Live paper trading (16h) reveals 3 actionable gaps:

1. **No downtrend strategy** — all trend-following passports are down −60% to −140% in current bear market. The system has no passport designed to profit from bearish conditions.
2. **Phase 4 research results unreliable** — current run used meme/low-cap pairs (top Binance volume = BANANA, BEAT, BLU). Results for `vwap_deviation` and `pivot_bounce` are suspicious (Stage1 −16% but Stage2 +10% via 1 lucky fold).
3. **ATR trailing stop never worked** — `add_atr()` exists in `indicators.py` but is never called in the scoring pipeline, so `atr_at_entry` is always `None`. The trailing stop silently falls back to a fixed-distance formula that was empirically proven destructive (−81.3%). This is also why `USE_ATR_EXITS=True` is broken.

---

## Approach: Research-Driven (Approved)

Re-run Phase 4 with quality pairs first to produce reliable survivor configs, then build passports from those configs. Simultaneously fix ATR (independent of research). Build passes from Phase 4 results after run completes.

---

## Phase A: Research Re-Run with Quality Pairs

### Goals
- Produce reliable Stage2 survivors backed by stable, liquid pairs
- Add SHORT-biased strategy families to the generator
- Identify strategies that specifically survive **Downtrend regime window** in Stage 2

### Quality Pairs List (hardcoded)
```python
QUALITY_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
]
```
Rationale: tier-1 coins with deep liquidity, stable 1H volatility, long Binance history. Will produce consistent backtest results across runs.

### New Strategy Family: `pressure_flow_short`
Add to `bot/research/generator.py` a new family that systematically varies:
- `pressure` weight: [2.0, 2.5, 3.0]
- `candle_direction` weight: [1.0, 1.5, 2.0]
- `ema_trend` weight: [0.5, 1.0]
- `direction_bias`: "SHORT_ONLY" (new config key, see Phase B)
- Confidence: [60, 65]

This family directly tests whether PressureReader's live edge (+43%, 55% WR) can be formalized and validated across regimes.

### Implementation
1. Add `--quality-pairs` flag to `run_research.py` that overrides the top-volume scanner with `QUALITY_PAIRS` list
2. Add `pressure_flow_short` family to generator with `direction_bias: "SHORT_ONLY"`
3. Run: `uv run python run_research.py --all --max-per-family 5 --days 180 --quality-pairs`
4. Expected duration: ~6–8 hours locally

### Success Criteria
- At least 3 Stage2 survivors with `median_return > 0%`
- At least 1 survivor that specifically passes the Downtrend regime fold in Stage 2
- Supersedes prior Phase 4 results (do NOT build passports from old meme-pair results except `rsi_momentum`)

---

## Phase B1: ATR Fix

### Root Cause
`add_atr(df, period=14)` in `bot/indicators.py` is defined but **never called** in the live scoring pipeline. As a result:
- `df['atr']` column never exists when `score_confluence()` returns
- `score_result.get('atr')` always returns `None`
- `sig.atr_at_entry` is always `None` for every position
- `USE_ATR_EXITS=True` computes `sl_atr = None * 2.0` → falls back to SR-based exits silently
- `USE_TRAILING_STOP=True` falls back to `abs(entry_price - sl)` (the fixed-distance broken formula)

### Fix

**Step 1: Call `add_atr()` in `score_confluence()`**
```python
# bot/scorer.py — add at top of score_confluence(), before any indicator calls
from bot.indicators import add_atr
def score_confluence(df, btc_trend="Sideways"):
    df = df.copy()
    add_atr(df, period=14)   # ← ADD THIS LINE
    ...
```
This ensures `df['atr']` is always populated and `score_result['atr']` always returns a float.

**Step 2: Validate existing trailing stop logic is correct (it is)**
The trailing formula in `position_manager.py` is already written correctly:
```python
trail_dist = (sig.atr_at_entry or abs(sig.entry_price - sig.sl)) * ATR_TRAIL_MULTIPLIER
```
- For LONG: `new_sl = high - trail_dist`, ratchets up, guarded by `new_sl > entry_price`
- For SHORT: `new_sl = low + trail_dist`, ratchets down, guarded by `new_sl < entry_price`
- Only fires after TP2 (last 10% of position)

Once Step 1 is applied, this formula will use real ATR. No changes needed to position_manager.py.

**Step 3: Add `TRAILING_STOP_MULTIPLIER` to config (already exists as `ATR_TRAIL_MULTIPLIER = 2.0`)**
Ensure this is overridable per-passport via `config_overrides`. No changes needed — `getattr(config, 'ATR_TRAIL_MULTIPLIER', 2.0)` already reads from config.

### Schema Safety
`atr_at_entry` is already a field in `Signal` dataclass (signals.py:27). No DB migration needed — `atr_at_entry` is stored inside `signal_json` in the positions table.

### Backtest Validation (REQUIRED before enabling)
Before enabling `USE_TRAILING_STOP=True` on any live passport, run backtest comparison:
```bash
uv run python scripts/backtest_atr_comparison.py  # new script
```
Compare for MACDDivergence and PressureReader:
- Baseline: no trailing stop
- ATR trail 2.0x: `USE_TRAILING_STOP=True, ATR_TRAIL_MULTIPLIER=2.0`
- ATR trail 2.5x: `USE_TRAILING_STOP=True, ATR_TRAIL_MULTIPLIER=2.5`

**Only enable `USE_TRAILING_STOP=True` per-passport if backtest shows neutral or better vs baseline.**

### Tests Required
- Unit: `score_confluence()` result contains non-None `atr` value
- Unit: trailing SL ratchet logic (LONG and SHORT) with known ATR value
- Unit: trailing SL respects breakeven constraint
- Unit: trailing SL boundary — doesn't trail below entry for LONG
- Integration: backtest run with `USE_TRAILING_STOP=True` completes without errors

---

## Phase B2: `direction_bias` Feature

### Purpose
Enable passports to restrict signal direction. A `direction_bias: "SHORT_ONLY"` passport will never open LONG positions regardless of confidence score. This is the foundation for dedicated downtrend passports.

### Config Schema (passport JSON)
```json
"config_overrides": {
    "DIRECTION_BIAS": "SHORT_ONLY",   // "LONG_ONLY", "SHORT_ONLY", or null
    ...
}
```

### Implementation
In `bot/passport_runner.py`, after scanning a pair and before calling `position_manager.open_position()`:
```python
bias = getattr(config, 'DIRECTION_BIAS', None)
if bias == "SHORT_ONLY" and signal.direction == "LONG":
    continue  # skip this signal
if bias == "LONG_ONLY" and signal.direction == "SHORT":
    continue
```

No changes to scorer, signal generator, or position_manager. The filter is a pure pre-check at the runner level.

### Default
`DIRECTION_BIAS = None` in `bot/config.py`. All existing passports unaffected.

### Tests Required
- Unit: `SHORT_ONLY` passport skips LONG signals
- Unit: `LONG_ONLY` passport skips SHORT signals
- Unit: `None` bias passes all signals
- Integration: PressureReader SHORT variant passport runs correctly

---

## Phase C: Build New Passports (post Phase 4 re-run)

### Passports to build after Phase 4 completes

**C1: `rsi_momentum` passport**  
Already validated (Stage2 +16.6%, PF=1.94) from previous run. Build regardless of new run results.
```json
{
  "name": "RSIMomentum",
  "config_overrides": {
    "RSI_PERIOD": 10,
    "CONFIDENCE_THRESHOLD": 65,
    "VOLUME_SPIKE_THRESHOLD": 1.5,
    "INDICATOR_WEIGHTS": {
      "ema_trend": 0.5, "macd_signal": 0.0, "rsi_position": 2.0,
      "rsi_divergence": 1.5, "bb_position": 0.0, "volume_spike": 0.0,
      "pressure": 0.0, "candle_direction": 0.0
    }
  }
}
```

**C2: `pressure_reader_short` — downtrend passport**  
Based on PressureReader live edge + `direction_bias: SHORT_ONLY`. Exact weights to be determined from Phase 4 `pressure_flow_short` family results. Provisional config (refine from research):
```json
{
  "name": "PressureReaderShort",
  "config_overrides": {
    "DIRECTION_BIAS": "SHORT_ONLY",
    "CONFIDENCE_THRESHOLD": 60,
    "BTC_TREND_WEIGHTS": {"Uptrend": 0.8, "Sideways": 1.0, "Downtrend": 1.2},
    "INDICATOR_WEIGHTS": {
      "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
      "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 0.0,
      "pressure": 2.5, "candle_direction": 1.5
    }
  }
}
```
Note: `Downtrend: 1.2` means this passport gets a slight boost in confirmed BTC downtrend.

**C3–C5: Top Phase 4 re-run survivors**  
After Phase 4 completes, pick top 3 Stage2 survivors with:
- `median_return > +5%`
- Passes at least 2 of 3 regime folds (Bull, Bear, Sideways)
- PF > 1.2

### Backtest each new passport before live
```bash
uv run python scripts/run_new_passport_backtest.py --passport <name> --days 180 --pairs 10 --quality-pairs
```
Target: return_pct > 0%, PF > 1.0, MaxDD < 25% before adding to VPS.

---

## What Stays Unchanged

- All 21 existing passports remain live (paper trading data is valuable)
- `USE_TRAILING_STOP = False` default unchanged — only per-passport override after backtest validation
- `DIRECTION_BIAS = None` default — existing passports unaffected by new feature
- The 30-day live validation clock continues running for all passports

---

## Implementation Order

```
Phase B1 (ATR fix)     → 1 line in scorer.py + 5 unit tests
Phase B2 (direction_bias) → 3 lines in passport_runner.py + 3 unit tests
Phase A  (re-run)      → CLI flag + generator family + background run (6-8h)
Phase C  (passports)   → after Phase 4 completes, build from results
```

B1 and B2 are independent and can be done in one commit before Phase A starts.

---

## Key Risks

| Risk | Mitigation |
|---|---|
| ATR trailing with wrong multiplier could hurt performance | Backtest validation required before enabling per-passport |
| `direction_bias: SHORT_ONLY` in bull market = very few signals | Acceptable — passport designed for bear regimes only |
| Phase 4 re-run meme pairs sneak in | Hardcode `QUALITY_PAIRS` list, override scanner behavior entirely |
| PressureReader SHORT variant is regime-specific (only works in bear) | Add to changelog, monitor closely, disable in sustained bull run |
