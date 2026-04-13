# Cryptopass — Findings, Failures & Learnings

> Living document. Updated after every iteration cycle.
> Purpose: avoid repeating mistakes, build on proven insights, explore new lineages with context.
> Last updated: 2026-04-12 (Session 11e — §21 Per-passport regime optimization)

---

## §21 — Session 11e: Per-Passport Regime Optimization (2026-04-12)

### What Changed
- **Regime hard gate enforced:** Each passport now only scans in its declared `active_regimes`. Previously all 25 scanned in all regimes — pure waste for trend-followers during HIGH_VOL_CHOP.
- **Regime params overlay:** `regime_params` dict in passport JSON allows per-regime config tuning (confidence threshold, position limits, risk, direction bias, trailing stop). Applied as layer 3 after config_overrides.
- **Config resolution order:** global defaults → config_overrides → regime_params[current_regime]
- **ATR_TRAIL_MULTIPLIER:** Default widened from 2.0 → 2.5 (still disabled globally)
- **All 26 passports updated** with active_regimes and regime_params (Phase 1: empty)

### Impact
- In HIGH_VOL_CHOP regime: only ~9 of 25 passports active (was 25)
- In LOW_VOL_COMPRESSION: only ~8 of 25 active
- Estimated loss prevention: ~60% of wrong-regime losses avoided
- Pareto ratio: ~1:100 (lose ~$50 upside, save ~$4,000-6,000 downside)

### Regime Distribution
- 11 trend-following → TREND_UP, TREND_DOWN
- 3 mean-reversion → HIGH_VOL_CHOP, LOW_VOL_COMPRESSION
- 5 breakout → LOW_VOL_COMPRESSION + TREND_UP + TREND_DOWN
- 6 hybrid → varies per passport

### New Tests
- `test_regime_gating.py`: Hard gate (5) + regime_params overlay (6) = 11 tests
- `test_regime_gating_integration.py`: Schema validation = 26 passports × 4 tests = 104 tests
- `test_passport_runner_regime.py`: regime_params loading = 2 tests

### Anti-Pattern Reinforced
The selectivity principle extends to regime selection: don't let a trend-follower trade in choppy markets. Hard gate is the cheapest, most impactful filter — simpler than tuning indicator weights.

---

## §16 — Session 9: ATR Fix, direction_bias, Quality Pairs Research (2026-04-08)

### ATR Bug (Critical, Fixed)

**Root cause:** `add_atr(df, period=14)` in `bot/indicators.py` was never called in the live pipeline.  
**Effect:** `sig.atr_at_entry` was `None` for every position ever created. Both `USE_TRAILING_STOP=True` and `USE_ATR_EXITS=True` were silently broken.  
**Fix:** One line — `indicators.add_atr(df, period=14)` added after the length guard in `score_confluence()` (commit `1b2ad09`).  
**Note:** The trailing stop logic in `position_manager.py` was correctly written — it already handled ATR via `sig.atr_at_entry`. ATR comparison script added: `scripts/backtest_atr_comparison.py` — run before enabling `USE_TRAILING_STOP=True` on any passport.

### direction_bias Feature (New)

**What it does:** New `DIRECTION_BIAS` config key (`None` / `"SHORT_ONLY"` / `"LONG_ONLY"`). When set, blocks signals of the opposite direction before position open.  
**Where applied:** Both `bot/backtester.py` (candle loop) and `bot/passport_runner.py` (signal loop). Same logic in both — `getattr(config, 'DIRECTION_BIAS', None)`.  
**Usage:** Add `"DIRECTION_BIAS": "SHORT_ONLY"` to any passport's `config_overrides`. Enables dedicated downtrend passports without changing scorer or signal logic.  
**Config isolation:** `PassportRunner._save_config()` snapshots all `config_overrides` keys, including `DIRECTION_BIAS` — restored after each passport scan (no cross-passport leakage).

### Research Engine Improvements

1. **`pressure_flow_short` family added** to `bot/research/families.py` — pressure=2.5 + candle=1.5 + ema=1.0, SHORT_ONLY, generates 4 candidates. Targets TREND_DOWN/HIGH_VOL_CHOP regimes.
2. **`--quality-pairs` flag** added to `run_research.py` — uses 10 hardcoded tier-1 pairs (BTC/ETH/SOL/BNB/XRP/ADA/DOGE/AVAX/LINK/DOT) instead of meme-coin top-volume Binance scan. Produces reproducible, stable backtest results.
3. **Phase 4 re-run launched** (2026-04-08 17:33 local) — 107 candidates, 180d, quality pairs, all families including `pressure_flow_short`. Log: `logs/research_phase4_quality_20260408_173313.log`.

### Session 9 Commits

| SHA | Change |
|---|---|
| `1b2ad09` | fix: add_atr() in score_confluence — atr_at_entry always None |
| `46a8640` | feat: DIRECTION_BIAS config — SHORT_ONLY / LONG_ONLY passports |
| `29939c7` | feat: DIRECTION_BIAS filter in passport_runner live scan |
| `fdd4bd7` | scripts: backtest_atr_comparison.py for ATR validation |
| `3a758e0` | feat: pressure_flow_short strategy family |
| `56af2c1` | feat: --quality-pairs flag in run_research.py |
| `3d4673b` | test: fix passport_runner tests (real run_scan_cycle coverage) |

### Tests: 296/296 passing

---



### What Changed
1. **System renamed to Cryptopass** — "Pumpradar" is the external alert bot; "Cryptopass" is our system
2. **Critical PnL Bug Fixed** — leverage was never applied to PnL calculations:
   - Old: `profit = risk_amount × (target_dist / sl_dist) × close_pct`
   - New: `profit = risk_amount × (target_dist / sl_dist) × close_pct × leverage`
   - Impact: All historical returns were understated by 4-7x
3. **Trading fees added** — 0.04% per side (0.08% round-trip), deducted proportionally per close tier
4. **Passport directory restructured:**
   - `pumpradar-passports/configs/` → `passports/pumpradar/` (7 OG derivatives)
   - New: `passports/cryptopass-research/` (15 custom strategies)
5. **Telegram threading fixed** — signals now routed through `send_signal()` → group, TP/SL replies correctly threaded
6. **Prometheus metrics exporter** — `bot/metrics_exporter.py` on port 9103, Grafana dashboard at `ops/grafana-cryptopass-dashboard.json`
7. **$500 fresh start** — All 22 passports re-enabled, clean equity reset

### PnL Formula Reference (corrected)
```
Per-level profit = risk_amount × (target_dist / sl_dist) × close_pct × leverage - fee
Fee per close    = notional × close_pct × 0.0008  (0.04% entry + 0.04% exit)
SL remaining     = remaining_fraction × (1.0 / 0.30 / 0.10 depending on TPs hit)
```

### Env Vars (post-rename)
```
CRYPTOPASS_TG_TOKEN       → Telegram bot token
CRYPTOPASS_TG_CHAT        → DM chat ID (fallback/logs)
CRYPTOPASS_TG_GROUP_ID    → Trade group supergroup ID
CRYPTOPASS_TG_TRADE_TOPIC_ID → Topic ID for trade signals
CRYPTOPASS_TG_LOG_TOPIC_ID   → Topic ID for system logs (General)
CRYPTOPASS_STATE_DB       → SQLite path (default: state.db)
CRYPTOPASS_BINANCE_VERIFY_TLS → TLS verification (default: true)
```

---

## Table of Contents

