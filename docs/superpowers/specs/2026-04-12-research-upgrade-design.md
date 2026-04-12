# Design: Full Research Upgrade — Promote Survivors + Pressure Families + Fold Fix

**Date:** 2026-04-12  
**Status:** Approved  
**Session:** 9d85c425 (Checkpoint 18+)

## Problem Statement

Phase 4 research produced 3 Stage 2 survivors (first ever!), but the pipeline has two structural issues:
1. Stage 2 uses only 1 walk-forward fold for 180d data (train=120d + test=60d = exactly 180d)
2. PressureReader is our most profitable live passport but the research pipeline's `pressure_reader` family lacks LONG_ONLY direction bias — the key to its success

## Scope

Three workstreams executed sequentially:

### WS1: Promote 3 Stage 2 Survivors to Paper Trading

Create passport JSONs in `passports/cryptopass-research/`:

**1. rsi_momentum_v2.json**
- Indicators: rsi_position=2.0, rsi_divergence=1.5, ema_trend=0.5, volume_spike=1.0 (rest 0.0)
- RSI_PERIOD=10, VOLUME_SPIKE_THRESHOLD=1.5, CONFIDENCE_THRESHOLD=65
- Stage 2 stats: Sharpe=1.96, median_ret=+7.3%
- BTC_TREND_WEIGHTS: mean-reversion-style (all 1.0 except TREND_DOWN=0.8)
- MAX_OPEN_POSITIONS_PER_PASSPORT=25, USE_TRAILING_STOP=false

**2. bollinger_breakout_v2.json**
- Indicators: bb_position=2.0, volume_spike=1.5, pressure=1.0 (rest 0.0)
- BB_PERIOD=15, BB_STD=1.5, VOLUME_SPIKE_THRESHOLD=1.5, CONFIDENCE_THRESHOLD=50
- Stage 2 stats: Sharpe=2.70, median_ret=+2.1%
- Note: conf=50 is below default 54, needs override
- BTC_TREND_WEIGHTS: mean-reversion (all 1.0)

**3. bollinger_breakout_v3.json** (v2 variant with higher selectivity)
- Same indicators as v2
- CONFIDENCE_THRESHOLD=55
- Stage 2 stats: Sharpe=1.22, median_ret=+1.2%

All three: enabled=true, version="0.1", changelog with Stage 2 backtest stats.
Update `passports/VERSIONS.md` with new entries.

### WS2: Enhance Pressure Research Families

**Add `pressure_flow_long` family** to `bot/research/families.py`:
```python
"pressure_flow_long": {
    "name": "Pressure Flow Long",
    "description": "PressureReader-inspired: pressure + candle LONG only",
    "weights": _w(pressure=2.0, candle_direction=1.5, volume_spike=1.0),
    "param_ranges": {
        "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0, 2.5],
        "CONFIDENCE_THRESHOLD": [55, 60, 65],
        "DIRECTION_BIAS": ["LONG_ONLY"],
    },
    "compatible_regimes": ["TREND_UP", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
    "min_trades": 20,
}
```

**Rationale:** Mirrors live PressureReader's actual config (LONG_ONLY + pressure + candle_direction). The existing `pressure_reader` family has no direction bias and the `pressure_flow_short` family is SHORT_ONLY. Neither captures PressureReader's winning formula.

**Also add `pressure_momentum_long`** (pressure + RSI for momentum confirmation):
```python
"pressure_momentum_long": {
    "name": "Pressure Momentum Long",
    "description": "Pressure + RSI momentum for long entries",
    "weights": _w(pressure=2.0, rsi_position=1.5, candle_direction=1.0, volume_spike=1.0),
    "param_ranges": {
        "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
        "CONFIDENCE_THRESHOLD": [55, 60, 65],
        "DIRECTION_BIAS": ["LONG_ONLY"],
    },
    "compatible_regimes": ["TREND_UP", "HIGH_VOL_CHOP"],
    "min_trades": 20,
}
```

### WS3: Fix Stage 2 Fold Strategy

**Current:** train=120d, test=60d, fold_size=180d, slide=30d  
→ For 180d data: only 1 fold (180d fits once, 210d > 180d for second fold)

**New:** train=90d, test=45d, fold_size=135d, slide=45d  
→ For 270d data: `(270 - 135) / 45 + 1 = 4 folds`

**Changes in `bot/research/pipeline.py`:**
- Update `_calc_folds()` default params: `train_days=90, test_days=45, slide=45`
- Pass `--days` from CLI through to fold calculation
- Log fold count at Stage 2 start for visibility

**Changes in `bot/research/evaluator.py`:**
- `min_positive_folds_ratio=0.67` stays (3 of 4 folds must be positive)
- For 4 folds: need ≥3 positive → more robust than single-fold pass/fail

**CLI change:** Default `--days 270` in `run_research.py` (was 180d).

### Deployment

1. Commit all changes
2. Push to GitHub
3. Deploy to VPS: `ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && sudo systemctl restart cryptopass.service"`
4. Validate with runbook checklist
5. Run research locally: `uv run python run_research.py --all --max-per-family 5 --days 270`

## Testing

- Existing test suite must stay green (383 tests)
- No new tests needed for passport JSONs (they're data)
- Fold calculation change should have a test verifying 270d produces 4 folds
- Pressure family additions are data-only (families dict), no logic change

## Risks

1. **Bollinger Breakout v2 conf=50 below default 54** — could produce many low-quality signals. Mitigated: it passed Stage 2 with this threshold.
2. **270d data requires more API calls at prefetch** — ~1.5x more candles per symbol. Cache handles this efficiently.
3. **4 folds may be too strict** — strategies that barely passed 1 fold might fail 3-of-4. This is a feature, not a bug — it means the previous results were insufficiently validated.

## Success Criteria

- 3 new passports appear in VPS logs during next scan cycle
- Research pipeline produces 3+ folds per Stage 2 candidate
- At least 1 pressure_flow_long variant passes Stage 1
- Total runtime ≤ 4 hours with KlineCache
