# Systematic Calculation Audit + Research Engine Alignment

**Date:** 2026-04-07  
**Status:** Draft  
**Branch:** `feat/systematic-calc-audit`  
**Predecessor:** Session 945a380a (BTC Uptrend weight fix, commit 10ec9b5)

## Problem Statement

A critical math bug (BTC Uptrend weight 0.5 → max confidence 50 < threshold 54, making ALL signals impossible during bull markets) was fixed in session 945a380a. A full audit of all calculation modules revealed **12 additional bugs**, including a research engine that uses **opposite BTC trend weights** compared to the live system — making all research results unreliable.

Additionally, the research engine has **never been run end-to-end** despite being fully built (Plans 1-3). Four critical mismatches between research and live systems must be resolved before the pipeline can produce trustworthy results.

The goal: fix all calculation bugs, make BTC_TREND_WEIGHTS per-passport overridable, align the research engine with live, and run the pipeline to ensure profitable strategies for every market condition.

## Constraints

- **All research/backtesting runs on local MacBook** — VPS is for live paper trading only.
- **TP cascade (70/20/10) is NOT modified** — don't touch what works.
- **No new strategy families** from the 151 strategies journal — fix existing 23 families first.
- **Trailing stop remains disabled** — known broken, out of scope.
- **All 240 existing tests must stay green** after every phase.
- **FINDINGS.md must be updated** after each phase completes.

## Phase 1: Systematic Calculation Bug Fixes

Fix all 12 identified bugs with regression tests.

### HIGH Severity

**H1 — Research engine uses opposite BTC trend weights**
- File: `bot/research/extended_scorer.py`, line 126
- Bug: Hardcoded `BTC_WEIGHT = {"Uptrend": 1.15, "Downtrend": 0.85, "Sideways": 1.0}`
- Live system uses `config.BTC_TREND_WEIGHTS = {"Uptrend": 0.8, "Downtrend": 1.0, "Sideways": 1.0}`
- Research BOOSTS uptrend (+15%), live PENALIZES it (-20%) — completely opposite philosophies
- **Fix:** Replace hardcoded dict with `config.BTC_TREND_WEIGHTS`
- **Test:** Assert `score_confluence_extended()` uses config values, not hardcoded ones

**H2 — Confidence can exceed 100% in extended scorer**
- File: `bot/research/extended_scorer.py`, line 126
- Bug: `confidence = raw_confidence * btc_weight` — with Uptrend=1.15, max = 115%
- Breaks leverage tier calculations (expects 0-100 range)
- **Fix:** `confidence = min(100.0, max(0.0, raw_confidence * btc_weight))`
- **Test:** Feed raw_confidence=95, btc_weight=1.15 → assert result ≤ 100

**H3 — Stage 4 trade_overlap uses nonexistent fields**
- File: `bot/research/stage4.py`, lines 38-43
- Bug: Uses `ta["entry_bar"]` and `ta["exit_bar"]` — backtester produces `entry_time` and `exit_time`
- Portfolio construction silently returns 0 overlap → no orthogonality filtering
- **Fix:** Parse `entry_time`/`exit_time` as timestamps, compute temporal overlap ratio
- **Test:** Create mock trades with known overlap, verify ratio calculation

**H4 — Regime classifier mismatch: 4 regimes vs 3**
- File: `bot/research/regime.py` uses 4 regimes: `TREND_UP`, `TREND_DOWN`, `HIGH_VOL_CHOP`, `LOW_VOL_COMPRESSION`
- Live system (`bot/data_fetcher.py`): 3 regimes: `Uptrend`, `Downtrend`, `Sideways`
- Research results can't be mapped to live conditions
- **Fix:** Add `map_to_live_regime()` function:
  - `TREND_UP` → `"Uptrend"`
  - `TREND_DOWN` → `"Downtrend"`
  - `HIGH_VOL_CHOP` → `"Sideways"`
  - `LOW_VOL_COMPRESSION` → `"Sideways"`
