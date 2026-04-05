# Pumpradar — Findings, Failures & Learnings

> Living document. Updated after every iteration cycle.
> Purpose: avoid repeating mistakes, build on proven insights, explore new lineages with context.
> Last updated: 2026-04-05 (Session 1–3 consolidated)

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

### ✅ Selective 3-indicator passports
- HiddenGem (EMA+BB+Vol): +25.9% at 180d ✅
- Sniper (BB+Vol+Candle): +26.0% at 180d ✅
- VolumeKing (Vol 2.5x+Candle): +9.1% at 180d ✅
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

### ✅ BBMeanRev (new candidate)
- 90d Jan–Apr 2026: +8.0%, PF=1.28, WR=45.2%, 157 trades
- BB+RSI mean reversion, 2 active indicators
- Best performer in the choppy Q1-2026 window

### ✅ RSIContrarian (new candidate)
- 90d Jan–Apr 2026: +4.2%, PF=1.24, WR=40.9%, 88 trades
- RSI+RSI_divergence+BB, 3 active indicators
- Selective, low trade count — quality over quantity

---

## 7. Backtesting Methodology Learnings

### Regime bias is real
| Window | OG Return | Why |
|---|---|---|
| Live 3d (Apr 2026) | +5.2% | Very short, possibly favorable micro-regime |
| 30d backtest | +11.3% | Captured bullish window |
| 30d optimized (vol=2.0) | +49.1% | Overfitted to this specific window |
| 180d backtest | -13.1% | Includes Oct–Jan bear market |

> **Rule:** Never make deployment decisions on <90d backtests. Always validate across at least 2 regime types.

### Test pairs matter
- Top-volume Binance futures pairs (0GUSDT, 1000BONKUSDT) in Jan–Apr 2026 are meme coins with noise-dominated price action
- Results on these pairs systematically understate strategy quality
- Better pairs for validation: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, AAVEUSDT, ADAUSDT

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

## 9. New Passport Candidates (90d Results)

> 90d window Jan–Apr 2026, 10 pairs (top Binance volume), equal-weight avg.
> Choppy/bear period — results conservative. Re-validate on better pairs and longer window.

| Rank | Passport | Strategy | Return | PF | WR | Trades | Assessment |
|---|---|---|---|---|---|---|---|
| 1 | 🔄 BBMeanRev v0.1 | BB+RSI mean reversion | **+8.0%** | 1.28 | 45.2% | 157 | ✅ **Deploy to paper** |
| 2 | 🔮 RSIContrarian v0.1 | RSI extremes+divergence+BB | **+4.2%** | 1.24 | 40.9% | 88 | ✅ **Deploy to paper** |
| 3 | 🚄 TrendMomentum v0.1 | EMA+RSI+MACD | +1.5% | 1.02 | 34.1% | 302 | 🟡 Monitor |
| 4 | 🎯 MinimalEdge v0.1 | EMA+Vol | +0.3% | 1.00 | 33.2% | 319 | 🟡 No clear edge |
| 5 | 📈 PureTrend v0.1 | EMA-only | +0.2% | 1.00 | 33.2% | 319 | 🟡 Too simple |
| 6 | 📊 MACDDivergence v0.1 | MACD+RSI_div | -1.3% | 0.96 | 32.9% | 164 | 🔴 Skip |
| 7 | ⚖️ BalancedSelective v0.1 | EMA+BB+RSI | -2.2% | 0.97 | 40.3% | 385 | 🔴 Too many trades |
| 8 | ✅ TrendConfirm v0.1 | EMA+MACD+Vol | -3.7% | 0.95 | 32.3% | 310 | 🔴 Skip |
| 9 | 💥 BreakoutVol v0.1 | BB+Vol+Candle | -10.8% | 0.85 | 36.0% | 403 | 🔴 Overtrades |
| 10 | 🌊 PressureReader v0.1 | Pressure+Candle+EMA | -14.9% | 0.78 | 30.8% | 338 | 🔴 Skip |

> Reference passports (v0.3) also negative in this window due to choppy regime — not a regression.

---

## 10. Open Code Issues (Not Yet Fixed)

### HIGH PRIORITY

**1. Trailing stop formula (position_manager.py L181–193)**
```python
# CURRENT (WRONG):
trail_dist = abs(sig.entry_price - sig.sl)  # fixed, too tight

# SHOULD BE:
trail_dist = current_atr * ATR_TRAIL_MULTIPLIER  # adaptive
# Also: only trail after TP2, not TP1
```

**2. RSI threshold not per-passport overridable (config.py L17–18)**
```python
RSI_LONG_THRESHOLD = 50   # hardcoded global
RSI_SHORT_THRESHOLD = 50  # hardcoded global
# Needs: setattr support in passport config_overrides
```
This blocks Reversal strategy from being usable as a true mean-reversion engine.

