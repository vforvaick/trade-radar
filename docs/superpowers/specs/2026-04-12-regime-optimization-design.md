# Per-Passport Regime Optimization — Design Spec

> **Created:** 2026-04-12 (Session 11d)
> **Status:** Approved — ready for implementation plan
> **Philosophy:** Each passport is an autonomous trading agent. Maximize each independently. No cross-passport interference.

---

## Problem Statement

Currently all 25 passports trade in all market regimes with identical parameters. This causes:
1. **Wrong-regime trades:** Trend-followers fire in HIGH_VOL_CHOP, losing money
2. **Uniform risk:** Same confidence threshold, position limits, risk size regardless of regime
3. **No adaptation:** Passport can't tighten behavior in uncertain regimes or loosen in its sweet spot

**Day 1 example:** Apr 7, BTC in TREND_UP — trend-following passports fired 549 SHORT signals, losing $6,496. Hard gate would have prevented 100% of these.

## Design Philosophy

> "25 passports = 25 autonomous agents. Each must be maximized for its niche. The only external factor is market regime. Equal treatment. No cross-passport interference."

This is a **Strategy Maximizer** approach, not a Fund Manager approach:
- No portfolio-level caps or rebalancing
- No capital shifting between passports
- Each passport manages its own risk independently
- The market (via regime detection) is the only input that changes behavior

## Solution: Unified `regime_params` Config

### Passport JSON Schema (extended)

```json
{
  "name": "PressureReader",
  "emoji": "🌊",
  "version": "0.4",
  "enabled": true,
  "description": "...",
  "active_regimes": ["TREND_UP", "HIGH_VOL_CHOP"],
  "config_overrides": {
    "INDICATOR_WEIGHTS": { ... },
    "DIRECTION_BIAS": "LONG_ONLY",
    "CONFIDENCE_THRESHOLD": 54,
    "...": "base settings (existing, unchanged)"
  },
  "regime_params": {
    "TREND_UP": {
      "CONFIDENCE_THRESHOLD": 54,
      "MAX_OPEN_POSITIONS": 10,
      "RISK_PER_TRADE": 0.03,
      "DIRECTION_BIAS": "LONG_ONLY",
      "USE_TRAILING_STOP": true,
      "ATR_TRAIL_MULTIPLIER": 2.5
    },
    "HIGH_VOL_CHOP": {
      "CONFIDENCE_THRESHOLD": 60,
      "MAX_OPEN_POSITIONS": 5,
      "RISK_PER_TRADE": 0.02,
      "DIRECTION_BIAS": "LONG_ONLY",
      "USE_TRAILING_STOP": false
    }
  }
}
```

### Config Resolution Order

```
1. bot/config.py defaults (global baseline)
2. passport.config_overrides (passport baseline — existing behavior)
3. passport.regime_params[current_regime] (regime-specific tuning — NEW)
```

**Rule:** Later overrides earlier. `regime_params` keys override both `config_overrides` and global defaults.

**If `regime_params` is empty or missing:** Falls back to `config_overrides` only (backward compatible).

**If current regime not in `active_regimes`:** Skip scan entirely (hard gate).

### Supported `regime_params` Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `CONFIDENCE_THRESHOLD` | int | 54 | Min confidence to fire signal |
| `MAX_OPEN_POSITIONS` | int | 10 | Max simultaneous positions |
| `RISK_PER_TRADE` | float | 0.03 | Fraction of equity risked per trade |
| `DIRECTION_BIAS` | str | "BOTH" | "LONG_ONLY", "SHORT_ONLY", or "BOTH" |
| `USE_TRAILING_STOP` | bool | false | Enable ATR trailing stop after TP2 |
| `ATR_TRAIL_MULTIPLIER` | float | 2.5 | ATR × this = trail distance |

**Extensible:** Any key from `bot/config.py` can be added to `regime_params` in the future. The application logic doesn't need to know which keys exist — it just does `setattr(config, key, value)` for each.

## Implementation: Hard Gate

### Where (PassportRunner.run_scan_cycle)

```python
# In run_scan_cycle(), before scanning each passport:
current_regime = self.scanner.btc_trend

for passport in self.passports:
    if not passport.enabled:
        continue

    # === HARD GATE (NEW) ===
    if passport.active_regimes and current_regime not in passport.active_regimes:
        logger.info(f"[{passport.name}] Skipped — regime {current_regime} not in {passport.active_regimes}")
        continue

    # Apply base overrides (existing)
    self._apply_overrides(passport.config_overrides)

    # === REGIME PARAMS (NEW) ===
    regime_overrides = passport.regime_params.get(current_regime, {})
    for key, value in regime_overrides.items():
        setattr(config, key, value)

    # Continue with scan...
```

### Backward Compatibility

- Passports without `active_regimes` → trade in ALL regimes (no gate)
- Passports without `regime_params` → use `config_overrides` only
- Existing behavior 100% preserved for passports that don't opt in

## Implementation: ATR Trailing Stop Fix

### Current Bug (position_manager.py)

The existing trailing stop code in `_check_position()` already uses ATR:
```python
trail_dist = position.signal.atr_at_entry * config.ATR_TRAIL_MULTIPLIER
```

This was fixed in Session 9 (ATR fix). The issue is:
1. `USE_TRAILING_STOP = false` globally — never activated
2. `ATR_TRAIL_MULTIPLIER = 2.0` — potentially too tight for 1H crypto

### Fix

1. Make `USE_TRAILING_STOP` and `ATR_TRAIL_MULTIPLIER` per-passport via `config_overrides` or `regime_params`
2. Change default `ATR_TRAIL_MULTIPLIER` from 2.0 → 2.5
3. Each passport can opt-in per regime:
   - Trailing in TREND_UP (ride the trend) ✅
   - No trailing in HIGH_VOL_CHOP (too noisy, gets whipped) ❌