- **Test:** Assert all 4 research regimes map correctly

### MEDIUM Severity

**M1 — Stage 3 skips INDICATOR_WEIGHTS perturbation**
- File: `bot/research/stage3.py`, lines 58-59
- Bug: `if key == "INDICATOR_WEIGHTS": result[key] = value.copy(); continue`
- Indicator weights are the most important parameter but never tested for robustness
- **Fix:** Perturb each individual weight value ±20%. Weights that are 0.0 stay 0.0 (zero = disabled).
- **Test:** Verify perturbed weights differ from originals; verify 0.0 weights stay 0.0

**M2 — Sortino ratio: optimistic hardcoded value**
- File: `bot/backtester.py`, lines 275-276
- Bug: If no negative daily returns, `sortino = 100.0` — arbitrary, could mislead ranking
- **Fix:** Cap at 999.99 (avoids JSON serialization issues with infinity)
- **Test:** Assert Sortino with all-positive returns returns capped value

**M3 — Composite utility returns 0 for perfect strategies**
- File: `bot/research/stage4.py`, lines 86-87
- Bug: `utility = return_pct * (return_pct / max_dd)` — if `max_dd == 0`, utility = 0 (worst score for best strategy)
- **Fix:** If `max_dd == 0.0`: `utility = return_pct * 100.0` (reward perfection)
- **Test:** Assert utility(return_pct=10, max_dd=0) > utility(return_pct=10, max_dd=5)

**M4 — Regime classifier hardcodes 4H annualization**
- File: `bot/research/regime.py`, line 51
- Bug: `annualization_factor = 252 * 6` (assumes 4H candles, 6 per day)
- We use 1H candles (24 per day, 365 days)
- **Fix:** Accept `candles_per_year` parameter, default to `365 * 24 = 8760` for 1H
- **Test:** Verify with 1H data that annualized volatility is in reasonable range

### LOW Severity

**L1 — RSI div-by-zero masking**
- File: `bot/indicators.py`, line 88
- Bug: `fillna(50)` on div-by-zero replaces extreme conditions with neutral
- **Fix:** `fillna(method='ffill')` first, then `fillna(50)` as last resort
- **Test:** Feed data with zero price change, verify RSI doesn't jump to 50

**L2 — MACD histogram assumes len > 1**
- File: `bot/indicators.py`, line 61
- Bug: No guard for DataFrame with <2 rows
- **Fix:** `if len(df) < 2: return "NEUTRAL", 0`
- **Test:** Feed single-row DataFrame, verify no crash

**L3 — OBV gap_pct unbounded**
- File: `bot/indicators.py`, line 329
- Bug: `1e-10` epsilon in denominator can produce huge `gap_pct` values
- **Fix:** Clamp: `gap_pct = max(-500, min(500, gap_pct))`
- **Test:** Feed near-zero previous OBV, verify clamped output

**L4 — Artificial equity point may skew metrics**
- File: `bot/backtester.py`, line 258
- Bug: Inserts `(start_date, starting_equity)` even when equity_curve has data
- **Fix:** Only insert if equity_curve is empty
- **Test:** Verify _summarize with pre-populated equity_curve doesn't duplicate the first point

## Phase 2: Per-Passport BTC_TREND_WEIGHTS Override

### Goal
Mean-reversion strategies should ignore BTC direction (`Uptrend: 1.0`), while trend-followers keep the penalty (`Uptrend: 0.8`).

### Changes

1. **`bot/passport_runner.py`** — Add `"BTC_TREND_WEIGHTS"` to the `_save_config()` key list (currently ~15 keys, adding 1). This enables snapshot/restore isolation.

2. **Passport JSON schema update** — `config_overrides` now accepts:
```json
{
  "BTC_TREND_WEIGHTS": {"Uptrend": 1.0, "Sideways": 1.0, "Downtrend": 1.0}
}
```

