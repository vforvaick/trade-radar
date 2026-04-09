# Counter-Trend Penalty Design Spec

**Date:** 2026-04-09
**Status:** Approved
**Session:** 10

## Problem

`BTC_TREND_WEIGHTS` in `scorer.py` applies the same confidence multiplier regardless of signal direction. During TREND_UP (0.8×), SHORT signals pass just as easily as LONG signals. Live paper trading confirmed: 77-92% of trades from HiddenGem/Sniper/BBMeanRev were SHORT during BTC uptrend → -59% portfolio loss.

Same issue exists in `research/extended_scorer.py`.

The existing `DIRECTION_BIAS` in passport_runner is a hard binary filter, not a confidence penalty.

## Solution: COUNTER_TREND_PENALTY

A new per-regime config multiplier applied **after** `BTC_TREND_WEIGHTS` only when signal direction opposes BTC trend.

### Effective multiplier chain:

```
final_confidence = raw_confidence × BTC_TREND_WEIGHT × COUNTER_TREND_PENALTY (if counter-trend)
```

### Config (bot/config.py)

```python
COUNTER_TREND_PENALTY = {
    "TREND_UP": 0.5,            # SHORT signals × 0.5 extra
    "TREND_DOWN": 0.5,          # LONG signals × 0.5 extra
    "HIGH_VOL_CHOP": 1.0,       # no directional penalty
    "LOW_VOL_COMPRESSION": 1.0, # no directional penalty
}
```

### Scorer change (bot/scorer.py, after line 127)

```python
# Apply counter-trend penalty
ctp = getattr(config, 'COUNTER_TREND_PENALTY', {})
penalty = ctp.get(btc_trend, 1.0)
is_counter = (
    (btc_trend == "TREND_UP" and direction == "SHORT") or
    (btc_trend == "TREND_DOWN" and direction == "LONG")
)
if is_counter:
    confidence *= penalty
```

Same change in `bot/research/extended_scorer.py`.

### Passport overrides

Mean-reversion passports override to 1.0 (no penalty):
- bb_mean_rev.json
- rsi_contrarian.json
- macd_divergence.json
- reversal_v2.json
- reversal.json

```json
"COUNTER_TREND_PENALTY": {
    "TREND_UP": 1.0, "TREND_DOWN": 1.0,
    "HIGH_VOL_CHOP": 1.0, "LOW_VOL_COMPRESSION": 1.0
}
```

Trend-following passports inherit default 0.5 penalty — no config change needed.

### Config isolation (bot/passport_runner.py)

Add `'COUNTER_TREND_PENALTY'` to the save/restore key list in `_save_config()`.

### Return value

Add to scorer return dict:
- `counter_trend_penalty`: float — the penalty applied (1.0 if none)

### Backward compatibility

- Passports without `COUNTER_TREND_PENALTY` in config_overrides get the default 0.5
- `getattr(config, 'COUNTER_TREND_PENALTY', {})` — safe if config doesn't have it
- Old 3-regime BTC_TREND_WEIGHTS still handled by existing warning logic

## Impact Math

| Scenario | BTC_TREND_WEIGHT | CTP | Effective | Raw conf needed | Result |
|----------|-----------------|-----|-----------|----------------|--------|
| LONG during TREND_UP (trend-follow) | 0.8 | 1.0 | 0.8 | 67.5 | ✅ Selective |
| SHORT during TREND_UP (trend-follow) | 0.8 | 0.5 | 0.4 | 135 | ❌ Impossible |
| SHORT during TREND_UP (mean-rev, override 1.0) | 0.8 | 1.0 | 0.8 | 67.5 | ✅ Trades freely |
| LONG during TREND_DOWN | 1.0 | 0.5 | 0.5 | 108 | ❌ Blocked |
| Any direction during CHOP | 0.9 | 1.0 | 0.9 | 60 | ✅ Normal |
| Mean-rev with BTW_UP=1.0 + CTP=1.0 | 1.0 | 1.0 | 1.0 | 54 | ✅ Full access |

## Files Changed

| File | Change |
|------|--------|
| `bot/config.py` | Add `COUNTER_TREND_PENALTY` dict |
| `bot/scorer.py` | 8 lines after line 127 |
| `bot/research/extended_scorer.py` | Same 8 lines after line 126 |
| `bot/passport_runner.py` | Add key to save/restore list |
| 5 passport JSONs | Add `COUNTER_TREND_PENALTY` override |
| `tests/test_scorer.py` | 3-4 new test cases |
| `tests/test_extended_scorer.py` | 1 parity test |
| `docs/FINDINGS.md` | Document the fix |
| `passports/VERSIONS.md` | Version bumps |

## Tests

1. `test_counter_trend_penalty_short_during_uptrend` — SHORT + TREND_UP → confidence × 0.5
2. `test_no_penalty_with_trend` — LONG + TREND_UP → confidence unchanged
3. `test_no_penalty_in_chop` — both dirs in HIGH_VOL_CHOP → confidence unchanged
4. `test_mean_rev_override_no_penalty` — CTP=1.0 override → counter-trend not penalized
5. `test_extended_scorer_counter_trend_parity` — extended_scorer applies same logic
