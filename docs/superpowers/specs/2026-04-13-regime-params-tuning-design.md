# Phase 2: Per-Regime Parameter Tuning — Design Spec

**Date:** 2026-04-13
**Depends on:** Phase 1 regime optimization (2026-04-12, complete)
**Status:** Draft

## Problem

Phase 1 deployed hard gates (passports skip wrong regimes) and the `regime_params` overlay infrastructure, but all `regime_params` are empty `{}`. Every passport uses identical parameters regardless of whether the market is trending, choppy, or compressing. This leaves money on the table:

- Trend-followers take counter-trend entries in TREND_UP/DOWN (LONG in bear, SHORT in bull)
- Mean-reversion fires low-conviction entries in HIGH_VOL_CHOP (whipsaw losses)
- No risk reduction in dangerous regimes (TREND_DOWN correlated dumps)

## Approach

**Thesis-driven tuning** — parameters set based on strategy logic per regime character, not curve-fit from backtests. Organized by passport category: trend-following → mean-reversion → breakout → hybrid.

**Core thesis per regime:**

| Regime | Character | Parameter Philosophy |
|--------|-----------|---------------------|
| TREND_UP | Clear momentum, low noise | Enforce LONG_ONLY for directional strategies, standard risk |
| TREND_DOWN | Treacherous, correlated dumps | Enforce SHORT_ONLY for directional, +4 confidence, 0.3% risk, cap 15 positions |
| HIGH_VOL_CHOP | Noisy whipsaws | +4 confidence (high conviction only), 0.3% risk, cap 10 positions |
| LOW_VOL_COMPRESSION | Quiet, clean signals | Standard params (signals are clean, no adjustment needed) |

**Parameters in scope:** CONFIDENCE_THRESHOLD, DIRECTION_BIAS, RISK_PER_TRADE_PCT, MAX_OPEN_POSITIONS_PER_PASSPORT

**Parameters NOT in scope:** USE_TRAILING_STOP (still broken), ATR_TRAIL_MULTIPLIER (already set globally to 2.5)

## Design Rules

1. **Relative, not absolute:** CONFIDENCE_THRESHOLD adjustments are `baseline + 4` where baseline = passport's config_overrides value (or global 54 if unset)
2. **Never increase risk:** MAX_OPEN_POSITIONS_PER_PASSPORT regime cap uses `min(baseline, cap)` — never opens more positions than the passport's own limit
3. **Only set deltas:** regime_params only contains values that DIFFER from config_overrides baseline. Empty regimes = baseline is fine.
4. **Guardrails respected:** Reversal passports have non-overridable guardrails (CONF ≥ 80, MAX_POS ≤ 5 in choppy). Don't set redundant values that guardrails will override.
5. **DIRECTION_BIAS for directional strategies only:** Trend-followers + momentum hybrids get LONG_ONLY/SHORT_ONLY. Mean-reversion + pure breakout keep BOTH.

## Category A: Trend-Following (11 passports)

Active regimes: TREND_UP, TREND_DOWN

| Passport | Baseline Conf | TREND_UP regime_params | TREND_DOWN regime_params |
|----------|---------------|------------------------|--------------------------|
| DualMA Crossover | 58 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 62, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| MinimalEdge | 54 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| OBV Trend | 55 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 59, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| PureTrend | 54 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| TrendConfirm | 60 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 64, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| TrendMomentum | 58 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 62, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| Pumpradar Dynamic | 60 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 64, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| Pumpradar HiddenGem | 54 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| Pumpradar Momentum | 60 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 64, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| Pumpradar Sniper | 70 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 74, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| Pumpradar VolumeKing | 54 | `{DIRECTION_BIAS: "LONG_ONLY"}` | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |

**Rationale:** TREND_UP is home turf — only change is enforcing LONG_ONLY (don't short in confirmed uptrend). TREND_DOWN is dangerous: force SHORT_ONLY, raise confidence bar, cut risk to 0.3%, cap at 15 positions to limit correlated-dump exposure.

## Category B: Mean-Reversion (4 passports)

Active regimes: HIGH_VOL_CHOP, LOW_VOL_COMPRESSION

| Passport | Baseline Conf | Baseline MaxPos | HIGH_VOL_CHOP regime_params | LOW_VOL_COMPRESSION regime_params |
|----------|---------------|-----------------|-----------------------------|------------------------------------|
| BBMeanRev | 60 | 25 | `{CONFIDENCE_THRESHOLD: 64, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` | `{}` |
| RSIContrarian | 62 | 25 | `{CONFIDENCE_THRESHOLD: 66, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` | `{}` |
| Pumpradar ReversalV2 | 70 | 3 | `{RISK_PER_TRADE_PCT: 0.3}` | `{}` |
| Pumpradar Reversal | 85 | 5 | `{RISK_PER_TRADE_PCT: 0.3}` | `{}` |

**Rationale:** HIGH_VOL_CHOP = whipsaw risk. Raise confidence bar (+4), reduce risk, cap positions at 10. LOW_VOL_COMPRESSION = clean range-bound signals, baseline works fine.

**ReversalV2/Reversal note:** Guardrails already enforce CONF ≥ 80 and MAX_POS ≤ 5 in choppy regimes — no need to set those in regime_params. Only add RISK reduction (0.3%).

## Category C: Breakout (5 passports)

Active regimes: LOW_VOL_COMPRESSION, TREND_UP, TREND_DOWN

| Passport | Baseline Conf | Baseline MaxPos | LOW_VOL_COMPRESSION | TREND_UP | TREND_DOWN |
|----------|---------------|-----------------|---------------------|----------|------------|
| BollingerBreakout | 55 | 25 | `{}` | `{}` | `{CONFIDENCE_THRESHOLD: 59, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| BollingerBreakoutV2 | 50 | 25 | `{}` | `{}` | `{CONFIDENCE_THRESHOLD: 54, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| BollingerBreakoutV3 | 55 | 25 | `{}` | `{}` | `{CONFIDENCE_THRESHOLD: 59, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| BreakoutVol | 54 | 20 | `{}` | `{}` | `{CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| Donchian Breakout | 58 | 25 | `{}` | `{}` | `{CONFIDENCE_THRESHOLD: 62, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |

**Rationale:** LOW_VOL_COMPRESSION is the ideal breakout setup (squeeze → release) — standard params. TREND_UP breakouts are reliable — standard. TREND_DOWN breakouts are risky (false breakdowns, sudden reversals) — tighten everything.

**No DIRECTION_BIAS for breakouts:** Breakouts can legitimately go either direction regardless of BTC regime.

## Category D: Hybrid (6 passports)

Each hybrid passport gets individual treatment based on its specific strategy thesis.

### BalancedSelective (TREND_UP, HIGH_VOL_CHOP)
Thesis: balanced indicator mix, slightly selective. Treat TREND_UP as trend-follower, HIGH_VOL_CHOP as mean-rev.

| Regime | regime_params |
|--------|---------------|
| TREND_UP | `{DIRECTION_BIAS: "LONG_ONLY"}` |
| HIGH_VOL_CHOP | `{CONFIDENCE_THRESHOLD: 62, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` |

### MACDDivergence (TREND_UP, TREND_DOWN, HIGH_VOL_CHOP)
Thesis: regime-neutral divergence detection (BTC_TREND_WEIGHTS=1.0, COUNTER_TREND_PENALTY=1.0). No direction bias — divergences are inherently counter-trend.

| Regime | regime_params |
|--------|---------------|
| TREND_UP | `{}` |
| TREND_DOWN | `{CONFIDENCE_THRESHOLD: 62, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| HIGH_VOL_CHOP | `{CONFIDENCE_THRESHOLD: 62, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` |

### PressureReader (TREND_UP, HIGH_VOL_CHOP)
Thesis: buying/selling pressure detection. In uptrend, pressure naturally skews long.

| Regime | regime_params |
|--------|---------------|
| TREND_UP | `{DIRECTION_BIAS: "LONG_ONLY"}` |
| HIGH_VOL_CHOP | `{CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` |

### RSIMomentumV2 (TREND_UP, TREND_DOWN, HIGH_VOL_CHOP)
Thesis: RSI momentum + divergence hybrid. Directional in trending, cautious in chop.

| Regime | regime_params |
|--------|---------------|
| TREND_UP | `{DIRECTION_BIAS: "LONG_ONLY"}` |
| TREND_DOWN | `{DIRECTION_BIAS: "SHORT_ONLY", CONFIDENCE_THRESHOLD: 69, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 15}` |
| HIGH_VOL_CHOP | `{CONFIDENCE_THRESHOLD: 69, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` |

### Pumpradar OG Seasonal (TREND_UP, HIGH_VOL_CHOP)
Thesis: original strategy with seasonal patterns. Broad indicator set.

| Regime | regime_params |
|--------|---------------|
| TREND_UP | `{DIRECTION_BIAS: "LONG_ONLY"}` |
| HIGH_VOL_CHOP | `{CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` |

### Pumpradar OG (TREND_UP, HIGH_VOL_CHOP)
Thesis: original all-indicator strategy.

| Regime | regime_params |
|--------|---------------|
| TREND_UP | `{DIRECTION_BIAS: "LONG_ONLY"}` |
| HIGH_VOL_CHOP | `{CONFIDENCE_THRESHOLD: 58, RISK_PER_TRADE_PCT: 0.3, MAX_OPEN_POSITIONS_PER_PASSPORT: 10}` |

## Implementation

### Approach: Python script + manual validation

1. Create `scripts/update_regime_params.py` with exact regime_params per passport (from tables above)
2. Script reads each JSON, sets regime_params, validates schema, writes back
3. Run existing test suite (505+ tests) to verify no breakage
4. Run integration tests (test_regime_gating_integration.py) to verify schema compliance
5. Commit all passport JSONs + script (then delete script)
6. Deploy to VPS

### Validation checklist

- [ ] All regime_params keys are valid config attribute names
- [ ] CONFIDENCE_THRESHOLD values are within [50, 95] range
- [ ] RISK_PER_TRADE_PCT values are within [0.1, 1.0] range
- [ ] MAX_OPEN_POSITIONS_PER_PASSPORT ≤ passport baseline (never increase)
- [ ] DIRECTION_BIAS values are "LONG_ONLY", "SHORT_ONLY", or absent (BOTH)
- [ ] Only active regimes have entries in regime_params
- [ ] Reversal passports' guardrails not made redundant
- [ ] 505+ tests still pass
- [ ] Integration tests validate new regime_params structure

## Risk Assessment

**Low risk:** This change only adds data to existing infrastructure. The 3-layer config resolution was built and tested in Phase 1. No code changes to passport_runner.py needed.

**Rollback:** Revert all regime_params to `{}` — passports return to Phase 1 behavior (hard gate only).

**Monitoring:** After VPS deploy, check Telegram signals for:
1. LONG_ONLY passports not firing SHORT signals
2. HIGH_VOL_CHOP signals have higher confidence than before
3. No "regime_params override" warnings in logs (from guardrails)