3. **Update mean-reversion passports** (set `Uptrend: 1.0`):
   - `passports/cryptopass-research/bb_mean_rev.json`
   - `passports/cryptopass-research/rsi_contrarian.json`
   - `passports/cryptopass-research/macd_divergence.json`
   - `passports/cryptopass-research/reversal.json`
   - Any passport where the strategy doesn't depend on BTC direction

4. **Trend-following passports** — No change needed (they use the default `Uptrend: 0.8`).

5. **Test:** Run two passports back-to-back (one mean-reversion, one trend), verify BTC_TREND_WEIGHTS are correctly isolated and restored.

### Validation
- No cross-contamination between passport scans
- Default behavior unchanged for passports without BTC_TREND_WEIGHTS override

## Phase 3: Research Engine Alignment

### Goal
Verify the research pipeline produces results comparable to live trading. All code fixes are applied in Phase 1 — Phase 3 is an **integration verification** that the combined fixes work correctly end-to-end.

### Integration Test
After all fixes:
1. Run BBMeanRev through `pipeline.py` (all 4 stages)
2. Separately run `backtester.run_backtest()` with the same config
3. Compare Stage 1 return_pct with manual backtest — should be within ±2%
4. Verify Stage 4 produces nonzero trade overlap values
5. Verify Stage 3 actually perturbs INDICATOR_WEIGHTS

## Phase 4: Run Research Pipeline End-to-End

### Execution (on local MacBook, NOT VPS)

```bash
uv run python run_research.py --all --max-per-family 5 --days 180
```

This generates ~115 candidates (5 per family × 23 families) and runs them through all 4 stages.

### Expected Flow
1. **Stage 1 (Sanity):** Filter candidates with <10 trades or profit_factor < 1.0
2. **Stage 2 (Regime Walk-Forward):** Test survivors across 4 regime windows
3. **Stage 3 (Monte Carlo):** Perturb parameters ±20%, check robustness
4. **Stage 4 (Portfolio Construction):** Select orthogonal portfolio

### Market Condition Coverage Check
After pipeline completes, verify at least one promoted strategy per regime:
- **BTC Uptrend:** Trend-following (HiddenGem, Sniper, VolumeKing — already proven +9-26%)
- **BTC Sideways:** Mean-reversion (BBMeanRev, RSIContrarian — need validation with correct BTC weights)
- **BTC Downtrend:** Short-bias or momentum-down (identify from pipeline results)

### Success Criteria
- At least 3 strategies with >+10% return per regime (180d)
- No strategy with max drawdown >25%
- Pipeline runs end-to-end without errors
- Results stored in `research_experiments.db`
- FINDINGS.md updated with results

### What is explicitly OUT OF SCOPE
- New strategy families from 151 strategies journal (future work)
- TP cascade modification
- Trailing stop fix (needs ATR-based formula — separate project)
- Multi-timeframe confluence
- Funding rate carry / liquidation fade strategies
- VPS deployment of research runs

## Deployment Strategy

- **Phases 1-3:** Fix code, run tests locally, commit to branch, deploy to VPS for live paper trading
- **Phase 4:** Run research pipeline on local MacBook only, analyze results, promote winners to paper trading on VPS

## Files Modified

| Phase | Files |
|-------|-------|
| 1 | `bot/research/extended_scorer.py`, `bot/research/stage4.py`, `bot/research/regime.py`, `bot/research/stage3.py`, `bot/backtester.py`, `bot/indicators.py` |
| 2 | `bot/passport_runner.py`, `passports/cryptopass-research/bb_mean_rev.json`, `rsi_contrarian.json`, `macd_divergence.json`, `reversal.json` |
| 3 | Integration tests only (fixes from Phase 1 cover the code changes) |
| 4 | `docs/FINDINGS.md`, `passports/VERSIONS.md` (results documentation) |
| Tests | `tests/test_calc_audit.py` (new), updates to existing test files as needed |