### Backtest Validation (Required)

Before enabling trailing stop for any passport:
1. Run backtest: current TP1/TP2/TP3 cascade (baseline)
2. Run backtest: same settings + `USE_TRAILING_STOP=true` + `ATR_TRAIL_MULTIPLIER=2.5`
3. Compare return, max DD, profit factor
4. Only enable if trailing shows improvement
5. Test multipliers: 2.0, 2.5, 3.0 — pick optimal per passport

## Regime Assignments

### Proposed `active_regimes` per passport

**Trend-Following (trade WITH the trend):**

| Passport | active_regimes | Direction Strategy |
|----------|---------------|-------------------|
| HiddenGem | TREND_UP, TREND_DOWN | BOTH |
| Sniper | TREND_UP, TREND_DOWN | BOTH |
| VolumeKing | TREND_UP, TREND_DOWN | BOTH |
| Momentum | TREND_UP, TREND_DOWN | BOTH |
| DualMA | TREND_UP, TREND_DOWN | BOTH |
| PureTrend | TREND_UP, TREND_DOWN | BOTH |
| TrendMomentum | TREND_UP, TREND_DOWN | BOTH |
| TrendConfirm | TREND_UP, TREND_DOWN | BOTH |
| MinimalEdge | TREND_UP, TREND_DOWN | BOTH |
| OBV Trend | TREND_UP, TREND_DOWN | BOTH |
| Dynamic | TREND_UP, TREND_DOWN | BOTH |

**Mean-Reversion (trade AGAINST extremes in ranging markets):**

| Passport | active_regimes | Direction Strategy |
|----------|---------------|-------------------|
| BBMeanRev | HIGH_VOL_CHOP, LOW_VOL_COMP | BOTH |
| RSIContrarian | HIGH_VOL_CHOP, LOW_VOL_COMP | BOTH |
| ReversalV2 | HIGH_VOL_CHOP, LOW_VOL_COMP | BOTH |

**Breakout (trade the expansion from compression):**

| Passport | active_regimes | Direction Strategy |
|----------|---------------|-------------------|
| BollingerBreakout | LOW_VOL_COMP, TREND_UP, TREND_DOWN | BOTH |
| BollingerBreakoutV2 | LOW_VOL_COMP, TREND_UP, TREND_DOWN | BOTH |
| BollingerBreakoutV3 | LOW_VOL_COMP, TREND_UP, TREND_DOWN | BOTH |
| BreakoutVol | TREND_UP, TREND_DOWN, LOW_VOL_COMP | BOTH |
| Donchian | LOW_VOL_COMP, TREND_UP, TREND_DOWN | BOTH |

**Hybrid / Flexible:**

| Passport | active_regimes | Direction Strategy |
|----------|---------------|-------------------|
| PressureReader | TREND_UP, HIGH_VOL_CHOP | LONG_ONLY |
| MACDDivergence | TREND_UP, TREND_DOWN, HIGH_VOL_CHOP | BOTH |
| RSIMomentumV2 | TREND_UP, TREND_DOWN, HIGH_VOL_CHOP | BOTH |
| OG | TREND_UP, HIGH_VOL_CHOP | BOTH |
| OG Seasonal | TREND_UP, HIGH_VOL_CHOP | BOTH |
| BalancedSelective | TREND_UP, HIGH_VOL_CHOP | BOTH |

### Default `regime_params` (starting values)

For Phase 1, all passports start with minimal regime differentiation:

```json
"regime_params": {
  "<preferred_regime>": {
    "CONFIDENCE_THRESHOLD": 54,
    "MAX_OPEN_POSITIONS": 10,
    "RISK_PER_TRADE": 0.03
  },
  "<secondary_regime>": {
    "CONFIDENCE_THRESHOLD": 60,
    "MAX_OPEN_POSITIONS": 7,
    "RISK_PER_TRADE": 0.025
  }
}
```

**Logic:** In primary regime, use standard settings. In secondary (less ideal) regime, raise threshold + reduce exposure. These are starting values — will be tuned based on live data.

## Testing Strategy

1. **Unit tests:** Regime gating logic (skip when wrong regime, pass when correct)
2. **Unit tests:** `regime_params` override resolution (base → override → regime_params)
3. **Unit tests:** Backward compat (no `active_regimes` = trade all, no `regime_params` = use base)
4. **Backtest:** ATR trailing stop comparison for top 5 passports
5. **Integration:** Load all 25 passport JSONs, verify no schema errors

## Files to Modify

| File | Change |
|------|--------|
| `bot/passport_runner.py` | Hard gate check + regime_params application in scan loop |
| `bot/config.py` | ATR_TRAIL_MULTIPLIER default 2.0 → 2.5 |
| All 25 passport JSONs | Add `active_regimes` + `regime_params` |
| `passports/VERSIONS.md` | Version bump entries |
| `tests/` | New tests for gating + regime_params |
| `docs/FINDINGS.md` | Session 11d/e update |

## What This Does NOT Include

- ❌ Cross-passport symbol caps (paper trading = isolated)
- ❌ Equity rebalancing (equal treatment)
- ❌ Passport disabling/pruning (discovery mode)
- ❌ Per-regime indicator weight tuning (Phase 2)
- ❌ Self-adaptive parameters (Phase 2)
- ❌ Portfolio-level risk management (not applicable to discovery phase)

## Success Criteria

1. Each passport only trades in its assigned regimes
2. Regime-specific risk params are applied correctly
3. No trade is opened in a wrong regime
4. ATR trailing stop is available per-passport (opt-in, backtest-validated)
5. All existing tests pass + new tests cover new logic
6. System is transparent: every skip/override is logged
