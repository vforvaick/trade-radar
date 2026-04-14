# Surgical Fixes — Confidence Cap + Position Limits

**Date:** 2026-04-15
**Status:** Approved
**Phase:** Approach A (of A→C→B incremental plan)

## Problem Statement

Deep dive analysis of 7 days paper trading (Apr 7-14) revealed 4 systemic bugs destroying the portfolio ($482 → $97, -79.9%):

1. **Confidence inversion** — 100% confidence trades have 28% WR (worst!), 50-59% has 46% WR (best!). When all indicators agree, the move is ending, not beginning (late-entry false consensus).
2. **SHORT massacre** — Every losing passport is profitable on LONG, destroyed on SHORT. CTP=0.68 blocks most shorts but the ones that pass (100% raw) are the worst performers.
3. **Position overload** — 316 open positions across 25 passports = ~$0.30 risk per trade (meaningless).
4. **SL placement** — 66% of trades hit SL directly (no TP) = -$18,139. (Deferred to Approach B.)

## Solution

Two config changes that address issues 1-3 simultaneously:

### Fix 1: Confidence Cap (`CONFIDENCE_CAP = 80`)

New config parameter applied to **raw confidence** (before BTC weight and CTP multipliers):

```python
# In scorer.py, after calculating raw_confidence:
confidence_cap = getattr(config, 'CONFIDENCE_CAP', 100)
raw_confidence = min(raw_confidence, confidence_cap)
```

**Combined effect with existing multipliers:**

| Regime | Direction | Calculation | Final | Result |
|--------|-----------|-------------|-------|--------|
| TREND_UP | LONG | 80 × 0.8 | 64 | ✅ Passes, 5x leverage |
| TREND_UP | SHORT | 80 × 0.8 × 0.68 | 43.5 | ❌ Blocked |
| TREND_DOWN | SHORT | 80 × 1.0 | 80 | ✅ With-trend, fine |
| TREND_DOWN | LONG | 80 × 1.0 × 0.68 | 54.4 | ✅ Barely passes, 4x |
| HIGH_VOL_CHOP | Any | 80 × 0.9 | 72 | ✅ 7x leverage |
| LOW_VOL_COMP | Any | 80 × 1.0 | 80 | ✅ 7x leverage |

**Why it works:** The cap prevents late-entry false consensus (100% raw → 80%) AND makes existing CTP effective at blocking counter-trend trades during trending markets. No new logic needed.

**Per-passport overridable** via `config_overrides.CONFIDENCE_CAP`.

### Fix 2: Position Limits (`MAX_OPEN_POSITIONS_PER_PASSPORT = 5`)

Reduced from 50 to 5. With 9 active passports: max 45 positions total (vs 316 today).

Each position gets meaningful risk allocation (~$1-2 per trade vs $0.30).

## Files Changed

| File | Change |
|---|---|
| `bot/config.py` | Add `CONFIDENCE_CAP = 80`, change `MAX_OPEN_POSITIONS_PER_PASSPORT` 50→5 |
| `bot/scorer.py` | Apply cap: `raw_confidence = min(raw_confidence, getattr(config, 'CONFIDENCE_CAP', 100))` |
| `bot/research/extended_scorer.py` | Same cap logic for research pipeline consistency |
| `tests/test_confidence_cap.py` | Test cap behavior, CTP interaction, per-passport override |
| `tests/test_position_limits.py` | Verify position limit enforcement at 5 |

## What This Fixes

- ✅ **Confidence inversion** — 100% raw → capped at 80%, no more 7x leverage on late entries
- ✅ **SHORT massacre** — cap + CTP naturally blocks counter-trend during trending
- ✅ **Position overload** — max 45 positions across portfolio
- ⬜ **SL placement** — deferred to Approach B (ATR-based SL redesign)

## Future Phases

- **Approach C (next):** Regime-based passport activation — dynamically enable/disable passports by BTC regime
- **Approach B (later):** Full scoring overhaul — diminishing returns function, indicator quality weighting