**3. Reversal strategy needs code rewrite before re-enabling**
- RSI logic needs threshold inversion (30/70 instead of 50/50)
- Or: replace with a dedicated mean-reversion indicator that checks RSI<30 LONG / RSI>70 SHORT
- Currently: `enabled: false` in passport JSON — do not enable until fixed

### MEDIUM PRIORITY

**4. Dynamic EXIT behavior unverified**
- `USE_ATR_EXITS: true` on Dynamic passport shows identical results to Momentum (same metrics)
- Need to trace through whether ATR exits are actually being called in backtester
- May need a dedicated test fixture with wide ATR to trigger the different exit logic

**5. BTC Uptrend confidence multiplier (scorer.py)**
- `btc_weight = 0.5` in Uptrend halves all confidence scores
- This means strategies often don't fire during bull markets
- Consider making this tunable per-passport or removing the Uptrend penalty

**6. Regime classification used in research engine may not match live bot**
- `bot/research/regime.py` classifies 4 regimes (Bull/Bear/Sideways/HighVol)
- Live bot uses `determine_btc_trend_at()` in backtester which only does Up/Down/Sideways
- These two need to be reconciled before deploying research-engine-selected passports

### LOW PRIORITY

**7. `reversal.json` has 9 INDICATOR_WEIGHTS keys (not 8)**
- Extra key `reversal_mode` inside INDICATOR_WEIGHTS
- Pre-existing, not causing failures (quarantined passport)
- Clean up when Reversal is properly rewritten

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
- 42 commits, 206/206 tests passing

---

## 12. What's Next

### Immediate (merge + paper trading)

1. **Review and merge PR #1** — 42 commits of foundational work. Can review at:
   https://github.com/vforvaick/trade-radar/pull/1

2. **Deploy to VPS for paper trading:**
   ```bash
   # On fight-tres:
   git pull origin fix/strategy-parameter-tuning  # or master after merge
   systemctl restart pumpradar.service
   ```
   - All 17 passports will auto-load (7 original + 10 new)
   - Monitor via Telegram `/summary`
   - Recommend **disabling** high-loss passports: Reversal (already disabled), Momentum, Dynamic initially

3. **Run BBMeanRev and RSIContrarian on better pairs** — re-validate on BTC/ETH/SOL/AAVE:
   ```bash
   uv run python scripts/run_new_passport_backtest.py --days 90 --pairs 10 \
     --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT AAVEUSDT ADAUSDT MATICUSDT DOTUSDT LINKUSDT AVAXUSDT
   ```

### Short-term (strategy improvement)

4. **Fix trailing stop formula** — highest ROI code fix:
   ```python
   # position_manager.py L182
   trail_dist = ATR_TRAIL_MULTIPLIER * current_atr  # needs ATR in position context
   ```
   Then re-enable `USE_TRAILING_STOP: true` on Dynamic and test.

5. **Make RSI thresholds per-passport overridable** — enables true mean-reversion:
   ```python
   # config.py
   RSI_LONG_THRESHOLD = getattr(config, 'RSI_LONG_THRESHOLD', 50)
   ```
   Then create a proper `reversal_v2.json` with RSI thresholds 30/70.

6. **Weekly seasonality filter** — historical data shows +81.1% skipping Wed+Fri vs +29.6% baseline:
   ```python
   # config_overrides: "SKIP_WEEKDAYS": [2, 4]  # 0=Mon, 2=Wed, 4=Fri
   ```

7. **Run 90d backtest on quality pairs** for all 10 new passports — current results are on noisy meme coins

### Medium-term (research engine)

8. **Activate the Strategy Research Engine** (`run_research.py`):
   ```bash
   uv run python run_research.py --all --max-per-family 5 --pairs 10 --days 90
   ```
   This runs all 25 families through the 4-stage pipeline and generates ranked candidates.

9. **Paper trading promotion pipeline:**
   - Generated passport → Stage 1-4 validation → `paper_live` status → 30d paper trading → check PromotionPolicy 7 gates → promote to `production`

10. **Portfolio construction:**
    - Use `bot/research/pipeline.py` Stage 4 (orthogonality) to select non-correlated strategy set
    - Target: 3–5 concurrent strategies covering different regimes (trend + mean-rev + breakout)

### Long-term (new lineages to explore)

11. **Multi-timeframe confluence** — combine 15m signal quality with 4H trend direction
12. **Funding rate carry strategy** — go long when funding rate is strongly negative (shorts paying longs)
13. **Volatility regime switching** — use ATR percentile to switch between trend and mean-reversion passports
14. **Short-side optimization** — shorts historically outperform longs (65.2% vs 50.0% WR); consider a short-only passport
15. **Weekly seasonality passport** — only trade Mon/Tue/Thu based on historical +81.1% edge
16. **OI + Liquidation cluster entries** — when OI spikes and price approaches liquidation clusters = high-conviction reversal

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