1. [Scoring Engine Mechanics](#1-scoring-engine-mechanics)
2. [The Selectivity Principle](#2-the-selectivity-principle--core-discovery)
3. [Passport Performance History](#3-passport-performance-history)
4. [Bugs Found & Fixed](#4-bugs-found--fixed)
5. [What Destroys Performance](#5-what-destroys-performance-anti-patterns)
6. [What Works](#6-what-works-proven-patterns)
7. [Backtesting Methodology Learnings](#7-backtesting-methodology-learnings)
8. [Architecture Decisions](#8-architecture-decisions)
9. [New Passport Candidates (90d Results)](#9-new-passport-candidates-90d-results)
10. [Open Code Issues](#10-open-code-issues-not-yet-fixed)
11. [Deployment & Infrastructure Notes](#11-deployment--infrastructure-notes)
12. [What's Next](#12-whats-next)

---

## 1. Scoring Engine Mechanics

> Source: `bot/scorer.py` L68–131. Critical for understanding ALL passport behavior.

### How confidence is computed

```
confidence = (dominant_score / total_weight) × 100 × btc_weight
```

### Key behaviors

| Behavior | Implication |
|---|---|
| **Zero-weighted indicators are completely absent** | They don't consume `total_weight`. Setting weight=0 removes the indicator entirely. |
| **NEUTRAL votes inflate `total_weight` but NOT scores** | Every neutral indicator DILUTES confidence — even with no opposing votes. |
| **Volume spike is binary + directional-confirmation-only** | Below threshold: adds 0 to score. Above: adds full weight to dominant direction only. Creates a cliff edge near threshold. |
| **BTC Uptrend multiplies confidence × 0.5** | Cuts all confidence in half during uptrends. Strategies relying on high confidence may filter out in bull markets. |
| **Minimum achievable confidence with 3 selective indicators** | With ema=1, bb=1, vol=2 (HiddenGem): minimum = 75%. CONFIDENCE_THRESHOLD of 54–70 is irrelevant. |

### REVERSAL_MODE (scorer.py L76–82)

Forces `ema_trend=0` and `macd_signal=0` regardless of passport weights. This is hardcoded — passports cannot override it.

---

## 2. The Selectivity Principle — Core Discovery

> Discovered during 180d backtest validation (Session 1–2, April 2026)

**"Adding indicators dilutes quality. Selectivity IS the edge."**

### Proof

| Passport | Active Indicators | 180d Return | Trades |
|---|---|---|---|
| HiddenGem v0.1 | 3 (EMA, BB, Vol) | **+25.9%** | ~450 |
| HiddenGem v0.2 | 4 (+ pressure=0.5) | **-26.8%** | ~771 |
| Sniper v0.1 | 3 (BB, Vol, candle) | **+26.0%** | — |
| Sniper v0.2 | 4 (+ macd=1.0) | **-14.7%** | — |
| VolumeKing v0.1 | 3 (Vol, candle, others) | **+9.1%** | — |
| VolumeKing v0.2 | 5 (+ macd=0.5, pressure=0.5) | **-20.5%** | — |

### Why it happens

More indicators → more candles return NEUTRAL for at least one indicator → total_weight inflates → confidence drops → the strategy fires on more, lower-quality setups → WR falls → net negative.

### Rule

> **Never add an indicator to a profitable passport without a documented hypothesis for why it specifically filters fakeouts in that strategy's entry logic.**

---

## 3. Passport Performance History

### Original 7 Passports — 180d Backtest (Jan–Apr 2026, 10 pairs)

| Passport | v0.1 Return | v0.2 Return | v0.3 Return | Status |
|---|---|---|---|---|
| 🏆 OG | -13.1% | -28.8% 🔴 | (=v0.1) -13.1% | Active v0.3 |
| 💎 HiddenGem | **+25.9%** 🟢 | -26.8% 🔴🔴 | (=v0.1) +25.9% | Active v0.3 |
| 🎯 Sniper | **+26.0%** 🟢 | -14.7% 🔴🔴 | (=v0.1) +26.0% | Active v0.3 |
| 📢 VolumeKing | **+9.1%** 🟢 | -20.5% 🔴 | (=v0.1) +9.1% | Active v0.3 |
| 🚀 Momentum | -39.5% | **-20.0%** 🟢 | — | Active v0.2 |
| 🎯 Dynamic | -16.3% | -20.0% | — | Active v0.2 |
| 🔄 Reversal | overtrades | quarantined | — | DISABLED |

> **Note:** OG was +5.2% in live trading (3 days, Apr 1–3 2026) and +11.3% in 30d backtest. The 180d value includes a bear/choppy regime not present in those windows. The "OG was profitable" memory is from live, not 180d.

### v0.1 Baseline Commit

```bash
git show 950e0ec:pumpradar-passports/configs/og_original.json
```

### Rollback Command

```bash
git checkout 950e0ec -- pumpradar-passports/configs/<file>.json
```

---

## 4. Bugs Found & Fixed

### Bug 1 — `USE_TRAILING_STOP` destroys performance
- **File:** `bot/position_manager.py` L181–193
- **Root cause:** `trail_dist = abs(entry - original_SL)` — uses a fixed distance from the entry-time SL. Crypto 1H candles retrace 3–5% intrabar → trail ratchets up on spike, stops out on normal retrace.
- **Impact:** -81.3% with trailing stop vs -17.9% without (63pp difference on 180d backtest)
- **Fix applied:** `USE_TRAILING_STOP: false` in all passports. Formula NOT fixed yet — see Open Issues.
- **Lesson:** Never enable `USE_TRAILING_STOP` until the formula is fixed to use ATR-based distance.

### Bug 2 — `backtester.run_backtest()` multi-symbol aggregation
- **File:** `bot/backtester.py` (fixed in commit `f32ab7b`)
- **Root cause:** Combined raw trades from all symbols into one list. Each symbol started equity at `INITIAL_EQUITY` independently. `final_eq` used the last active symbol's equity → `return_pct` reflected only one symbol. `max_dd` was always 0.0% because equity resets per symbol hid drawdowns.
- **Fix:** Compute `_summarize()` per symbol, then average `return_pct` and `max_dd` across active symbols (equal-weight portfolio interpretation).
- **Lesson:** Always verify aggregation logic in multi-symbol backtests. 0.0% MaxDD across all strategies is a red flag.

### Bug 3 — `StateDB.list_passports()` returns raw JSON strings
- **File:** `bot/deploy/state_db.py` L86–99 (fixed in commit `91e1e37`)
- **Root cause:** `list_passports()` returned raw strings from SQLite `config` and `metrics` columns. `get_passport()` properly deserialized. Inconsistent API.
- **Fix:** Added `json.loads()` for both fields in `list_passports()`.

### Bug 4 — `PositionManager.signal_to_intent()` KeyError on missing `direction`
- **File:** `bot/execution/position_manager.py` L33–36 (fixed in commit `91e1e37`)
- **Root cause:** Accessed `signal["direction"]` without guard. If a signal dict was missing the field (e.g., malformed upstream), would raise `KeyError`.
- **Fix:** Guard returns `None` instead.

### Bug 5 — `Reversal` strategy: RSI logic is momentum not reversal
- **File:** `bot/indicators.py` L93–106, `bot/config.py` L17–18
- **Root cause:** `RSI_LONG_THRESHOLD = 50` — RSI>50 = LONG is a momentum rule. True mean-reversion should be RSI<30 = oversold LONG. Not overridable per-passport (hardcoded in `config.py`).
- **Additional issue:** In reversal logic, RSI and BB CANCEL each other (oversold = RSI says SHORT, BB says LONG). With EMA/MACD disabled via REVERSAL_MODE, there's no trend anchor → overtrades massively in sideways market.
- **Impact:** 337 signals in 3 days live before quarantine.
- **Fix needed:** Make RSI thresholds per-passport overridable, OR rewrite reversal logic as a separate indicator. NOT fixed yet.

### Bug 7 — BTC Uptrend multiplier 0.5 makes ALL signals mathematically impossible
- **File:** `bot/config.py` L101 (fixed in commit `10ec9b5`)
- **Root cause:** `BTC_TREND_WEIGHTS["Uptrend"] = 0.5`. Max raw confidence = 100%. After ×0.5 = 50%. `CONFIDENCE_THRESHOLD = 54`. Since 50 < 54, `go = False` for every single pair — **forever** during BTC Uptrend.
- **Impact:** 5+ hours of live paper trading with 0 signals on 2026-04-07. All 21 passports silenced.
- **Fix:** Changed `Uptrend: 0.5 → 0.8`. Now needs raw confidence ≥67.5% to fire — still selective in bull markets, but not impossible.
- **Lesson:** Whenever you apply a multiplier to a threshold system, verify that `max_possible_value × multiplier ≥ threshold`. With confidence max=100 and threshold=54: any multiplier below 0.54 silences everything.
- **Detected by:** Observing 0 signals across 21 passports + 310 pairs for 5.5 hours.
- **Long-term fix needed:** Make `BTC_TREND_WEIGHTS` per-passport overridable (mean-reversion passports like BBMeanRev/RSIContrarian should use `Uptrend: 1.0`).

### Bug 6 — Dynamic v0.2 = Momentum v0.2 identical metrics
- **Files:** `pumpradar-passports/configs/dynamic_exit.json`, `momentum.json`
- **Root cause:** Backtester may not differentiate `USE_ATR_EXITS=true` in the test window, OR ATR exit is not active for the specific trade duration. Both show 1095 trades, 37.6% WR, -20.0%.
- **Status:** Not investigated. Needs a test where ATR exits are the differentiating factor.

### Bugs 8–19 — Systematic Calculation Audit (Session 8, 2026-04-07, branch `feat/systematic-calc-audit`)

Full audit of all calculation modules — 12 bugs found and fixed, 49 new tests added (241→289).

#### HIGH Severity

**Bug 8 — `extended_scorer.py` hardcoded BTC weights opposite to live system**
- **File:** `bot/research/extended_scorer.py` (H1)
- **Root cause:** `BTC_WEIGHT = {"Uptrend": 1.15, "Downtrend": 0.85, "Sideways": 1.0}` — hardcoded, completely different from live `config.BTC_TREND_WEIGHTS`. Research scoring boosted uptrend candidates by 15% but live penalizes them by 20%. Research backtests were inflated and not comparable to live.
- **Fix:** Replaced with `config.BTC_TREND_WEIGHTS` + `from bot import config`.

**Bug 9 — Research confidence could exceed 100%**
- **File:** `bot/research/extended_scorer.py` (H2)
- **Root cause:** `100 × 1.15 = 115%` — unclamped. Sharpe ratio calculations based on inflated confidence.
- **Fix:** `confidence = min(100.0, max(0.0, ...))` clamped to [0, 100].

**Bug 10 — `stage4.calc_trade_overlap()` used non-existent fields**
- **File:** `bot/research/stage4.py` (H3)
- **Root cause:** Used `entry_bar`/`exit_bar` but backtester produces `entry_time`/`exit_time` strings. Function always returned 0.0 overlap (KeyError silently swallowed or field not present). Portfolio orthogonality filter was broken.
- **Fix:** Parse `pd.Timestamp(trade["entry_time"])` / `exit_time`, check interval overlap `ta_entry <= tb_exit and ta_exit >= tb_entry`.

**Bug 11 — Research regime names don't match live system**
- **File:** `bot/research/regime.py` (H4)
- **Root cause:** Research uses 4 enum values (`TREND_UP`, `TREND_DOWN`, `HIGH_VOL_CHOP`, `LOW_VOL_COMPRESSION`) but live scanner uses 3 strings (`Uptrend`, `Downtrend`, `Sideways`). Walk-forward regime filtering was comparing incompatible types.
- **Fix:** Added `map_to_live_regime(RegimeType)` and `map_regime_value_to_live(str)` mapping functions. `HIGH_VOL_CHOP` and `LOW_VOL_COMPRESSION` both map to `"Sideways"`.

#### MEDIUM Severity

**Bug 12 — Stage 3 Monte Carlo skipped INDICATOR_WEIGHTS**
- **File:** `bot/research/stage3.py` (M1)
- **Root cause:** `perturb_config()` iterated over `INDICATOR_WEIGHTS` keys but immediately `continue`d — no perturbation applied. Monte Carlo was testing zero parameter variance for the most important config. Robustness scores were meaningless.
- **Fix:** Perturb each weight ±20% (`w * random.uniform(0.8, 1.2)`). Zero weights preserved as 0.0 (disabled = off switch).

**Bug 13 — Sortino sentinel 100.0 identical to actual high Sortino**
- **File:** `bot/backtester.py` (M2)
- **Root cause:** `sortino = 100.0` when no negative returns — but a genuinely excellent strategy can also produce Sortino ~100. The sentinel was indistinguishable from real data.
- **Fix:** `sortino = 999.99` — clearly a sentinel, outside plausible real values.

**Bug 14 — `composite_utility` returned 0 for best strategies (max_dd=0)**
- **File:** `bot/research/stage4.py` (M3)
- **Root cause:** `dd_factor = 1 / max_dd` → `1/0 = ZeroDivisionError` caught with `return 0` fallback. A strategy with no drawdown got the worst possible composite utility score, causing it to be ranked last in portfolio selection.
- **Fix:** `if dd_factor <= 0: return (sharpe + calmar) * 10.0 + 100.0` — returns high utility.

**Bug 15 — Volatility annualization uses 4H formula on 1H data**
- **File:** `bot/research/regime.py` (M4)
- **Root cause:** `_calc_realized_vol()` hardcoded `candles_per_year = 252 * 6 = 1512` (4H * 252 trading days). 1H data has 8760 candles/year. Regime volatility was understated by √(8760/1512) = 2.4×. HIGH_VOL regime was nearly never triggered.
- **Fix:** `candles_per_year: int = 365 * 24` parameter, default 8760 for 1H.

#### LOW Severity

**Bug 16 — RSI fillna(50) masks extreme conditions**
- **File:** `bot/indicators.py` (L1)
- **Root cause:** `rsi.fillna(50)` fills ALL NaN — including mid-series gaps from missing candles, which should inherit previous value. A sudden NaN in a 20-bar RSI mid-series would snap to 50 (neutral) instead of carrying the previous extreme value.
- **Fix:** `rsi.ffill().fillna(50)` — forward-fill first, only 50-fill the leading NaN (startup).

**Bug 17 — MACD crashes with insufficient data**
- **File:** `bot/indicators.py` (L2)
- **Root cause:** MACD needs `slow + signal` bars minimum (e.g., 26+9=35). With short history or ultra-fresh symbols, `calc_macd()` would raise IndexError.
- **Fix:** `if len(df) < slow + signal: return "NEUTRAL", 0` early guard.

**Bug 18 — OBV gap_pct effectively uncapped (prior L3)**
- **File:** `bot/indicators.py` (L3 → resolved)
- **Note:** Originally capped at 500.0, but since `strength = min(gap_pct, 1.0)` immediately follows, the 500.0 cap was redundant dead code. Removed the intermediate cap for clarity. The epsilon denominator (1e-10) prevents division by zero; the `min(strength, 1.0)` is the effective cap.

**Bug 19 — Backtester equity starting point duplicated if already present**
- **File:** `bot/backtester.py` (L4)
- **Root cause:** Always inserted artificial equity starting point `(start_time, initial_equity)`. If a trade exits at the same timestamp as `start_time`, the duplicate skewed Sharpe calculation.
- **Fix:** `if start_time not in eq_series.index: eq_series[start_time] = initial_equity`

---

### Phase 2 — Per-Passport BTC_TREND_WEIGHTS Override (Session 8)

**Problem:** All passports shared `BTC_TREND_WEIGHTS = {"Uptrend": 0.8, ...}` (global). Mean-reversion strategies (BBMeanRev, RSIContrarian, Reversal) don't depend on BTC direction — the 0.8× uptrend penalty suppressed them unnecessarily during bull markets.

**Fix applied:**
1. Added `'BTC_TREND_WEIGHTS'` to `passport_runner._save_config()` key list — prevents cross-contamination between passport scan cycles.
2. Added `"BTC_TREND_WEIGHTS": {"Uptrend": 1.0, "Sideways": 1.0, "Downtrend": 1.0}` to `config_overrides` of 5 mean-reversion passports:
   - `bb_mean_rev.json` → v0.2
   - `rsi_contrarian.json` → v0.2
   - `reversal_v2.json` → v0.3
   - `reversal.json` → v0.3 (still `enabled: false`)
   - `macd_divergence.json` → v0.2

**Lesson:** BTC trend filter is only appropriate for directional strategies. Mean-reversion strategies trade price reversion regardless of BTC trend direction.

---

## 5. What Destroys Performance (Anti-Patterns)

### ❌ Trailing Stop (current formula)
- Destroys 63+ percentage points of return
- Formula `trail_dist = abs(entry - SL)` is wrong for crypto
- **Never enable** `USE_TRAILING_STOP: true` until fixed

### ❌ Adding indicators to working strategies
- HiddenGem: +25.9% → -26.8% after adding 1 indicator
- Sniper: +26.0% → -14.7% after adding 1 indicator
- Mechanism: NEUTRAL vote inflation → more trades at lower quality

### ❌ Using REVERSAL_MODE without RSI threshold fix
- RSI>50 = momentum logic, not reversal
- RSI and BB cancel in true reversal setups
- 337 signals in 3 live days = capital destruction

### ❌ High-volume altcoins as test pairs (0G, 1000BONK, etc.)
- The 90d test using Binance top-volume pairs returns 0GUSDT, 1000BONKUSDT, 1000PEPEUSDT, etc.
- These are meme/low-quality pairs with extreme choppiness
- Consider testing on BTC, ETH, SOL, BNB, AAVE, ADA for more reliable signals

### ❌ 30d backtests for strategy validation
- 30d captured a bullish window (+11.3% OG, +49.1% grid search)
- 180d revealed the full picture including bear regime (-13.1%)
- Minimum meaningful window: 90–180d with regime diversity

### ❌ Equal-weight scoring across too many indicators
- OG v0.1: all 8 indicators at weight=1.0 → every single candle has multiple NEUTRAL votes → confidence floor is low → many mediocre-quality entries

---

## 6. What Works (Proven Patterns)

### ✅ Selective 3-indicator passports (still the pattern, but pair-sensitive)
- HiddenGem/Sniper: **+2.5%** on Apr 5 quality-meme mix vs **+25.9%/+26.0%** on Apr 4 run
- ⚠️ The +25.9%/+26.0% figures may have reflected a lucky pair draw — not a stable absolute number
- **The selectivity principle still holds** (v0.2 always worse than v0.1 by -10pp to -23pp)
- VolumeKing (Vol 2.5x+Candle): +9.1% at 180d (Apr 4 run) — pair-dependent
- Pattern: 2–3 active indicators, others set to 0.0

### ✅ Volume spike as the primary filter
- Vol threshold 2.0x+ acts as a regime filter: only fires when real momentum is present
- Vol threshold 2.5x+ (VolumeKing) makes strategy so selective it rarely fires but quality is high
- Proven: 30d backtest showed vol 2.0x = +49.1% vs vol 1.5x = +11.3%

### ✅ TP1-to-breakeven SL move
- After TP1 hit: SL moves to entry (breakeven)
- Eliminates "win then lose" scenarios
- Explains why MaxDD in backtests can appear very low — most positions either hit TP1 (small win) or SL before TP1 (fixed loss)

### ✅ Fixed 3% risk per trade + TP cascade (70/20/10)
- Proven in live data: 49 resolved trades, PF=1.50, +29.6% equity simulation
- Short side outperforms: 65.2% WR shorts vs 50.0% WR longs
- Skip Wed+Fri: +81.1% vs +29.6% baseline (crypto weekly seasonality)

### ✅ BBMeanRev (new candidate — confirmed)
- Quality-pair 90d: +7.7%, PF=1.32, WR=47.3%, 131 trades — **robust across pair types**
- Very consistent: only -0.3pp vs meme pairs (+8.0%)
- Mean-reversion strategies are less sensitive to pair quality (good property)

### ✅ MACDDivergence (new candidate — quality pairs only)
- Quality-pair 90d: +9.1%, PF=1.39, WR=41.5%, 123 trades — **top performer**
- BUT highly pair-sensitive: +9.1% on quality pairs vs -1.3% on meme pairs (+10.4pp swing)
- Only deploy with quality pairs (BTC/ETH/SOL/AAVE/BNB/ADA/DOT/LINK/AVAX/MATIC)

### ✅ Trailing stop now properly ATR-based (fixed Session 4)
- `trail_dist = atr_at_entry * ATR_TRAIL_MULTIPLIER` (was fixed dollar distance)
- Only trails after TP2 (was TP1) — lets winners run longer
- Still disabled by default; test in paper before enabling

### ✅ RSI thresholds and weekday filter now per-passport
- Any passport can set `RSI_LONG_THRESHOLD: 30` in config_overrides
- Any passport can set `SKIP_WEEKDAYS: [2, 4]` to skip Wed/Fri
- `seasonality_og.json` leverages the +81.1% weekday edge

---

## 7. Backtesting Methodology Learnings

### Regime bias is real
| Window | OG Return | Why |
|---|---|---|
| Live 3d (Apr 2026) | +5.2% | Very short, possibly favorable micro-regime |
| 30d backtest | +11.3% | Captured bullish window |
| 30d optimized (vol=2.0) | +49.1% | Overfitted to this specific window |
| 180d (Apr 4 run) | -13.1% | Includes Oct–Jan bear market |
| 180d (Apr 5 run) | -21.7% | Different top-10 pair set pulled |

> **Rule:** Never make deployment decisions on <90d backtests. Always validate across at least 2 regime types.

### Test pairs matter — results vary by ±20pp depending on which pairs are used

**HiddenGem 180d comparison across runs:**
| Run | Return | Pairs |
|---|---|---|
| Apr 4 run | **+25.9%** | Top-10 vol (included "lucky" pairs) |
| Apr 5 run | **+2.5%** | Different top-10 vol (different meme coins) |

⚠️ **23pp swing from one day to the next on 180d backtest = pairs dominate results, not strategy.**

> **Rule:** Never anchor to a single backtest number. Run 3+ times with different pair sets. Use quality pairs (BTC/ETH/SOL/AAVE/BNB) as the canonical benchmark.

### Suspicious identical results = config isolation bug indicator
- HiddenGem v0.1 and Sniper v0.1 show **identical** results in Apr 5 run (424 trades, 33.3% WR, +2.5%)
- Different strategies should not produce identical metrics — possible config not being isolated per-passport
- Investigate `_save_config()` / `_restore_config()` in `run_passport_validation.py` if this recurs

### Multi-symbol backtest aggregation (fixed bug)
- Before fix: `return_pct` = last active symbol's return only. `max_dd` always 0.
- After fix: average of per-symbol returns (equal-weight portfolio)
- PF (profit factor) is the most reliable metric since it's per-trade and doesn't depend on equity curve

### MaxDD vs PF as reliability indicators
- MaxDD is unreliable in the current backtester (see Bug 2)
- **PF > 1.0** with a reasonable trade count (>50) is the most credible signal of edge
- PF < 1.0 with positive return = suspect (likely aggregation artifact)

### 90d window Jan–Apr 2026 assessment
- Bear/choppy market for most altcoins
- Reference v0.3 passports (HiddenGem, Sniper, VolumeKing) showed negative in this period
- Does NOT mean strategies are broken — they were designed for bull/neutral trend-following
- BBMeanRev and RSIContrarian showed positive — mean-reversion strategies suit choppy markets

---

## 8. Architecture Decisions

### Passport JSON schema
```json
{
    "name": "...",
    "emoji": "...",
    "version": "0.x",
    "changelog": [{
        "version": "0.x",
        "date": "YYYY-MM-DD",
        "git_sha": "...",
        "description": "...",
        "backtest_90d": { "return_pct": ..., "win_rate": ..., "trades": ..., "profit_factor": ... }
    }],
    "config_overrides": {
        "INDICATOR_WEIGHTS": {
            "ema_trend": 0.0, "macd_signal": 0.0, "rsi_position": 0.0,
            "rsi_divergence": 0.0, "bb_position": 0.0, "volume_spike": 0.0,
            "pressure": 0.0, "candle_direction": 0.0
        }
    }
}
```

> **All 8 INDICATOR_WEIGHTS keys are required** even when set to 0.0. Missing keys cause config errors.

### Versioning scheme
- `major.minor`: major = thesis change, minor = parameter tune
- Rollback = new version (v0.3) with old params + rollback reason in changelog
- v0.1 baseline always retrievable via git: `git show 950e0ec:pumpradar-passports/configs/<file>.json`

### Config override safety
```python
# How bot/passport_runner.py applies overrides (critical for isolation)
original = {}
for k, v in cfg_override.items():
    original[k] = getattr(config, k, None)
    setattr(config, k, v)
# ... run scan ...
for k, v in original.items():
    setattr(config, k, v)  # MUST restore — prevents cross-passport pollution
```

### Multi-passport architecture
- Each passport gets its own `PositionManager` instance
- State isolated per-passport in SQLite namespaces
- Paper vs Prod: separate SQLite DBs (`paper.db` / `prod.db`) via `NamespaceManager`

### Strategy Research Engine (designed, implemented in Plans 1–3)
- **Plan 1:** 25 scoring families, 21 indicators, regime classifier (4 regimes: Bull/Bear/Sideways/High-Vol), passport generator, Stage 1 (sanity gate) + Stage 2 (walk-forward)
- **Plan 2:** Stage 3 (Monte Carlo perturbation), Stage 4 (orthogonality + portfolio construction), versioning v2 registry with lifecycle states
- **Plan 3:** Execution layer (OrderIntent/Fill/PositionRecord), PortfolioRiskManager, NamespaceManager, RateLimiter/Orchestrator, HealthMonitor, PromotionPolicy (7-gate), StateDB, Telegram formatters
- **Tests:** 206/206 passing

---

## 9. New Passport Candidates — Backtest Results

### 9a. Quality Pairs (90d, Jan–Apr 2026) — BTC/ETH/SOL/BNB/AAVE/ADA/DOT/LINK/AVAX/MATIC

> Ran after fixing meme-coin bias. This is the authoritative result set.
> Log: `logs/new_passports_20260405_105110.log`

| Rank | Passport | Return | PF | WR | Trades | Assessment |
|---|---|---|---|---|---|---|
| 1 | 📊 MACDDivergence v0.1 | **+9.1%** | 1.39 | 41.5% | 123 | ✅ **Top candidate** |
| 2 | 🔄 BBMeanRev v0.1 | **+7.7%** | 1.32 | 47.3% | 131 | ✅ **Deploy to paper** |
| 3 | 🔮 RSIContrarian v0.1 | +0.5% | 1.02 | 36.1% | 97 | 🟡 Marginal, monitor |
| 4 | 🎯 Sniper v0.3 | -3.4% | 0.90 | 33.1% | 160 | 🟡 Choppy window, proven 180d |
| 5 | 💎 HiddenGem v0.3 | -3.4% | 0.90 | 33.1% | 160 | 🟡 Choppy window, proven 180d |
| 6 | 🏆 OG v0.3 | -4.1% | 0.93 | 40.8% | 277 | 🟡 Choppy window |
| 7 | ⚖️ BalancedSelective v0.1 | -4.2% | 0.92 | 40.6% | 254 | 🔴 Skip |
| 8 | 🚄 TrendMomentum v0.1 | -7.0% | 0.85 | 30.3% | 201 | 🔴 Skip |
| 9 | ✅ TrendConfirm v0.1 | -7.8% | 0.84 | 31.5% | 216 | 🔴 Skip |
| 10 | 🎯 MinimalEdge v0.1 | -11.5% | 0.76 | 28.2% | 213 | 🔴 Skip |
| 11 | 📈 PureTrend v0.1 | -11.5% | 0.76 | 28.2% | 213 | 🔴 Skip |
| 12 | 📢 VolumeKing v0.3 | -11.7% | 0.77 | 27.9% | 219 | 🟡 Choppy window, proven 180d |
| 13 | 🌊 PressureReader v0.1 | -13.2% | 0.69 | 29.0% | 200 | 🔴 Skip |
| 14 | 💥 BreakoutVol v0.1 | -19.4% | 0.62 | 29.7% | 259 | 🔴 Skip |

### 9b. Meme Pairs (90d, Jan–Apr 2026) — Previous run for comparison

> Pairs: 0GUSDT, 1000BONKUSDT, 1000PEPEUSDT etc. Results are noisy — use §9a instead.

| Rank | Passport | Return (meme) | Return (quality) | Delta |
|---|---|---|---|---|
| MACDDivergence v0.1 | -1.3% | **+9.1%** | **+10.4pp** |
| BBMeanRev v0.1 | +8.0% | +7.7% | -0.3pp |
| RSIContrarian v0.1 | +4.2% | +0.5% | -3.7pp |

> **Key insight:** MACDDivergence is extremely pair-sensitive (+10pp swing). BBMeanRev is robust across pair types (only -0.3pp). Always use quality pairs for validation.

### 9c. 180d Validation — v0.1 vs v0.2 Comparison (Apr 5, 2026 run, mixed pairs)

> Log: `logs/passport_validation_20260405_110244.log`
> Pairs: top-10 volume (includes meme coins — pair-sensitive, see §7 warning)

| Passport | v0.1 Return | v0.2 Return | Delta | Verdict |
|---|---|---|---|---|
| 🏆 OG | -21.7% | -30.6% | ↓-8.9pp | ⚠️ WORSE |
| 💎 HiddenGem | **+2.5%** | -20.9% | ↓-23.4pp | ⚠️ WORSE |
| 🚀 Momentum | -21.8% | **-11.0%** | ↑+10.7pp | ✅ BETTER |
| 🎯 Dynamic | -27.1% | **-11.1%** | ↑+16.0pp | ✅ BETTER |
| 🔫 Sniper | **+2.5%** | -8.4% | ↓-10.9pp | ⚠️ WORSE |
| 📢 VolumeKing | -13.1% | -17.9% | ↓-4.8pp | ⚠️ WORSE |

**Key findings from this run:**
- **Momentum/Dynamic v0.2 both improved** — confirms that reducing MACD/RSI sensitivity helped
- **Selective strategies (HiddenGem/Sniper) got much worse in v0.2** — adding indicators to selective passports is destructive (selectivity principle confirmed)
- **HiddenGem/Sniper show IDENTICAL results** (424 trades, 33.3% WR, +2.5%) → possible config isolation bug in validation script — investigate if it recurs
- **Dynamic v0.2 ≠ Momentum v0.2** (finally, -11.1% vs -11.0%) — ATR exits are marginally functional; 0.1pp difference suggests they are nearly equivalent for this pair set

### 9d. 180d Run-to-Run Variance (CRITICAL WARNING)

| Passport | Apr 4 run | Apr 5 run | Variance |
|---|---|---|---|
| HiddenGem v0.1 | **+25.9%** | +2.5% | **-23.4pp** |
| Sniper v0.1 | **+26.0%** | +2.5% | **-23.5pp** |
| VolumeKing v0.1 | **+9.1%** | -13.1% | **-22.2pp** |
| OG v0.1 | -13.1% | -21.7% | -8.6pp |

> ⚠️ **23pp variance from one day to the next on 180d backtest = the top-10 pairs drew from a different meme coin pool**
> **DO NOT anchor to any single 180d run number.** Only trust quality-pair results (§9a) or multi-run averages.
> True +25.9% figure for HiddenGem may have been on a lucky pair selection, not a stable absolute value.

---

## 10. Open Code Issues

### FIXED IN SESSION 4 ✅

**✅ Trailing stop formula** (fixed 2026-04-05, commit `62c2c39`)
```python
# OLD (WRONG): trail_dist = abs(sig.entry_price - sig.sl)  # fixed distance
# NEW (CORRECT): trail_dist = (sig.atr_at_entry or fallback) * ATR_TRAIL_MULTIPLIER
# Also: now trails after TP2 (not TP1)
```
- `atr_at_entry` added to Signal dataclass, populated from scorer result
- `ATR_TRAIL_MULTIPLIER = 2.0` in config.py (per-passport overridable)
- Still disabled by default: `USE_TRAILING_STOP: false` in all passports

**✅ RSI thresholds not per-passport** (fixed 2026-04-05, commit `62c2c39`)
- Added `RSI_LONG_THRESHOLD` and `RSI_SHORT_THRESHOLD` to `_save_config()` keys
- Passports can now override via `config_overrides`
- `reversal_v2.json` created with correct 30/70 thresholds (disabled, needs backtest)

**✅ Weekday filter missing** (added 2026-04-05, commit `62c2c39`)
- `SKIP_WEEKDAYS = []` in config.py (per-passport overridable)
- `seasonality_og.json` created with `SKIP_WEEKDAYS: [2, 4]` (skip Wed/Fri)
- Historical edge: +81.1% vs +29.6% baseline

### STILL OPEN

**1. Dynamic EXIT behavior partially verified — still needs deeper test (MEDIUM)**
- `USE_ATR_EXITS: true` on Dynamic passport showed -11.1% vs Momentum v0.2 -11.0% (only 0.1pp diff)
- ATR exits ARE functional (results no longer perfectly identical as seen in earlier runs)
- But 0.1pp diff suggests minimal real-world impact — need a fixture with high-ATR pairs to see meaningful difference

**2. BTC Uptrend confidence × 0.5 multiplier (MEDIUM)**
- Strategies rarely fire in bull markets due to halved confidence
- Consider making `BTC_TREND_WEIGHTS` per-passport overridable

**3. Regime classifier mismatch (MEDIUM) — documented, not yet fixed**
- Research engine (`bot/research/regime.py`): 4 regimes (TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION)
- Backtester (`determine_btc_trend_at()` in `bot/backtester.py`): 3 regimes (Uptrend/Downtrend/Sideways)
- `extended_scorer.py` also uses 3-regime labels (Uptrend/Downtrend/Sideways) via `BTC_WEIGHT` dict
- `classify_regime()` in `regime.py` is **never called** anywhere — it's unused infrastructure; the actual regime detection is `determine_btc_trend_at` with 3 labels
- Must reconcile before integrating regime-aware scoring into the research pipeline; requires changing `determine_btc_trend_at` to emit 4 labels OR mapping 4→3 in `extended_scorer.py`

**4. reversal_v2.json — v0.1 + v0.2 EMA-gate experiment — FAILED both, kept disabled (RESOLVED)**

_v0.1 (RSI 30/70 + BB only, threshold=70):_
- 90d quality-pair backtest (BTCUSDT ETHUSDT SOLUSDT BNBUSDT AAVEUSDT ADAUSDT DOTUSDT LINKUSDT AVAXUSDT MATICUSDT)
- Return: **-11.78%** | Win Rate: **29.6%** | Profit Factor: **0.70** | Trades: **186**
- Diagnosis: pure mean-reversion fires too often in trending markets → low WR, negative PF

_v0.2 (EMA gate: ema_trend=0.5, rsi_position=1.5, bb_position=1.5, threshold=65) — REVERTED:_
- Return: **-16.44%** | Win Rate: **32.6%** | Profit Factor: **0.63** | Trades: **227**
- Result: dramatically worse — lowered threshold (70→65) opened more marginal trades, negating any EMA filtering. EMA weight boosts confidence additively; it is not a hard gate.
- Decision: reverted config to v0.1 weights; remain `enabled: false`
- Next attempt: raise CONFIDENCE_THRESHOLD to 75+, OR implement EMA as a hard pre-filter in signal logic (not a weight)

**5. `reversal.json` has 9 INDICATOR_WEIGHTS keys (LOW)**
- Extra `reversal_mode` key inside INDICATOR_WEIGHTS — pre-existing, harmless
- Clean up when rewriting Reversal

---

## 11. Deployment & Infrastructure Notes

### VPS Setup (updated Session 7 — 2026-04-07)
- **Host:** `fight-tres`
- **Service:** `cryptopass.service` (systemd — was `pumpradar.service`)
- **Metrics service:** `cryptopass-metrics.service` — Prometheus exporter on port 9103
- **Start/stop:** `systemctl restart cryptopass.service`
- **Entry:** `python -m bot.main_multi --interval=1h`
- **Passport dir:** `passports/` (scans `passports/pumpradar/` + `passports/cryptopass-research/`)
- **New passports auto-activate** — just push to VPS and restart service
- **Fresh start:** `python scripts/fresh_start.py --db state.db --confirm` (clears positions + equity history)
- **Deploy sequence:** `git pull && python scripts/fresh_start.py --db state.db --confirm && systemctl restart cryptopass.service`

### Telegram
- HTTP API via bot token in `.env`
- Threading: signal message → TP/SL replies in same thread (group_msg_id stored in notifier)
- Commands: `/status`, `/ping`, `/summary`
- New formatters in `bot/telegram_commands.py`: strategies, compare, health, promotion, digest
- **Group routing (Session 7):** Trade signals → `CRYPTOPASS_TG_GROUP_ID=-1003773269891` topic `CRYPTOPASS_TG_TRADE_TOPIC_ID=6`. System logs → `CRYPTOPASS_TG_LOG_TOPIC_ID=1` (General topic). DM only for `/status` etc. command replies.

### Monitoring (Prometheus + Grafana)
- **Prometheus:** fight-uno `http://localhost:9090` — scrapes `fight-tres:9103` (job: `cryptopass`)
- **Grafana:** fight-uno `http://localhost:3333` (faiq/trader2026) — dashboard: "Cryptopass Trading Dashboard"
- **Dashboard UID:** `cryptopass-main` — URL: `/d/cryptopass-main/cryptopass-trading-dashboard`
- **Metrics exposed (port 9103):** equity, unrealized_pnl, drawdown, trades_total, win_rate, profit_factor, open_positions, heartbeat_age_seconds
- **Heartbeat:** updates every scan cycle (1h). `-1` = no snapshots yet (expected on fresh start)
- **Config:** `ops/grafana-cryptopass-dashboard.json` — import via Grafana UI or API

### State Persistence
- `bot/state_store.py`: SQLite with `positions`, `equity_snapshots`, `trade_log`
- `bot/deploy/state_db.py`: new SQLite with `passport_state`, `trade_log`, `system_events`
- Paper/prod isolation: separate `.db` files via `NamespaceManager`

### Python Environment
- Python 3.14.0 via `.venv`, managed with `uv`
- **Always use:** `uv run python` (not `python` or `python3` — not in PATH)
- Run tests: `uv run pytest tests/ -v --tb=short`

### Binance API
- Production: `fapi.binance.com` (futures)
- Sometimes unreachable locally — test with `curl fapi.binance.com/fapi/v1/ping`
- If blocked locally: run backtests from VPS where API is always accessible

### Branch/PR Status
- Branch `fix/strategy-parameter-tuning` → PR #1 open on GitHub
- URL: https://github.com/vforvaick/trade-radar/pull/1
- **49 commits**, 206/206 tests passing

---

## 12. What's Next

### Current State (2026-04-07 Session 7)
- **VPS:** `cryptopass.service` running on master, 22 passports loaded ($500 fresh start)
- **Monitoring:** `cryptopass-metrics.service` on port 9103 → Prometheus/Grafana live on fight-uno
- **Enabled passports:** All 22 except Reversal (quarantined)
- **Disabled (quarantine):** `reversal.json` (`enabled: false`)
- **Telegram routing:** Trade signals → Trader Zone group topic (thread=6). System logs → General topic (thread=1). TP/SL replies threaded.
- **Tests:** 240/240 passing on master (HEAD `e323087`)

### Bugs Fixed in Session 7 (post-merge audit)
1. **Heartbeat timezone** — `datetime.utcnow()` vs SQLite CURRENT_TIMESTAMP (UTC) — matched correctly
2. **`open_positions_total` undercount** — `status='OPEN'` → `NOT IN ('TP3_CLOSED', 'SL_CLOSED')` 
3. **`reversal.json` still enabled** — quarantined: `enabled: false`
4. **`equity_snapshots_v2` missing** — all 3 queries now individually wrapped in try/except
5. **TP1/TP2 equity display in Telegram** — was showing pre-trade equity, now correctly shows `passport.equity + pos.realized_pnl`
6. **`snapshot_equity_all`** — `remaining_fraction` now applied per TP tier; `pending_realized` added to true_realized

### 30-Day Paper Trade Countdown (started 2026-04-07)
- **Goal:** Identify passports that hit PromotionPolicy 7-gate threshold (≥30d live, PF≥1.2, WR≥40%, MaxDD<15%)
- **Check weekly:** Grafana dashboard for equity curves + `cryptopass_heartbeat_age_seconds` for health
- **Expected signals:** MACDDivergence and BBMeanRev are top candidates based on 90d quality-pair backtest
- **Monitor:** If any passport fires >30 trades/week, audit for overtrade condition

### Short-term Priorities
1. **Let 30d paper trade run** — resist tweaking; collect real signal data
2. **Grafana dashboard** — add equity curve panel once snapshots accumulate (48h)
3. **Research engine (local only)** — VPS is compute-constrained; run `run_research.py` locally
4. **reversal_v2 next attempt** — raise `CONFIDENCE_THRESHOLD` to 75+, OR implement EMA as hard pre-filter (not weight)
5. **OBV hybrid passport** — `bb_position=1.5, obv_signal=0.5, volume_spike=2.0` — test on quality pairs

### Key Commands
```bash
# VPS health
ssh fight-tres "systemctl status cryptopass.service cryptopass-metrics.service --no-pager"
ssh fight-tres "journalctl -u cryptopass.service -n 50 --no-pager -o short-iso"

# Metrics
curl fight-tres:9103/metrics | grep cryptopass_equity
curl fight-tres:9103/health

# Grafana
open http://fight-uno:3333/d/cryptopass-main/cryptopass-trading-dashboard

# After code changes
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && systemctl restart cryptopass.service"
```

### Research Engine — First Live Run (2026-04-05)

**180-day quality-pair validation** (`scripts/run_new_passport_backtest.py`, 10 quality pairs, 180d):

| Rank | Passport | Trades | WR% | Return | PF | Status |
|------|----------|--------|-----|--------|----|--------|
| 1 | MACDDivergence v0.1 | 123 | 41.5% | +9.1% | 1.39 | 🟢 TOP |
| 2 | BBMeanRev v0.1 | 305 | 47.3% | +7.7% | 1.32 | 🟢 |
| 3 | RSIContrarian v0.1 | 97 | 36.1% | +0.5% | 1.02 | 🟡 marginal |
| 4 | BalancedSelective v0.1 | 254 | 40.6% | -4.2% | 0.92 | 🔴 |
| 5 | TrendMomentum v0.1 | 435 | 32.4% | -5.7% | 0.94 | 🔴 |
| 6 | PureTrend v0.1 | 431 | 32.0% | -5.3% | 0.95 | 🔴 |

Full log: `logs/new_passports_20260405_105110.log`

### 9e. Three New Strategy Passports — 90d Quality Pairs (Session 6, 2026-04-05)

**Passports:** DualMA Crossover, Donchian Breakout, OBV Trend  
**New indicators added to `bot/indicators.py`:** `calc_donchian_channel()`, `calc_obv_signal()`  
**Scorer wired:** both new indicators added to `score_confluence()` with backward-compat guard (default weight=0 for existing passports)

| Passport | Return | PF | Trades | WR% | MaxDD | Status |
|----------|--------|----|--------|-----|-------|--------|
| DualMA Crossover | -8.96% | 0.806 | 137 | 29.9% | 24.93% | 🔴 Disabled |
| Donchian Breakout | +0.56% | 1.016 | 111 | 34.2% | 17.71% | 🟡 Marginal |
| OBV Trend | -11.45% | 0.771 | 149 | 28.2% | 27.93% | 🔴 Disabled |

**Key learnings:**
- **DualMA**: Pure EMA crossover (10/20) over-trades in choppy 1H timeframe — 137 trades at 29.9% WR confirms whipsaw problem. EMA trend alone without momentum confirmation isn't selective enough.
- **Donchian Breakout**: Best of the 3 with PF=1.016 and lowest MaxDD=17.71%. Technically profitable but too marginal to enable. Most promising for re-test in a trending market (Q2 bull run or sustained downtrend). The EMA filter helps but channel breakouts still get faded in ranging conditions.
- **OBV Trend**: Highest trade count (149) at worst WR (28.2%) — OBV signal generates too many entries. OBV EMA crossover is too noisy as a primary signal; better used as a secondary confirmation (weight 0.5–1.0) alongside a trend indicator.
- **Pairs Trading**: Definitively rejected — single-asset scanner architecture is incompatible. Would require cross-symbol state + major architectural changes.
- **Selectivity principle re-confirmed**: All 3 new passports underperform HiddenGem/Sniper despite similar indicator count because the underlying signal quality (EMA crossover, Donchian breakout, OBV) is lower conviction than EMA+BB+Volume combo on 1H crypto.

**Next steps for new passports:**
- Donchian: re-test with 180d window covering a trending period; try raising `donchian_signal` weight to 4.0 and adding `bb_position=1.0` as breakout confirmation
- OBV: demote to secondary confirmation (weight=0.5–1.0) in a new hybrid passport alongside BB+Vol
- DualMA: try 4H timeframe or require MACD confirmation before enabling

**Research pipeline** (`run_research.py --all --days 90 --max-per-family 2`):
- Stage 1: ✅ Working — tested 4 candidates, 3 passed (ema_crossover-55: +4.1% Sharpe=1.15; rsi_momentum-50: +6.8% Sharpe=1.45)
- Stage 2: ✅ **FIXED** — `run_stage2()` now scales `train_days`/`test_days` proportionally when `total_days < train_days + test_days`. `--days 90` now gives `train=60, test=30` instead of degenerate fold. Fix is in `bot/research/pipeline.py` (branch `fix/strategy-parameter-tuning`).

**Next steps for research engine:**
4. **Re-run with quality pairs only** (fewer API calls, faster Stage 1):
   ```bash
   uv run python run_research.py --all --max-per-family 5 --pairs 10 --days 90
   ```
5. ~~**Backtest reversal_v2**~~ — ✅ DONE: v0.1 (-11.78%) and v0.2 EMA-gate experiment (-16.44%) both failed. See §10 issue #4 for full diagnosis.
6. **Test trailing stop on Dynamic** — enable `USE_TRAILING_STOP: true` on just the Dynamic passport and compare 90d results

### Long-term (new lineages to explore)

- **Multi-timeframe confluence** — 15m signal + 4H trend direction
- **Funding rate carry** — long when funding rate strongly negative
- **Volatility regime switching** — ATR percentile selects trend vs mean-reversion mode
- **Short-only passport** — shorts WR 65.2% vs longs 50.0% historically
- **OI + Liquidation clusters** — high-conviction reversal entries

---

## §17 — Why v0.1→v0.2 Passport Upgrades Failed (Deep Analysis)

> Added: 2026-04-09. Source: scorer.py math + passport changelog forensics.
> Purpose: Definitive root-cause analysis so this class of mistake is never repeated.

### Summary

Three profitable v0.1 passports were destroyed by v0.2 "improvements":

| Passport | v0.1 Return | v0.2 Return | Delta | v0.2 Trade Count |
|---|---|---|---|---|
| 💎 HiddenGem | **+25.9%** | -26.8% | **-52.7pp** | 450→771 (+72%) |
| 🎯 Sniper | **+26.0%** | -14.7% | **-40.7pp** | 450→812 (+80%) |
| 📢 VolumeKing | **+9.1%** | -20.5% | **-29.6pp** | 790→919 (+16%) |

All three were rolled back to v0.1 params as v0.3. This analysis explains the exact mechanisms that caused each failure.

### The Scoring Formula (Reference)

From `bot/scorer.py` L76–128:

```
For each non-volume indicator with weight > 0:
    total_weight += weight              (ALWAYS — even when NEUTRAL)
    dominant_score += weight            (ONLY when direction matches dominant)

Volume spike (special):
    If vol_spike=True AND dominant exists:
        total_weight += vol_weight
        dominant_score += vol_weight
    If vol_spike=False: completely ignored (0 weight, 0 score)

raw_confidence = dominant_score / total_weight × 100
confidence = raw_confidence × btc_weight
```

**Critical property:** Setting weight=0.0 removes an indicator entirely (adds 0 to total_weight). Setting weight=0.5 adds 0.5 to total_weight on EVERY candle, but only adds 0.5 to score when the indicator is directional and agrees with the dominant side. When NEUTRAL, it's pure dilution.

### Per-Passport Breakdown

---

#### 💎 HiddenGem: +25.9% → -26.8% (-52.7pp)

**What changed v0.1→v0.2:**
- `ema_trend`: 1.0 → 1.5
- `pressure`: 0.0 → 0.5 (NEW indicator activated)
- `CONFIDENCE_THRESHOLD`: 54 → 58
- `bb_position`: 1.0 (unchanged), `volume_spike`: 2.0 (unchanged)

**v0.1 base total_weight:** 2.0 (ema=1.0 + bb=1.0)
**v0.2 base total_weight:** 3.0 (ema=1.5 + bb=1.0 + pressure=0.5) — **+50% dilution surface**

**Root Cause #1: Asymmetric EMA weight broke tie-breaking**

In v0.1, EMA and BB had equal weight (1.0 each). When they disagreed, the result was a TIE → no signal. This was a crucial quality filter: the strategy only traded when trend (EMA) and mean-reversion (BB) agreed.

In v0.2, EMA weight=1.5 > BB weight=1.0. Now EMA can override BB's dissent:

| Market Condition | v0.1 (ema=1.0, bb=1.0) | v0.2 (ema=1.5, bb=1.0, pressure=0.5) |
|---|---|---|
| EMA=LONG, BB=SHORT, vol spike | Tie (1.0 vs 1.0) → **NO SIGNAL** | long=1.5 > short=1.0 → vol confirms → raw=(1.5+2.0)/(3.0+2.0)=**70%** → **FIRES** |
| EMA=LONG, BB=SHORT, pressure=LONG, vol spike | Tie → **NO SIGNAL** | long=1.5+0.5=2.0, short=1.0 → vol → raw=(2.0+2.0)/5.0=**80%** → **FIRES** |
| EMA=SHORT, BB=LONG, vol spike | Tie → **NO SIGNAL** | short=1.5 > long=1.0 → vol confirms → raw=**70%** → **FIRES** |

These are BAD entries. EMA says "trending" while BB says "overextended" — entering with trend here means buying overbought or selling oversold. This is exactly the type of trade that loses money.

**Root Cause #2: Pressure's NEUTRAL dilution**

`calc_pressure()` returns NEUTRAL when buy pressure is between 40-60% (the `PRESSURE_THRESHOLD=60` check in `indicators.py` L227-232). On 1H crypto candles, this happens on approximately 40-50% of candles — pressure is indecisive more often than not.

When pressure is NEUTRAL, its 0.5 weight inflates total_weight without contributing to score:

| Scenario | v0.1 Confidence | v0.2 Confidence (pressure=NEUTRAL) |
|---|---|---|
| EMA✓ BB✓ vol✓ | (1+1+2)/(1+1+2) = **100%** | (1.5+1+2)/(1.5+1+0.5+2) = **90%** |
| EMA✓ BB✓ no vol | (1+1)/(1+1) = **100%** | (1.5+1)/(1.5+1+0.5) = **83.3%** |
| EMA✓ BB=N vol✓ | (1+2)/(1+1+2) = **75%** | (1.5+2)/(1.5+1+0.5+2) = **70%** |
| BB✓ EMA=N vol✓ | (1+2)/(1+1+2) = **75%** | (1+2)/(1.5+1+0.5+2) = **60%** |

Every scenario loses 5-17pp of confidence. Trades that were 100% conviction become 83-90%. Trades at 75% drop to 60-70%. This pushes entries into lower leverage tiers (7×→5×→4×), reducing profit on wins while losses stay the same.

**Combined effect:**
- v0.1 possible raw confidences: {50%, 75%, 100%} — only 75% and 100% fire (binary, clean)
- v0.2 possible raw confidences: {33%, 50%, 58%, 60%, 66%, 70%, 80%, 83%, 90%, 100%} — many intermediate values fire
- v0.1 fires when EMA+BB agree or one agrees+vol spike (high-quality setups only)
- v0.2 fires when EMA overrides BB in disagreement, creating 321 NEW low-quality entries
- Trade count: 450→771 (+72%), turning +25.9% into -26.8%

---

#### 🎯 Sniper: +26.0% → -14.7% (-40.7pp)

**What changed v0.1→v0.2:**
- `ema_trend`: 1.0 → 1.5
- `macd_signal`: 0.0 → 1.0 (NEW indicator activated)
- `CONFIDENCE_THRESHOLD`: 70 → 65
- `bb_position`: 1.0 (unchanged), `volume_spike`: 2.0 (unchanged)

**v0.1 base total_weight:** 2.0 (ema=1.0 + bb=1.0)
**v0.2 base total_weight:** 3.5 (ema=1.5 + macd=1.0 + bb=1.0) — **+75% dilution surface**

**Root Cause #1: Same tie-breaking destruction as HiddenGem**

EMA=1.5 overrides BB=1.0 dissent:

| Market Condition | v0.1 | v0.2 |
|---|---|---|
| EMA=LONG, BB=SHORT, MACD=LONG, vol spike | Tie (EMA=BB=1.0) → **NO SIGNAL** | long=1.5+1.0=2.5, short=1.0 → raw=4.5/5.5=**81.8%** → **FIRES** |
| EMA=LONG, BB=SHORT, MACD=NEUTRAL, vol spike | Tie → **NO SIGNAL** | long=1.5, short=1.0 → raw=3.5/5.5=**63.6%** → doesn't fire at 65 |

When MACD confirms EMA (which it often does — both are trend-following), the 2-vs-1 supermajority (EMA+MACD vs BB) creates a false sense of confluence. In reality, MACD and EMA are highly correlated (both derived from exponential moving averages), so MACD "confirming" EMA provides almost no independent information.

**Root Cause #2: MACD nearly never returns NEUTRAL**

Unlike pressure (NEUTRAL ~40-50% of time), MACD returns LONG or SHORT on almost every candle (histogram > 0 = LONG, < 0 = SHORT, per `indicators.py` L66-77). This means MACD's 1.0 weight almost always adds to total_weight AND to one side's score.

This creates a new failure mode: MACD can CREATE a majority where none existed:

| Scenario | v0.1 | v0.2 |
|---|---|---|
| EMA=NEUTRAL, BB=NEUTRAL, MACD=LONG, vol spike | No direction (both 0) → **NO SIGNAL** | long=1.0, short=0 → vol → raw=3.0/5.5=**54.5%** → doesn't fire at 65 |
| EMA=LONG, MACD=LONG, BB=NEUTRAL, no vol | long=1 → raw=50% → **NO SIGNAL** (threshold 70) | long=2.5 → raw=2.5/3.5=**71.4%** → **FIRES at 65** |

The last scenario is critical: EMA+MACD agreement without volume confirmation now fires. In v0.1, this required vol spike (75% at threshold 70). In v0.2, the extra MACD weight pushes confidence above the lowered 65% threshold even without volume. These unconfirmed-by-volume entries are lower quality.

**Root Cause #3: Threshold lowered 70→65**

v0.1 Sniper's edge was extreme selectivity: threshold=70 with minimum achievable confidence=75% meant EVERY trade had at least 75% conviction. Lowering to 65 opened the door for weaker setups.

**Combined effect:**
- v0.1: Only fires when EMA+BB agree (75-100%), extremely selective
- v0.2: Fires on EMA+MACD agreement (71.4%), EMA override of BB (81.8%), and intermediate scenarios
- Trade count: 450→812 (+80%), turning +26.0% into -14.7%

---

#### 📢 VolumeKing: +9.1% → -20.5% (-29.6pp)

**What changed v0.1→v0.2:**
- `volume_spike` weight: 3.0 → 2.5
- `VOLUME_SPIKE_THRESHOLD`: 2.5 → 2.0
- `macd_signal`: 0.0 → 0.5 (NEW indicator activated)
- `pressure`: 0.0 → 0.5 (NEW indicator activated)
- `ema_trend`: 1.0 (unchanged), `candle_direction`: 1.0 (unchanged)

**v0.1 base total_weight:** 2.0 (ema=1.0 + candle=1.0)
**v0.2 base total_weight:** 3.0 (ema=1.0 + macd=0.5 + pressure=0.5 + candle=1.0) — **+50% dilution surface**

**Root Cause #1: Volume threshold lowered 2.5x→2.0x**

VolumeKing's entire thesis is "only trade on genuine volume spikes." The 2.5x threshold was specifically high to filter for unusual institutional-grade volume events. Lowering to 2.0x means:
- A volume bar at 2.0x average is relatively common (happens several times per day per pair)
- A volume bar at 2.5x average is genuinely unusual (happens a few times per week)
- Estimated ~40% more candles qualify as "spikes" at 2.0x vs 2.5x
- This floods the strategy with mediocre volume events that don't represent real momentum

**Root Cause #2: Dilution destroyed the volume dominance**

v0.1's genius was volume_spike=3.0 being the dominant weight. When vol spike fires alongside one directional indicator:

| Scenario | v0.1 (vol=3.0, base=2.0) | v0.2 (vol=2.5, base=3.0) |
|---|---|---|
| EMA✓ candle=N vol✓ | (1+3)/(1+1+3)=**80%** | (1+2.5)/(1+0.5+0.5+1+2.5)=**63.6%** |
| candle✓ EMA=N vol✓ | (1+3)/(1+1+3)=**80%** | (1+2.5)/(1+0.5+0.5+1+2.5)=**63.6%** |
| EMA✓ candle✓ vol✓ | (1+1+3)/(1+1+3)=**100%** | varies by MACD/pressure: **81.8-100%** |
| EMA✓ candle✓ no vol | (1+1)/(1+1)=**100%** | (1+1)/(3.0)=**66.7%** |

The 80%→63.6% drop is devastating: entries that were in the 7× leverage tier (70-100%) now fall to the 4× tier (54-60%). Wins shrink by ~43% (4×/7×) while losses stay proportional to risk.

**Root Cause #3: New low-quality MACD/pressure entries**

| New scenario (v0.2 only) | Confidence |
|---|---|
| MACD✓ only + vol spike | (0.5+2.5)/5.5 = **54.5%** → barely fires |
| Pressure✓ only + vol spike | (0.5+2.5)/5.5 = **54.5%** → barely fires |

These 54.5% entries didn't exist in v0.1 (MACD and pressure were weight=0). They're the lowest quality entries possible — a single minor indicator plus volume. They fire near the 54% threshold floor with 4× leverage, meaning small wins and regular losses.

**Combined effect:**
- Volume threshold reduction: more fake spikes → more bad entries
- Weight dilution: 80% confidence → 63.6% → lower leverage on same market conditions
- New indicators: created 54.5% bottom-scraping entries
- Trade count: 790→919 (+16%), turning +9.1% into -20.5%

---

#### 🏆 OG: -13.1% → -28.8% (-15.7pp) — Different Mechanism

**What changed:** Only `VOLUME_SPIKE_THRESHOLD`: 1.5 → 2.0 (weights unchanged, all 8 at 1.0)

OG was already unprofitable at v0.1 (-13.1%) due to all 8 indicators being active (massive NEUTRAL dilution). The v0.2 change made it worse through a subtler mechanism:

With all 8 indicators active, volume confirmation is the primary quality filter. A typical scenario:
- 4 of 7 directional indicators agree + vol spike: (4+1)/(7+1) = **62.5%** → tier 2 (5× leverage)
- Same 4 agree + NO vol spike: 4/7 = **57.1%** → tier 1 (4× leverage)

Raising vol threshold from 1.5x to 2.0x caused entries with volume between 1.5-2.0x to lose their vol confirmation. These entries dropped from 62.5% to 57.1% confidence — still firing, but at 4× instead of 5× leverage. The volume-confirmed entries (62.5%) were systematically the BETTER trades (genuine momentum). Removing their vol confirmation didn't stop them from trading, it just reduced their profit potential while keeping the same downside.

Trade count: 1267→1148 (-9%). Fewer trades AND worse quality on remaining trades.

---

#### 🚀 Momentum: -39.5% → -20.0% (+19.5pp) — Why v0.2 IMPROVED

**What changed:** ema=1→2, rsi_div=1→0.5, pressure=1→0.5, candle=1→0.5, vol=1→1.5, threshold=54→60, max_positions=50→30

This moved TOWARD selectivity:
- Higher threshold (60 vs 54) filtered borderline entries
- Reduced noise indicator weights (rsi_div, pressure, candle from 1.0 to 0.5) cut their dilution impact
- EMA emphasis (2.0) gave trend direction more decisive weight
- Trade count: 1317→1095 (-17%) — fewer, better trades
- Still negative (-20.0%) because 8 indicators remain active (total base weight = 6.5)

---

#### 🎯 Dynamic: -16.3% → -20.0% (-3.7pp net, but +12.3pp MaxDD improvement)

**What changed:** Same weight changes as Momentum + `USE_TRAILING_STOP`: true→false

The improvement in MaxDD (85.9%→73.6%) came from disabling the broken trailing stop. The weight changes were identical to Momentum v0.2. Net return slightly worse but risk profile dramatically better.

---

### The Math: Confidence Dilution Worked Examples

#### Example 1: HiddenGem — Adding pressure=0.5 to a 3-indicator passport

**Setup:** EMA=LONG, BB=LONG, vol_spike=True, pressure=NEUTRAL (the most common pressure state)

```
v0.1: dominant = 1.0 + 1.0 + 2.0 = 4.0
       total   = 1.0 + 1.0 + 2.0 = 4.0
       raw     = 4.0/4.0 × 100   = 100.0%  → 7× leverage (tier 3)

v0.2: dominant = 1.5 + 1.0 + 2.0 = 4.5       (pressure NEUTRAL: +0 to score)
       total   = 1.5 + 1.0 + 0.5 + 2.0 = 5.0 (pressure NEUTRAL: +0.5 to total)
       raw     = 4.5/5.0 × 100   = 90.0%  → 7× leverage (tier 3)

Confidence delta: -10pp on the SAME market condition.
Still in tier 3, but the safety margin above threshold eroded significantly.
```

#### Example 2: The deadly tie-break (HiddenGem/Sniper)

**Setup:** EMA=LONG, BB=SHORT, vol_spike=True

```
v0.1: long_score = 1.0 (EMA), short_score = 1.0 (BB)
       TIE → "No directional consensus" → NO SIGNAL

v0.2: long_score = 1.5 (EMA), short_score = 1.0 (BB)
       EMA wins → vol confirms LONG → total=5.0, long=3.5
       raw = 3.5/5.0 × 100 = 70.0%  → SIGNAL FIRES at 7× leverage

This entry is BUYING into an overbought BB condition (BB=SHORT means price > 80th
percentile of Bollinger range). EMA says trend, BB says overextended. v0.1 correctly
refused this trade. v0.2 takes it because EMA's extra 0.5 weight breaks the tie.
```

#### Example 3: VolumeKing — Volume weight dilution

**Setup:** EMA=LONG, candle=NEUTRAL, vol_spike=True

```
v0.1: dominant = 1.0 + 3.0 = 4.0, total = 1.0 + 1.0 + 3.0 = 5.0
       raw = 4.0/5.0 × 100 = 80.0%  → 7× leverage

v0.2: dominant = 1.0 + 2.5 = 3.5, total = 1.0 + 0.5 + 0.5 + 1.0 + 2.5 = 5.5
       raw = 3.5/5.5 × 100 = 63.6%  → 4× leverage

Same market condition: leverage drops from 7× to 4× — a 43% reduction in profit
potential per winning trade, while the risk amount per trade stays the same.
```

#### Example 4: The general dilution formula

For a passport with `n` active non-volume indicators of equal weight `w` and volume weight `v`:

```
When k of n indicators agree + vol spike:
    confidence = (k×w + v) / (n×w + v) × 100

Adding 1 indicator (n→n+1) with weight w:
    If it agrees:   new_conf = ((k+1)×w + v) / ((n+1)×w + v) × 100  (slightly higher)
    If it's NEUTRAL: new_conf = (k×w + v) / ((n+1)×w + v) × 100     (LOWER — diluted)
    If it opposes:   new_conf = (k×w + v) / ((n+1)×w + v) × 100     (same as NEUTRAL!)

The NEUTRAL case is the common case for most indicators on most candles.
```

Example with HiddenGem numbers (k=2, n=2, w=1.0, v=2.0):
```
Before: (2×1 + 2) / (2×1 + 2) = 4/4 = 100%
After adding 1 NEUTRAL indicator:
        (2×1 + 2) / (3×1 + 2) = 4/5 = 80%  → instant 20pp drop
```

### The Three Failure Mechanisms

| # | Mechanism | Affected Passports | How It Destroys Performance |
|---|---|---|---|
| 1 | **Tie-breaking destruction** | HiddenGem, Sniper | Asymmetric weights (ema>bb) let trend override mean-reversion dissent. Creates entries where EMA says "go" but BB says "overextended." These are the worst entries. |
| 2 | **NEUTRAL dilution** | All three | Adding weight to indicators that are frequently NEUTRAL (pressure ~40-50%, BB in middle ~60%) inflates total_weight without adding to score. Every entry loses 5-20pp of confidence. |
| 3 | **Threshold/filter relaxation** | VolumeKing, Sniper | Lowering vol threshold (2.5→2.0) or confidence threshold (70→65) admits lower-quality setups that the original passport specifically filtered out. |

### Why Win Rate Barely Changed But Returns Collapsed

| Passport | v0.1 WR | v0.2 WR | Δ WR | v0.1 Return | v0.2 Return |
|---|---|---|---|---|---|
| HiddenGem | 33.8% | 33.9% | +0.1pp | +25.9% | -26.8% |
| Sniper | 33.8% | 33.6% | -0.2pp | +26.0% | -14.7% |
| VolumeKing | 34.1% | 33.8% | -0.3pp | +9.1% | -20.5% |

Win rate barely moved because the NEW entries (from tie-breaking destruction) have roughly the same ~34% hit rate as existing entries. But the QUALITY of wins degraded:

1. **Lower leverage on all trades** — confidence dilution pushes trades from tier 3 (7×) to tier 2 (5×) or tier 1 (4×). A 7× win at 2:1 R:R = +14% of risk. A 4× win at 1.25:1 = +5% of risk. Same loss either way: -1× risk.

2. **More trades = more fees** — At 0.04% per side (0.08% round-trip), 321 extra trades at average 4× leverage = 321 × 0.08% × 4 = ~10.3% of portfolio eaten by fees alone.

3. **More concurrent positions = worse drawdowns** — More entries means more simultaneous losers during adverse regimes. MaxDD: HiddenGem 60.1%→68.2%, VolumeKing 73.1%→79.9%.

### Lessons (Actionable Rules)

1. **Never break indicator tie-breaking.** If two indicators have equal weight and opposite thesis (trend vs mean-reversion), their tie = "no signal" is a FEATURE. Giving one extra weight to "break ties" is actually removing a safety filter.

2. **Never add an indicator without calculating the NEUTRAL dilution cost.**
   Before adding indicator X with weight w to a passport with base total_weight T:
   ```
   dilution_cost = w / (T + w) × 100
   ```
   For HiddenGem adding pressure=0.5: 0.5/(2.0+0.5)×100 = **20% dilution** on every NEUTRAL candle.
   This must be justified by a proportional improvement in signal quality.

3. **Every indicator added must be independently informative.** MACD "confirming" EMA is almost worthless — both are EMA-derived. Pressure "confirming" trend is low-value — pressure is noisy on 1H candles. Only add indicators that filter a specific failure mode the existing set misses.

4. **The minimum achievable confidence IS the strategy's selectivity floor.** Calculate it before deploying:
   ```
   min_confidence = min_agreeing_weight / (base_total_weight + vol_weight) × 100
   ```
   If min_confidence is close to CONFIDENCE_THRESHOLD, the strategy will fire on marginal setups.

5. **Volume threshold is the quality-of-entry filter, not a tuning parameter.** VolumeKing at 2.5x was selective for a reason. Lowering it "for more trades" is lowering the bar for what counts as unusual volume — the exact thing the strategy is built to detect.

6. **If a passport is profitable, the ONLY safe changes are:**
   - Raising CONFIDENCE_THRESHOLD (fewer, higher-quality trades)
   - Raising VOLUME_SPIKE_THRESHOLD (stricter volume filter)
   - Removing an indicator (set weight to 0.0) — reduces dilution
   - Position sizing changes (max_positions, risk_pct)
   - NEVER: adding indicators, lowering thresholds, or changing relative weight ratios

7. **Momentum/Dynamic improved because they moved TOWARD selectivity** — reduced noise indicator weights, raised threshold, capped positions. The pattern is universal: less is more.

---

## Appendix: Key File Locations

| Purpose | File |
|---|---|
| Scoring engine | `bot/scorer.py` |
| All indicators | `bot/indicators.py` |
| Position lifecycle | `bot/position_manager.py` |
| Backtest engine | `bot/backtester.py` |
| Multi-passport runner | `bot/main_multi.py` |
| Research pipeline | `bot/research/pipeline.py` |
| Portfolio risk | `bot/risk/portfolio_risk.py` |
| Health/promotion | `bot/health/promotion.py` |
| State DB | `bot/deploy/state_db.py` |
| Passport configs | `pumpradar-passports/configs/*.json` |
| Version registry | `pumpradar-passports/VERSIONS.md` |
| Backtest script | `scripts/run_new_passport_backtest.py` |
| Validation script | `scripts/run_passport_validation.py` |
| Reference strategies | `~/fight/trading/reference/agentic/151-trading-strategies/` |
| Strategy spec | `docs/strategy_spec.md` |
| Deep dive analysis | `docs/superpowers/plans/2026-04-04-strategy-deepdive-parameter-fix.md` |
| Historical signals | `data/validated_ledger.csv`, `data/equity_summary.json` |

---

## §18 — 4-Regime Upgrade (Session 10)

**Date:** 2026-04-09
**Branch:** master
**Tests:** 332 passing (was 296 before upgrade)

### Change
Replaced 3-regime EMA-based BTC trend detector with 4-regime ADX+volatility classifier.

**Old system:** `fetch_btc_trend()` → EMA 9/21 crossover on 4H → `"Uptrend"`/`"Downtrend"`/`"Sideways"`
**New system:** `RegimeDetector.get_current_regime()` → 4H `classify_regime()` + 1H EMA confirmation → `"TREND_UP"`/`"TREND_DOWN"`/`"HIGH_VOL_CHOP"`/`"LOW_VOL_COMPRESSION"`

### Key design decisions
- 1H confirmation only DOWNGRADES trending regimes (never upgrades)
- Cache TTL = 1 hour, safe default = `HIGH_VOL_CHOP`
- Passive mode (Phase 1): `active_regimes` field parsed + logged, but NOT enforced
- `RegimeLogger` collects per-scan, per-signal, per-trade regime data to SQLite

### Files added
| File | Purpose |
|---|---|
| `bot/regime_detector.py` | Cached multi-TF regime detection (4H primary + 1H confirmation) |
| `bot/regime_logger.py` | SQLite regime data collection + daily Telegram digest |
| `tests/test_regime_detector.py` | 12 tests |
| `tests/test_regime_logger.py` | 10 tests |
| `tests/test_scanner_regime.py` | 4 tests |
| `tests/test_backtester_regime.py` | 3 tests |
| `tests/test_passport_runner_regime.py` | 4 tests |
| `tests/test_regime_integration.py` | 2 tests |

### Files modified
| File | Change |
|---|---|
| `bot/config.py` | `BTC_TREND_WEIGHTS` migrated from 3 to 4 keys |
| `bot/scanner.py` | Delegates to `RegimeDetector` instead of `fetch_btc_trend()` |
| `bot/backtester.py` | `determine_btc_trend_at()` uses `classify_regime()` for parity |
| `bot/passport_runner.py` | Old-key warning, 4-regime guardrails, `active_regimes` Phase 1, `RegimeLogger` wiring |
| `bot/data_fetcher.py` | `fetch_btc_trend()` deprecated with warning |
| `bot/research/regime.py` | `map_to_live_regime()` returns native 4-regime keys |
| 5 passport JSONs | `BTC_TREND_WEIGHTS` migrated to 4-regime format |

### Passport migration
- 5 passports with explicit `BTC_TREND_WEIGHTS` overrides migrated from 3→4 keys (all mean-reversion, all set to 1.0 for all regimes)
- 17 passports use config defaults (auto-migrated via config change)

### Backtester parity
`determine_btc_trend_at()` now uses same `classify_regime()` as live `RegimeDetector`. This ensures backtest results reflect the same regime classification as live trading.

### Implementation approach
- 10-task TDD plan with dependency graph
- Executed via subagent-driven development (4 parallel waves)
- Wave 1: RegimeDetector + Config + Passports + RegimeLogger (parallel)
- Wave 2: Scanner + Backtester + PassportRunner (parallel)
- Wave 3: Integration wiring + Deprecation (parallel)
- Wave 4: Docs + verification

---

## §19 — Counter-Trend Penalty & Portfolio Triage (Session 10b, 2026-04-09)

### Critical discovery: directional gap in scorer

**Root cause of -59% portfolio loss identified:**
- `BTC_TREND_WEIGHTS` applies same confidence multiplier regardless of signal direction
- During TREND_UP (0.8×), SHORT signals pass just as easily as LONG
- Live analysis: 77-92% of HiddenGem/Sniper/BBMeanRev trades were SHORT during BTC uptrend
- Only PressureReader profitable (+$12, 100% LONG, PF 1.06)

### Fix: COUNTER_TREND_PENALTY

New config multiplier applied **after** `BTC_TREND_WEIGHTS`, only for counter-trend signals:
```
final = raw_confidence × BTC_TREND_WEIGHT × COUNTER_TREND_PENALTY (if counter-trend)
```

| Config | TREND_UP | TREND_DOWN | CHOP | COMPRESSION |
|--------|----------|-----------|------|-------------|
| Default (trend-follow) | 0.5 | 0.5 | 1.0 | 1.0 |
| Mean-reversion override | 1.0 | 1.0 | 1.0 | 1.0 |

- Trend-following: SHORT during TREND_UP → 0.8 × 0.5 = 0.4 effective → requires 135% raw conf → **blocked**
- Mean-reversion: SHORT during TREND_UP → 0.8 × 1.0 = 0.8 → requires 67.5% raw conf → **trades freely**

Applied to both `scorer.py` and `extended_scorer.py` (research parity).

### Portfolio triage: 9 passports disabled

All passports with PF < 0.30 disabled (they still manage existing open positions until they close):
- HiddenGem (PF 0.09), Sniper (PF 0.15), VolumeKing (PF 0.42)
- DualMA (PF 0.24), MinimalEdge (PF 0.25), TrendMomentum (PF 0.27)
- Donchian (PF 0.19), OBV Trend (PF 0.18), PureTrend (PF 0.20)

12 active passports remain.

### Phase 4 research results (Apr 9 run)

**107 generated → 24 Stage 1 → 0 Stage 2** (Binance API timeout killed all Stage 2 evaluations)

Stage 1 standouts (before network death):
| Strategy | Return | Max DD | Sharpe |
|----------|--------|--------|--------|
| rsi_bb_reversal (BB=15, STD=1.5, conf=65) | **+7.1%** | 14.9% | 1.51 |
| vwap_deviation (conf=65) | +3.6% | 11.4% | 0.86 |
| stochastic_reversal (conf=65) | +3.5% | 11.4% | 0.85 |

All trend-following candidates (obv, donchian, keltner, ichimoku) showed -15% to -18% returns.

**Insight:** Mean-reversion continues to outperform in recent market conditions. The counter-trend penalty will help trend-followers avoid bleeding against the trend, while mean-reversion strategies trade freely.

### Key anti-pattern documented

**Never apply a uniform confidence multiplier regardless of signal direction.** The BTC_TREND_WEIGHTS multiplier was introduced to be "selective during bull markets" but it was selective for ALL signals, not just counter-trend ones. A directional filter must be directional.

## §20 — BollingerBreakout Promotion & Phase 4 Retry (Session 10b continued, 2026-04-10)

### Phase 4 research retry results

**Run 1 (Apr 9, with resilient retry):** 107 generated → **81 Stage 1 survivors** (vs 24 in previous run!). Dramatic improvement, likely due to `--quality-pairs` flag giving stable backtests.

Stage 2 walk-forward: **8 PASS / 8 FAIL** out of 16/81 evaluated (process died — laptop sleep).

| Strategy | Sharpe | Median Return | Verdict |
|----------|--------|---------------|---------|
| bollinger_breakout (BB=15,1.5σ,conf=55) | **2.39** | **+23.9%** | ✅ STAR |
| bollinger_breakout (conf=65) | 2.09 | +21.5% | ✅ |
| bollinger_breakout (conf=50,vol=2.0) | 2.09 | +21.6% | ✅ |
| bollinger_breakout (conf=60) | 1.69 | +23.3% | ✅ |
| macd_divergence (conf=50,fast=8/slow=21/sig=7) | 1.61 | **+25.9%** | ✅ |
| rsi_momentum (conf=50,vol=2.0) | 1.39 | +12.5% | ✅ |
| bollinger_breakout (conf=50) | 1.14 | +2.2% | ✅ |
| rsi_momentum (conf=50,vol=1.5) | 1.13 | +2.2% | ✅ |

**Key insight:** bollinger_breakout dominates — 5 of 8 passes. BB(15,1.5σ) + Vol + Pressure is a potent combination. Uses 3 active indicators (selectivity principle).

### BollingerBreakout passport promoted to paper trading

Created `passports/cryptopass-research/bollinger_breakout.json` v0.1:
- Config: BB_PERIOD=15, BB_STD=1.5, CONFIDENCE_THRESHOLD=55
- Active indicators: bb_position=2.0, volume_spike=1.5, pressure=1.0
- BTC_TREND_WEIGHTS: default (0.8 Uptrend) — breakout thesis aligned with trend
- COUNTER_TREND_PENALTY: default (0.5) — breakout filtered by trend direction
- Deployed to VPS, 22 passports total (13 active + 9 disabled managing open positions)

### Post-CTP performance (first 24h since Apr 9 deployment)

**CRITICAL FINDING:** CTP deployment was a game changer. Portfolio went from bleeding to broadly profitable.

| Passport | Post-CTP PnL | WR | PF | Status |
|----------|-------------|-----|-----|--------|
| VolumeKing | **+$281.77** | 88.9% | 5.85 | Disabled (closing old positions) |
| **PressureReader** | **+$191.82** | 60.0% | 2.29 | Focus 3 ⭐ |
| HiddenGem | +$160.99 | 62.5% | 4.47 | Disabled |
| DualMA | +$143.51 | 53.8% | 7.17 | Disabled |
| Sniper | +$136.49 | 61.1% | 2.61 | Disabled |
| OG | +$113.41 | 46.3% | 1.31 | Active |
| OBV Trend | +$108.28 | 53.8% | 5.78 | Disabled |
| BBMeanRev | +$81.59 | 56.0% | 1.77 | Active |
| MACDDivergence | -$21.16 | 31.2% | 0.89 | Focus 3 |
| BreakoutVol | -$3.65 | 28.6% | 0.95 | Focus 3 |

**Note:** Disabled passports are closing pre-CTP positions profitably (market favorable). Active passports with CTP filtering show improved quality. PressureReader confirmed as alpha generator.

Portfolio total: $8,382.67 (started $11,000). Still underwater but recovering — first day of consistent profitability across most passports.

### Research Phase 4 retry #2 (Apr 10)

Restarted from scratch: `nohup uv run python run_research.py --all --max-per-family 5 --days 180 --quality-pairs`. Running locally on MacBook. Expected ~6-8 hours for all 4 stages.

---

## §21: Bugs Found & Fixed — Session 10b Parallel Investigation (Apr 10)

Three parallel investigations dispatched. All findings documented below.

### Bug 20: TP3_HIT Negative PnL — Bankrupt Equity Inversion 🔴

**Severity:** Critical (inverts ALL PnL calculations)
**Root cause:** `open_position()` had no guard against negative equity. When a passport's equity goes below $0 (e.g., Sniper with 50 simultaneous SL hits: $500 - 50×$17.52 = -$376), `risk_amount = equity × 0.5% = -$1.88`. This makes every PnL formula produce inverted results — TP3_HIT returns *negative* realized_pnl.

**Numerical confirmation (matches VPS data exactly):**
```
equity ≈ -$391 → risk_amount = -$11.73
TP1 profit: -$11.73 × 1.5 × 0.70 = -$12.32
TP2 profit: -$11.73 × 1.5 × 1.61 × 0.20 = -$5.67
TP3 profit: -$11.73 × 1.5 × 1.61 × 1.53 × 0.10 = -$4.33
TOTAL: -$22.32 ≈ observed -$22.36 ✓
```

**Fix:** Single guard in `bot/position_manager.py:open_position()`:
```python
if equity <= 0:
    return None
```
**Commit:** `8329337`

### Bug 21: CTP=0.5 Was a Complete Off-Switch, Not a Penalty 🔴

**Severity:** Critical (no counter-trend signals possible in TREND_UP/DOWN)
**Root cause:** BTC_TREND_WEIGHTS (0.8) and CTP (0.5) stack multiplicatively:
```
SHORT during TREND_UP = raw × 0.8 × 0.5 = raw × 0.40
Max achievable: 100 × 0.4 = 40 < CONFIDENCE_THRESHOLD(54) → IMPOSSIBLE
```
CTP was deployed as a "penalty" but mathematically it's a binary block. No short signal can ever fire during TREND_UP, regardless of conviction.

**Fix:** CTP 0.5 → 0.75 → **0.68** (final). Tuning rationale:
```
CTP=0.50 → max = 100 × 0.8 × 0.50 = 40 → ALL counter-trend BLOCKED (binary off-switch)
CTP=0.68 → max = 100 × 0.8 × 0.68 = 54.4 → only raw ≥ 99.3% pass (1% safety valve)
CTP=0.75 → max = 100 × 0.8 × 0.75 = 60 → raw ≥ 90% pass (too loose)
```
Backtest (90d, 4 pairs) confirmed stricter = better:
- BreakoutVol: CTP=0.50 → +20.4%, CTP=0.75 → +17.6%
- BBMeanRev: identical (overrides CTP=1.0)
- PressureReader: both negative, marginal difference

CTP=0.68 chosen as minimum value that still allows near-perfect setups while blocking 99%+ of low-quality counter-trend signals.
**Commits:** `8329337` (initial fix), `7f116d4` (final tuning to 0.68)

### Bug 22: Research Extended Scorer Leverage Mismatch 🟡

**Severity:** Medium (research PnL underestimated by 2-3×)
**Root cause:** `bot/research/extended_scorer.py` had hardcoded leverage tiers (1-5×) that didn't match live `config.LEVERAGE_TIERS` (4-7×):

| Confidence | Live (scorer.py) | Research (extended_scorer.py) |
|---|---|---|
| 70%+ | **7×** | ~~5×~~ → **7×** (fixed) |
| 61-69% | **5×** | ~~2×~~ → **5×** (fixed) |
| 54-60% | **4×** | ~~1×~~ → **4×** (fixed) |

Research Stage 1-4 results were undervaluing strategy performance. Not a live trading bug, but invalidates historical research PnL estimates.

**Fix:** Aligned `_leverage_from_confidence()` in extended_scorer to match live config.
**Commit:** `8329337`

### Finding: Backtest-Live Gap Root Cause — SHORT Signal Quality

**Not a bug, but critical insight:**
```
LONG:  735 trades, +$1,200, WR=45.4% (PROFITABLE)
SHORT: 713 trades, -$5,989, WR=16.4% (CATASTROPHIC)
```
Risk/reward is actually good (avg TP win $20.12 vs avg SL loss $11.11 = 1.81×). Problem is signal *frequency* — too many low-quality SHORT entries, especially counter-trend. CTP is the correct architectural fix. With CTP=0.68, only near-perfect (raw ≥ 99%) counter-trend signals fire during TREND_UP.

### CTP Tuning: Backtest Comparison (scripts/backtest_ctp_compare.py)

| Passport | CTP | Return | MaxDD | WR% | PF | Trades | L/S |
|---|---|---|---|---|---|---|---|
| BreakoutVol | 0.50 | **+20.4%** | -21.1% | 48% | 1.36 | 151 | 76/75 |
| BreakoutVol | 0.75 | +17.6% | -23.5% | 47% | 1.28 | 169 | 98/71 |
| BBMeanRev | 0.50 | +4.7% | -14.5% | 42% | 1.17 | 73 | 53/20 |
| BBMeanRev | 0.75 | +4.7% | -14.5% | 42% | 1.17 | 73 | 53/20 |
| PressureReader | 0.50 | -16.1% | -32.2% | 29% | 0.78 | 139 | 131/8 |
| PressureReader | 0.75 | -15.5% | -32.6% | 36% | 0.78 | 164 | 163/1 |

**Conclusion:** Stricter CTP → better returns for trend-followers. 0.68 chosen as the mathematical minimum that still allows a 1% safety valve for genuinely exceptional counter-trend setups.

### New Tool: Daily PnL Monitor

Created `scripts/daily_monitor.py` — pulls state.db from VPS, displays per-passport dashboard:
- Focus passports highlight (PressureReader, MACDDivergence, BreakoutVol, BollingerBreakout)
- LONG vs SHORT direction split
- Pre-CTP vs Post-CTP performance comparison
- Colored terminal output with aligned columns
- 20 tests in `tests/test_daily_monitor.py`

Usage: `uv run python scripts/daily_monitor.py`

### All 9 Disabled Passports Re-enabled

HiddenGem, Sniper, VolumeKing, DualMA, MinimalEdge, TrendMomentum, Donchian, OBV Trend, PureTrend — all re-enabled now that CTP filters counter-trend signals. Only `reversal.json` remains quarantined. Commit: `c708f59`.

---

## Session 11 — KlineCache + Live Performance Analysis (2026-04-11)

### KlineCache Implemented — Research Infrastructure Fix

**Problem:** Research pipeline made ~5,350 Binance API calls per run, taking 10-22 hours and crashing 5/9 times from API timeouts.

**Solution:** Parquet-based kline data cache (`bot/research/data_cache.py`):
- Downloads all symbol data once during `prefetch()` (41 seconds for 16 symbols × 180 days)
- Serves all backtesting from memory — zero API calls during Stage 1-4
- Gap detection: only fetches missing date ranges on subsequent runs
- Per-symbol error isolation: one API failure doesn't abort entire pipeline
- Cache stats: 16 files, 118,874 rows, 4.4 MB disk

**Performance improvement:**
| Metric | Before | After |
|--------|--------|-------|
| API calls per run | ~5,350 | ~100 (prefetch only) |
| Run time | 10-22 hours | ~4 hours |
| Crash rate | 56% (5/9 runs) | 0% expected |
| Disk usage | N/A | 4.4 MB |

Files: `bot/research/data_cache.py`, `bot/backtester.py` (kline_provider param), `bot/research/pipeline.py` (wiring).
Tests: 383/383 passing. Commits: `92dfbc3` → `9ae706c`.

### Live Paper Trading Performance (Apr 11, 2026)

**Portfolio:** $5,683 / $11,000 start = **-48.3%** across 22 passports. 1,792 closed trades.

| Passport | Equity | Trades | WR | Status |
|----------|--------|--------|----|--------|
| 🟢 PressureReader | $626 | 55 | 47% | **ONLY PROFITABLE** |
| RSIContrarian | $493 | 28 | 25% | Near breakeven |
| BBMeanRev | $473 | 63 | 40% | Near breakeven |
| BollingerBreakout | $465 | 20 | 30% | Slightly down |
| Pumpradar OG | $456 | 191 | 41% | Moderate loss |
| MACDDivergence | $452 | 41 | 32% | Moderate loss |
| BreakoutVol | $441 | 35 | 37% | Moderate loss |
| BalancedSelective | $390 | 87 | 38% | -22% |
| OG Seasonal | $378 | 145 | 40% | -24% |
| Momentum | $272 | 96 | 31% | -46% |
| Dynamic | $257 | 71 | 24% | -49% |
| OBV Trend | $208 | 72 | 26% | -58% |
| TrendConfirm | $190 | 80 | 26% | -62% |
| DualMA | $167 | 92 | 21% | -67% |
| Donchian | $167 | 65 | 20% | -67% |
| TrendMomentum | $111 | 96 | 25% | -78% |
| MinimalEdge | $102 | 99 | 20% | -80% |
| PureTrend | $82 | 101 | 16% | -84% |
| VolumeKing | $76 | 158 | 41% | -85% |
| HiddenGem | -$38 | 97 | 29% | **NEGATIVE EQUITY** |
| Sniper | -$85 | 98 | 27% | **NEGATIVE EQUITY** |

### Key Insights from Live Trading

**1. Backtest ≠ Live — The Old Champions Failed**
HiddenGem (+25.9% backtest) → -107% live. Sniper (+26.0% backtest) → -117% live. VolumeKing (+9.1% backtest) → -85% live. These were the "proven profitable" passports from Session 7. The 180d backtests were likely overfit to specific market conditions and pair selection (meme coin volatility as noted in Session 9).

**2. PressureReader is the Real Winner**
Only passport in green ($626, +25%). Uses `pressure` indicator (buy/sell volume ratio) with `candle_direction` confirmation — a unique thesis not shared by any other passport. 47% WR with +2.3% avg per trade suggests genuine edge.

**3. Mean-Reversion > Trend-Following in Current Market**
Top 4 passports (PressureReader, RSIContrarian, BBMeanRev, BollingerBreakout) all have mean-reversion or pressure-based thesis. Bottom 7 (PureTrend, MinimalEdge, TrendMomentum, DualMA, Donchian, OBV, TrendConfirm) are all trend-following → confirms current market is choppy/ranging.

**4. Win Rate Correlates Strongly with Profitability**
PressureReader 47% WR → profitable. PureTrend 16% WR → -84%. Any passport with WR < 30% is hemorrhaging money.

**5. High Trade Count + Low WR = Fast Death**
VolumeKing: 158 trades × 41% WR still loses 85% — too many mediocre entries. PureTrend: 101 trades × 16% WR = rapid destruction.

### EMA Crossover Drawdown Analysis (Research Pipeline)

All 4 EMA crossover candidates tested so far fail Stage 1 with >50% drawdown (51.6-51.8%). Root cause:
- EMA crossover uses only 2 indicators (ema_trend=2.0, volume_spike=1.0)
- Easy to reach high confidence (max 100%) → takes many positions
- No regime filter → fires during ranging/choppy markets too
- 100+ trades per symbol × 15 symbols × many losers = catastrophic drawdown
- **Not a bug** — the drawdown gate is correctly filtering a bad strategy
- Fix option: add regime gating (only trade during TREND_UP/TREND_DOWN regime) in research pipeline

### Recommendation: Urgent Passport Triage

Based on live performance, immediate actions needed:
1. **Disable passports with equity <$150** (PureTrend, MinimalEdge, TrendMomentum, VolumeKing, HiddenGem, Sniper) — they're hemorrhaging the portfolio
2. **Study PressureReader** — understand why it works, generate more pressure-based variants in research
3. **Tune BBMeanRev + RSIContrarian** — near breakeven, may become profitable with tighter entries
4. **Add regime gating to research** — EMA crossover fails because it doesn't respect market regime

---

## Session 11b: Research Phase 4 Complete + Day 1 Root Cause Analysis

### Phase 4 Research Results (First Successful Full Pipeline Run!)

**Pipeline:** 107 generated → 49 Stage 1 → **3 Stage 2 survivors** (first time EVER!)

KlineCache made this possible: 41s prefetch, 0 API crashes, ~2h total runtime vs previous 10-22h with 56% crash rate.

**Stage 2 Survivors:**

| Candidate | Sharpe | Median Return | Key Parameters |
|-----------|--------|---------------|----------------|
| rsi_momentum (conf=65, RSI=10, vol=1.5) | 1.96 | +7.3% | RSI period 10, high selectivity |
| bollinger_breakout (BB=15, std=1.5, conf=50, vol=1.5) | 2.70 | +2.1% | Tight BB, low threshold |
| bollinger_breakout (BB=15, std=1.5, conf=55, vol=1.5) | 1.22 | +1.2% | Same BB, slightly higher conf |

**Key Patterns:**
- RSI momentum (conf=65) is the BEST performer: +7.3% median return with Sharpe 1.96
- Bollinger breakout works with tight bands (1.5 std vs default 2.0) — captures smaller mean-reversion moves
- Higher confidence → fewer trades → better quality (conf=65 > conf=50)
- All survivors use 2-3 focused indicators — selectivity principle holds
- 46/49 Stage 2 failures = "Single fold is not positive" → most strategies don't survive walk-forward

**Stage 2 Filter Issue:** Only 1 regime fold available (180d is treated as single window). Need longer history or different fold strategy to properly test regime robustness.

### Day 1 Disaster: Complete Root Cause Analysis

**Date:** Apr 7, 2026 | **Damage:** -$6,496 (59% of $11,000) | **570 trades, 549 SL / 21 TP, WR=9%**

**Root Cause: Massive SHORT bias during BTC Uptrend**

| Passport | SL | TP | WR | LONG | SHORT | PnL |
|----------|----|----|-----|------|-------|-----|
| VolumeKing | 58 | 1 | 2% | 9 | 50 | -$803 |
| Sniper | 54 | 0 | 0% | 4 | 50 | -$714 |
| HiddenGem | 51 | 0 | 0% | 5 | 46 | -$639 |
| PureTrend | 32 | 0 | 0% | 8 | 24 | -$483 |
| TrendMomentum | 33 | 0 | 0% | 6 | 27 | -$482 |
| MinimalEdge | 30 | 0 | 0% | 7 | 23 | -$462 |
| DualMA | 30 | 0 | 0% | 6 | 24 | -$460 |
| Donchian | 25 | 0 | 0% | 2 | 23 | -$434 |
| TrendConfirm | 23 | 0 | 0% | 1 | 22 | -$355 |
| OBV Trend | 22 | 0 | 0% | 1 | 21 | -$331 |

**Three compounding failures:**
1. **BTC_TREND_WEIGHTS Uptrend:0.5 bug** — max confidence = 50 < threshold 54 → NO signals during uptrend. But this was the WRONG direction for the fix: it meant trend-following passports had their LONG signals suppressed while SHORT signals (from other indicators) still fired at full weight.
2. **No Counter-Trend Penalty** — CTP wasn't deployed until Apr 10. Without it, a SHORT signal during BTC Uptrend gets full confidence credit.
3. **No regime-aware gating** — 4-regime detector wasn't deployed until Apr 9. All passports fired in all conditions.

**Timing analysis:** 21:00-22:00 UTC saw 265 trades (mostly SL hits) — cascading liquidation wave as crypto market pumped.

**What changed since Day 1:**
- Apr 8: ATR fix + direction_bias → WR jumped to 42%
- Apr 9: 4-regime detector → PnL=$+1,360 (best day)
- Apr 10: CTP deployed → gradual improvement
- **Total recovery since Day 1: +$2,263 (+65% from bottom)**

### PressureReader Deep Dive — Why It Works

PressureReader is the ONLY passport consistently profitable live. Profile:

- **78 trades, ALL LONG** (direction_bias = LONG_ONLY)
- **WR=44%**, PnL=+$59 (was higher before Day 1 loss of -$96)
- **Avg confidence: 70%** → highly selective
- **TP cascade working:** 34 TP1 → 21 TP2 → 14 TP3 (40% cascade rate!)
- **20 breakeven SLs** — TP1 hit → SL moved to entry → protected from reversal
- **Top symbols:** AERO (+$45), AIA (+$25), BR (+$18), AIOT (+$18) — meme/altcoins

**Why PressureReader works and others don't:**
1. **LONG_ONLY bias** — avoided the Day 1 SHORT massacre entirely
2. **Pressure indicator** — buy/sell volume ratio is a direct measure of demand vs supply (fundamental)
3. **Candle direction confirmation** — ensures price action confirms the pressure signal
4. **Only 2 indicators** → clean confidence signal, no dilution from NEUTRAL votes
5. **No BTC trend dependency** — pressure indicator doesn't care about BTC direction

**Comparison:**
| Metric | PressureReader | PureTrend | Sniper |
|--------|---------------|-----------|--------|
| Trades | 78 | 131 | 107 |
| WR | 44% | 18% | 30% |
| PnL | +$59 | -$434 | -$538 |

### Implications for Strategy Development

1. **Direction bias matters enormously** — LONG_ONLY avoided catastrophic loss. Future passports should consider directional constraints per regime.
2. **Pressure (buy/sell volume ratio) is underexplored** — no research family generates pressure-based variants yet. This is our most profitable indicator.
3. **TP cascade is working as designed** — 40% of PressureReader's TP1 hits cascade to TP3. The 70/20/10 split is effective.
4. **RSI momentum + Bollinger breakout** passed Stage 2 — these should be promoted to paper trading.
5. **All trend-following passports failed Day 1** — they need regime gating to avoid firing counter-trend.

---

## Session 11c: Research Upgrade Deployed

### Changes Made
1. **Promoted 3 Stage 2 survivors** to paper trading: RSIMomentumV2, BollingerBreakoutV2, BollingerBreakoutV3
2. **Added 2 pressure LONG_ONLY families**: pressure_flow_long, pressure_momentum_long (inspired by PressureReader)
3. **Fixed Stage 2 fold strategy**: train=90d, test=45d, slide=45d (was 120/60/30)
   - 270d data → 4 folds (was 1 fold for 180d)
   - Now requires 3 of 4 folds positive → much more robust validation
4. **CLI default changed**: `--days 270` (was 180)

### Expected Impact
- Research pipeline should produce more robust survivors (multi-fold validation)
- Pressure LONG_ONLY families should discover PressureReader-like strategies
- 3 new passports add diversity to the live portfolio (RSI momentum + BB breakout thesis)
- Total passports: 25 (was 22)

---

## Session 11d: Deploy + System Status Snapshot (Apr 12)

### Deployment
- **VPS deployed**: `fcf0c82` — all 6 commits (promote 3 passports, pressure families, fold fix, docs)
- **25 passports loaded** including 3 new: RSIMomentumV2, BollingerBreakoutV2, BollingerBreakoutV3
- New passports start at $500 each, 0 trades

### Portfolio Status (Day 6, Apr 7–12)
| Metric | Value |
|--------|-------|
| Total Equity | $6,012 |
| Started | $11,000 (22 × $500) |
| Net PnL | -$4,988 (-45%) |
| Closed Trades | 2,448 |
| Win Rate | 19.0% |
| Open Positions | 481 |
| Profitable Passports | 3/22 |
| Current Regime | HIGH_VOL_CHOP (since Apr 9) |

### Passport Performance Tiers
**Profitable (3):**
- 🌊 PressureReader: $654 (+$154, 93 trades) — BEST performer, LONG_ONLY
- 🔃 ReversalV2: $546 (+$46, few trades)
- 💥 BreakoutVol: $503 (+$3, 50 trades)

**Near breakeven (3):**
- BBMeanRev: $497, OG: $449, MACDDivergence: $438

**Heavy losses (bottom 5):**
- PureTrend: $64 (-$436), TrendMomentum: $71 (-$429), VolumeKing: $84 (-$416)
- HiddenGem: -$10 (-$510), Sniper: -$38 (-$538)

### Key Insights
1. **Day 1 disaster dominates**: Apr 7 wiped -$6,496. Recovery since = +$2,263 (+65% from bottom). Without Day 1, most passports would be near breakeven or profitable.
2. **Counter-trend penalty (CTP) is working**: Since Session 10b deployment, massive SHORT-during-Uptrend trades stopped.
3. **PressureReader is the proven template**: LONG_ONLY + pressure indicator + minimal indicators = only consistently profitable strategy.
4. **Regime detector shows 100% HIGH_VOL_CHOP** since deployment (Apr 9) — BTC at $71K in volatile sideways.
5. **3 new passports deployed**: Need 7-30 days to collect meaningful data.

### Research Phase 5 Launched
- Running locally (MacBook, screen session)
- 270d data, 28 families, ~42+ candidates expected
- Fold strategy: train=90d, test=45d, slide=45d → 4 folds
- Key improvement: multi-fold validation should filter out overfitters

---

### §22 Phase 2: Per-Regime Parameter Tuning (Session 11f)

**What:** Populated `regime_params` for all 26 passports with thesis-driven values.

**Core thesis:** Dangerous regimes (TREND_DOWN, HIGH_VOL_CHOP) get tightened parameters. Home regimes get minimal changes. Direction-following strategies enforce DIRECTION_BIAS.

**Key parameters per dangerous regime:**
- CONFIDENCE_THRESHOLD: baseline + 4 (higher conviction required)
- RISK_PER_TRADE_PCT: 0.3% (down from 0.5%, 40% risk reduction)
- MAX_OPEN_POSITIONS_PER_PASSPORT: capped at 15 (TREND_DOWN) or 10 (HIGH_VOL_CHOP)
- DIRECTION_BIAS: LONG_ONLY in TREND_UP, SHORT_ONLY in TREND_DOWN (directional strategies only)

**What this means for live trading:**
1. In bull markets: trend-followers only go LONG (no counter-trend shorts)
2. In bear markets: 40% less risk per trade, fewer positions, higher confidence bar
3. In choppy markets: mean-reversion fires only on high-conviction setups
4. In compression: standard behavior (signals are clean)

**Expected impact:** Fewer losing trades in adverse regimes, same profitable trades in favorable regimes. Net positive Sharpe ratio improvement.

**Validation:** 118 parametrized tests ensure design rules are enforced (test_regime_params_values.py). 104 schema tests validate JSON structure (test_regime_gating_integration.py). 50 enforcement tests ensure all dangerous-regime params exist (TestDangerousRegimeParamsMustExist).

### §22b Phase 2 Backtest Validation (Session 11f continued)

**Method:** 90-day backtest, 5 meme coin pairs, applied regime overlay uniformly to measure isolated effect of each regime's parameter changes.

#### TREND_DOWN overlay (SHORT_ONLY + conf+4, risk 0.3%, max_pos 15)

| Passport | Baseline | With Overlay | **Δ Return** | Baseline DD | Overlay DD | **Δ DD** |
|---|---|---|---|---|---|---|
| **Momentum** | -11.8% | **+7.4%** | **+19.2pp** 🔥 | 27.9% | 7.0% | **-20.9pp** |
| **DualMA** | -6.4% | **+8.5%** | **+15.0pp** 🔥 | 32.0% | 14.2% | **-17.8pp** |
| **HiddenGem** | -9.0% | **+4.6%** | **+13.6pp** 🔥 | 25.6% | 11.6% | **-14.0pp** |

Win rate: Momentum 36→47%, DualMA 34→39%, HiddenGem 30→38%.

**Root cause:** DIRECTION_BIAS = SHORT_ONLY prevents trend-followers from going LONG during BTC downtrend. This eliminates the majority of losing trades (counter-trend LONGs in bearish market). Combined with reduced risk sizing, the result is dramatically better risk-adjusted returns.

#### HIGH_VOL_CHOP overlay (conf+4, risk 0.3%, max_pos 10)

| Passport | Baseline | With Overlay | Δ Return | Baseline DD | Overlay DD | **Δ DD** |
|---|---|---|---|---|---|---|
| **BBMeanRev** | -0.4% | -0.1% | +0.3% | 15.4% | 9.5% | **-5.9pp** |
| **BalancedSelective** | 4.3% | 2.9% | -1.4% | 19.4% | 12.1% | **-7.3pp** |

**Root cause:** Position sizing reduction works — DD cut 38-39%. Slight return reduction is expected tradeoff (less risk = less upside). Trade count and win rate identical — params only reduce exposure, not signal quality.

#### Key Conclusions

1. **DIRECTION_BIAS is the killer feature** — single biggest improvement. Preventing counter-trend trades during bear markets flipped 3 passports from negative to positive returns.
2. **Risk reduction in choppy markets works as designed** — protects capital without killing signals.
3. **Phase 2 thesis validated:** thesis-driven params (not curve-fit) produce measurable improvement.

⚠️ **Caveat:** Test applies overlay uniformly across all 90 days. In live trading, overlay only activates during detected regime periods. Real impact is proportional to time spent in each regime.

### §22c Logging Fix (Session 11f)

**Bug:** `logger.info("applying regime_params...")` in `passport_runner.py` was silently dropped — no `logging.basicConfig()` was configured in `main_multi.py`. All Python `logging` module output was invisible in journalctl.

**Fix:** Added `logging.basicConfig(level=logging.INFO, format=..., stream=sys.stdout)` at top of `bot/main_multi.py`. Commit `d3f65bb`.

**Impact:** regime_params application, warnings, and errors now visible in VPS logs via `journalctl -u cryptopass.service`.

### §22d Phase 5 Research Pipeline Results (Session 11f)

**Run:** `exp-2026-04-12-093633` — 117 generated → 31 Stage 1 → **17 Stage 2 survivors** (562.6 min, MacBook local).

**Command:** `uv run python run_research.py --all --max-per-family 5 --days 180`

**Note:** This was the first full research run after 12 bug fixes (Session 9 calculation audit). All PnL formulas, leverage, fees, and TP cascade math are now correct. Previous research runs (exp-2026-04-07, exp-2026-04-09) used buggy math and their results are not comparable.

#### 17 Stage 2 Survivors (ranked by Sharpe)

| Rank | Family | Conf | Sharpe | PF | Med Ret | +Folds | Indicators |
|---|---|---|---|---|---|---|---|
| 1 | hidden_gem_variant | 55 | **2.06** | 1.025 | +2.4% | 3/4 | EMA + BB + Volume |
| 2 | hidden_gem_variant | 60 | **2.06** | 1.025 | +2.4% | 3/4 | EMA + BB + Volume |
| 3 | hidden_gem_variant | 65 | **2.02** | 1.025 | +2.4% | 3/4 | EMA + BB + Volume |
| 4 | hidden_gem_variant | 70 | 1.93 | 1.098 | +3.5% | 3/4 | EMA + BB + Volume |
| 5 | rsi_momentum | 50 | 1.75 | 1.002 | +1.1% | 2/4 | EMA + RSI + RSI Div |
| 6 | rsi_momentum | 55 | 1.75 | 0.973 | +0.0% | 2/4 | EMA + RSI + RSI Div |
| 7 | hidden_gem_variant | 55 | 1.67 | 1.055 | +3.9% | 3/4 | EMA + BB + Volume (vol=2.0) |
| 8 | rsi_momentum | 65 | 1.44 | 1.134 | +0.9% | 2/4 | EMA + RSI + RSI Div |
| 9 | rsi_momentum | 50 | 1.30 | 1.005 | +1.4% | 2/4 | EMA + RSI + RSI Div (vol=2.0) |
| 10 | rsi_momentum | 60 | 1.29 | 1.027 | +1.9% | 3/4 | EMA + RSI + RSI Div |
| 11 | rsi_bb_reversal | 60 | 1.12 | **1.195** | +1.2% | **4/4** | RSI + BB + Volume |
| 12 | rsi_bb_reversal | 55 | 1.12 | **1.195** | +1.2% | **4/4** | RSI + BB + Volume |
| 13 | rsi_bb_reversal | 65 | 0.89 | **1.368** | +1.8% | **4/4** | RSI + BB + Volume |
| 14 | pressure_flow_short | 65 | 0.62 | **1.545** | +0.9% | 2/4 | EMA + Pressure + Candle (SHORT_ONLY) |
| 15 | pressure_flow_short | 65 | 0.62 | **1.545** | +0.9% | 2/4 | EMA + Pressure + Candle (SHORT_ONLY) |
| 16 | pressure_flow_short | 60 | 0.60 | **1.439** | +0.7% | 2/4 | EMA + Pressure + Candle (SHORT_ONLY) |
| 17 | pressure_flow_short | 60 | 0.60 | **1.439** | +0.7% | 2/4 | EMA + Pressure + Candle (SHORT_ONLY) |

#### Family Summary

| Family | Variants | Best Sharpe | Avg Sharpe | Avg PF | Avg Med Ret | Assessment |
|---|---|---|---|---|---|---|
| **hidden_gem_variant** | 5 | **2.06** | 1.95 | 1.045 | +2.9% | 🟢 Best risk-adj, but PF barely >1. BB(18)+EMA(8/45)+Vol |
| **rsi_momentum** | 5 | 1.75 | 1.51 | 1.028 | +1.1% | 🟡 High Sharpe but low PF. Only 2/4 folds positive |
| **rsi_bb_reversal** | 3 | 1.12 | 1.04 | **1.253** | +1.4% | 🟢 **All 4 folds positive**. Best consistency. BB(15,1.5σ)+RSI(10) |
| **pressure_flow_short** | 4 | 0.62 | 0.61 | **1.492** | +0.8% | 🟡 Highest PF but SHORT_ONLY, low Sharpe. Niche downtrend strategy |

#### Key Insights

1. **Selectivity Principle confirmed again** — all 17 survivors use exactly 3 active indicators. Zero survivors use 4+ indicators.
2. **hidden_gem_variant dominates Sharpe** but has marginal PF (1.02-1.10). High Sharpe comes from low volatility rather than large returns.
3. **rsi_bb_reversal is the most consistent** — only family with ALL 4 regime folds positive. Lower Sharpe but higher PF (1.2-1.4). This is the mean-reversion counterpart we've been looking for.
4. **pressure_flow_short validates PressureReader thesis** — SHORT_ONLY pressure-based strategies work. PF 1.4-1.5 is excellent. Pairs well with LONG_ONLY trend-followers.
5. **Stage 3 (Monte Carlo) and Stage 4 (orthogonality) were NOT run** — these survivors need robustness testing before promotion to paper trading.

#### Next Steps

- Run Stage 3+4 on the 17 survivors to filter for robustness and portfolio orthogonality
- Top candidates for promotion: rsi_bb_reversal (consistency), hidden_gem_variant conf=70 (highest PF in family), pressure_flow_short conf=65 (SHORT_ONLY niche)
- Consider running a fresh pipeline now that regime_params and all 12 bug fixes are deployed
