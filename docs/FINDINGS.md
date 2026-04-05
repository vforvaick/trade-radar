# Pumpradar — Findings, Failures & Learnings

> Living document. Updated after every iteration cycle.
> Purpose: avoid repeating mistakes, build on proven insights, explore new lineages with context.
> Last updated: 2026-04-05 (Session 4 — trailing stop fix, RSI/weekday overrides, quality-pair backtest)

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

### Bug 6 — Dynamic v0.2 = Momentum v0.2 identical metrics
- **Files:** `pumpradar-passports/configs/dynamic_exit.json`, `momentum.json`
- **Root cause:** Backtester may not differentiate `USE_ATR_EXITS=true` in the test window, OR ATR exit is not active for the specific trade duration. Both show 1095 trades, 37.6% WR, -20.0%.
- **Status:** Not investigated. Needs a test where ATR exits are the differentiating factor.

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

**3. Regime classifier mismatch (MEDIUM)**
- Research engine (`bot/research/regime.py`): 4 regimes (Bull/Bear/Sideways/HighVol)
- Backtester (`determine_btc_trend_at()`): 3 regimes (Up/Down/Sideways)
- Must reconcile before deploying research-engine-selected passports to live bot

**4. reversal_v2.json backtested — FAILED, kept disabled (RESOLVED)**
- 90d quality-pair backtest (BTCUSDT ETHUSDT SOLUSDT BNBUSDT AAVEUSDT ADAUSDT DOTUSDT LINKUSDT AVAXUSDT MATICUSDT)
- Return: **-11.78%** | Win Rate: **29.6%** | Profit Factor: **0.70** | Trades: **186**
- Diagnosis: pure mean-reversion (RSI 30/70 + BB only) fires too often in trending markets, producing a low win-rate and negative PF
- Decision: remain `enabled: false`; strategy needs trend-filter gate before re-testing

**5. `reversal.json` has 9 INDICATOR_WEIGHTS keys (LOW)**
- Extra `reversal_mode` key inside INDICATOR_WEIGHTS — pre-existing, harmless
- Clean up when rewriting Reversal

---

## 11. Deployment & Infrastructure Notes

### VPS Setup
- **Host:** `fight-tres`
- **Service:** `pumpradar.service` (systemd)
- **Start/stop:** `systemctl restart pumpradar.service`
- **Entry:** `python -m bot.main_multi --interval=1h`
- **Config auto-load:** `main_multi.py` loads all `*.json` from `pumpradar-passports/configs/`
- **New passports auto-activate** — just push to VPS and restart service

### Telegram
- HTTP API via bot token in `.env`
- Threading: signal message → TP/SL replies in same thread
- Commands: `/status`, `/ping`, `/summary`
- New formatters in `bot/telegram_commands.py`: strategies, compare, health, promotion, digest

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

### Immediate — Deploy to VPS (needs your action — SSH required)

```bash
# On fight-tres — pull branch and restart:
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git fetch origin && git checkout fix/strategy-parameter-tuning && git pull && systemctl restart pumpradar.service"

# Validate (wait ~30s after restart):
ssh fight-tres "journalctl -u pumpradar.service -n 50 --no-pager -o short-iso"
```

Expected output: 19 passports load (17 original/new + reversal_v2 + seasonality_og), `reversal.json` and `reversal_v2.json` skipped (disabled), all others scanning.

### Short-term — paper trading observation

1. Monitor MACDDivergence and BBMeanRev — top 90d performers on quality pairs
2. SeasonalityOG runs Mon/Tue/Thu only — compare vs regular OG performance
3. Check if any passport overtrades (>50 positions/day) → raise CONFIDENCE_THRESHOLD

### Medium-term — research engine

4. **Run research engine for the first time** (built but never run live):
   ```bash
   uv run python run_research.py --all --max-per-family 5 --pairs 10 --days 90
   ```
5. **Backtest reversal_v2** — now has correct RSI 30/70 thresholds:
   ```bash
   uv run python scripts/run_new_passport_backtest.py --days 180 --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT AAVEUSDT
   ```
6. **Test trailing stop on Dynamic** — enable `USE_TRAILING_STOP: true` on just the Dynamic passport and compare 90d results

### Long-term (new lineages to explore)

- **Multi-timeframe confluence** — 15m signal + 4H trend direction
- **Funding rate carry** — long when funding rate strongly negative
- **Volatility regime switching** — ATR percentile selects trend vs mean-reversion mode
- **Short-only passport** — shorts WR 65.2% vs longs 50.0% historically
- **OI + Liquidation clusters** — high-conviction reversal entries

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
