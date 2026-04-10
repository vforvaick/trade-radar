# Cryptopass — Strategic Roadmap

> Created: 2026-04-09 (Session 10)
> Updated: 2026-04-10 (Session 10b — BollingerBreakout promoted, post-CTP results)
> Status: Active — living document, update after each major milestone

---

## North Star (Staged)

**Original North Star (Sessions 1–9):**
> "3+ passports with >+15% return over 180d, validated across multiple market regimes"

**Endgame North Star:**
> **"Portfolio Sharpe ≥ 1.0 across all 4 market regimes, with ≥1 profitable specialist per regime"**

**Current Operational Target (Stage 1):**
> **"1 passport profitable in live paper trading within 30 days (Apr 7 → May 7)"**

### Staged Approach

| Stage | Target | Timeframe | Success Criteria |
|-------|--------|-----------|------------------|
| 🥉 **Stage 1 (NOW)** | 1 profitable passport in live paper | 30 days (→ May 7) | Return > 0%, PF > 1.0, ≥ 30 trades |
| 🥈 Stage 2 | 3 passports pass 7-gate promotion | +60 days | Full promotion criteria |
| 🥇 Stage 3 | Portfolio Sharpe ≥ 1.0 across 4 regimes | +90 days | Endgame North Star |

### Focus 3 — Stage 1 Watch List (decided Session 10b)

| # | Passport | Closed PnL (Day 2) | Post-CTP PnL (24h) | WR | PF | Role |
|---|----------|---------------------|---------------------|----|----|------|
| 🥇 | **PressureReader** | -$23 | **+$191.82** | 60.0% | **2.29** | **Alpha generator** ⭐ |
| 🥈 | **MACDDivergence** | -$15 | -$21.16 | 31.2% | 0.89 | Mean-rev baseline |
| 🥉 | **BreakoutVol** | -$34 | -$3.65 | 28.6% | 0.95 | CTP beneficiary test |
| NEW | **BollingerBreakout** | — | -$55 (4 trades) | 0% | 0.00 | Phase 4 research star |

> **Apr 10 update:** PressureReader confirmed as alpha generator — +$191 in 24h post-CTP. BreakoutVol nearly breakeven. BollingerBreakout just deployed, too early to judge (4 trades). MACDDivergence still slightly negative.

### Evaluation Checkpoints

| Date | Day | Action |
|------|-----|--------|
| Apr 14 | Day 7 | First: any green closed PnL? |
| Apr 21 | Day 14 | Mid: PF/WR trend, DD check |
| Apr 28 | Day 21 | Decision: continue or pivot? |
| May 7 | Day 30 | Final: promotion gate eval |

### Why the staged change

We have excellent infrastructure but zero validated alpha. Trying to cover 4 regimes when we haven't proven a single strategy works live is premature optimization. Prove the edge first, then expand.

### Gate Metrics (per specialist passport)

| Metric | Threshold | Why |
|--------|-----------|-----|
| 180d Return | ≥ +10% | Absolute profitability floor |
| Sharpe Ratio | ≥ 0.8 | Risk-adjusted: return/volatility |
| Max Drawdown | ≤ -20% | Capital preservation |
| Win Rate | ≥ 45% | Signal quality |
| Profit Factor | ≥ 1.3 | Edge consistency: gross profit / gross loss |
| Live Paper 30d | Required | No simulation-only promotion |
| Regime Verified | Required | Must be tested in its target regime window |

### Portfolio-Level Target

| Metric | Target | Current |
|--------|--------|---------|
| Combined Sharpe | ≥ 1.0 | Unknown — need regime-tagged backtests |
| Regime Coverage | 4/4 regimes | 2/4 (Uptrend ✅, Sideways ✅, Downtrend ❌, LowVol ❌) |
| Profitable Specialists | ≥ 4 (one per regime) | 3 proven (HiddenGem, Sniper, BBMeanRev) |
| Max Portfolio DD | ≤ -15% | Unknown — need portfolio-level backtest |

---

## Strategic Approach: Hybrid Specialist Portfolio

**Why Hybrid?**

| Approach | Pros | Cons |
|----------|------|------|
| Pure Specialists | Simple, proven, each passport optimized for one regime | Need to build specialists for every regime; can't adapt |
| Universal Adaptive | One passport for all conditions | Very hard to build; compromises everywhere; regime detection must be perfect |
| **Hybrid (chosen)** | **Specialists first, add adaptive layer later** | Slightly more complex portfolio management |

**Concrete plan:**
1. **Phase 1 (now → +30d):** Fill regime gaps with specialists. Build bear market + low-vol passports.
2. **Phase 2 (+30d → +60d):** Deploy 4-regime detector. Collect regime data. Passports tag signals with regime.
3. **Phase 3 (+60d → +90d):** First adaptive passport attempt. Uses regime detection to shift indicator weights dynamically.
4. **Phase 4 (+90d+):** Evaluate — does the adaptive beat the specialist portfolio? If yes, promote. If no, stay specialist-only.

---

## Current Portfolio Assessment

### Tier 1 — Proven Profitable (backtest + scientific basis)

| Passport | Return (180d) | Regime | Thesis | Rational? |
|----------|---------------|--------|--------|-----------|
| **HiddenGem** | +25.9% | Uptrend | EMA trend + BB squeeze + volume confirmation. 3 independent signals, selectivity principle. | ✅ Strong — trend-following with volume confirmation is textbook momentum |
| **Sniper** | +26.0% | Uptrend | BB position + volume spike + candle direction. High threshold (70%+) for extreme conviction entries. | ✅ Strong — price-action confluence at volatility extremes |
| **VolumeKing** | +9.1% | Uptrend | Volume-led with price confirmation. Binary volume filter eliminates noise trades. | ✅ Moderate — volume precedes price is a valid thesis, but WR (32%) is low |

### Tier 2 — Promising Candidates (need more data)

| Passport | Return (90d QP) | Regime | Thesis | Status |
|----------|-----------------|--------|--------|--------|
| **BBMeanRev** | +7.7% PF=1.32 | Sideways | Bollinger Band mean-reversion with Uptrend:1.0 (regime-neutral). | 🟡 Paper trading — need 30d live data |
| **MACDDivergence** | +9.1% PF=1.39 | Sideways | MACD histogram divergence signals exhaustion → reversal. | 🟡 Paper trading — need 30d live data |

### Tier 3 — Unproven / Research

All remaining 17 passports. Most are negative in backtest. Research pipeline evaluates new candidates continuously.

### Gaps

| Regime | Status | Action |
|--------|--------|--------|
| **TREND_UP** | ✅ Covered | HiddenGem, Sniper, VolumeKing |
| **SIDEWAYS / HIGH_VOL_CHOP** | ✅ Partially covered | BBMeanRev, MACDDivergence (need live validation) |
| **TREND_DOWN** | ❌ No strategy | Priority gap — see Research Priorities §1 |
| **LOW_VOL_COMPRESSION** | ❌ Unknown | Untested regime — see Research Priorities §2 |

---

## Research Priorities

### Priority 1: Bear Market Specialist

**Goal:** Find a passport that profits when BTC is in sustained downtrend.

**Why it's hard:** Most crypto strategies are inherently long-biased. Short-selling in a downtrend requires:
- Accurate identification of bear market (not just a dip)
- Timing shorts during bounces, not at the bottom
- Managing liquidation risk (shorts have unlimited loss potential)

**Research approaches (ordered by effort):**
1. **Short-bias passport** — Set `DIRECTION_BIAS: "short"` on existing HiddenGem-style indicators. Lowest effort. Test hypothesis: if EMA+BB+Vol works for longs in uptrend, does the mirror work for shorts in downtrend?
2. **RSI Overbought Reversal** — RSI > 70 + BB upper band + volume spike → short entry. Mean-reversion thesis in overextended bear rallies.
3. **Funding Rate Carry** — When perpetual funding is deeply negative (longs pay shorts), this often signals exhaustion and reversal. Requires funding rate API endpoint.
4. **OI Liquidation Clusters** — High open interest + price approaching major support/resistance → expect liquidation cascade. Advanced; requires OI data feed.

**Validation criteria:** Same gate metrics, but tested specifically on TREND_DOWN regime windows (e.g., Jun-Sep 2022, May-Jun 2024, Jan 2025 drawdowns).

### Priority 2: Low-Volatility Compression Strategy

**Goal:** Profit during quiet, range-bound markets with declining volatility (Bollinger Band squeeze).

**Thesis:** Low-vol compression precedes breakouts (the "spring effect"). A strategy that detects BB squeeze and enters on the first breakout candle should capture the expansion move.

**Research approaches:**
1. **BB Squeeze Breakout** — BB width < 20th percentile + candle closes outside band = entry.
2. **Donchian in compression** — Donchian breakout (20-period high/low) filtered by low ATR environment.

### Priority 3: Strategy Robustness Validation

**Goal:** Ensure existing profitable strategies aren't curve-fitted.

**Method:** Monte Carlo parameter perturbation (Stage 3 of research pipeline):
- Perturb each parameter ±20% randomly, 50 iterations
- If >70% of perturbations remain profitable, the strategy is robust
- If <30%, it's curve-fitted to specific parameters

**Status:** Research pipeline Stage 3 built but never completed a full run on live data (Binance API timeouts killed first attempt).

---

## Architecture Roadmap

### 1. 4-Regime Upgrade (Next Implementation)

**Spec:** `docs/superpowers/specs/2026-04-09-4-regime-upgrade-design.md`

Replace the simplistic EMA 9/21 3-regime detector with ADX-based 4-regime system:
- TREND_UP, TREND_DOWN, HIGH_VOL_CHOP, LOW_VOL_COMPRESSION
- Multi-timeframe: 4H primary + 1H confirmation
- Per-passport BTC_TREND_WEIGHTS with 4 keys
- RegimeLogger for data collection + Telegram daily digest
- Cache TTL = 3600s to avoid redundant API calls

**Impact:** Enables regime-aware strategy selection. Passports can opt in/out of regimes. Portfolio allocation becomes regime-conditional.

### 2. ATR-Based Trailing Stop Fix

**Current state:** `USE_TRAILING_STOP = false` everywhere because the formula is broken (fixed trail distance too tight for 1H crypto).

**Fix:** `trail_dist = ATR(14) × multiplier` where multiplier is per-passport configurable (default 2.5).

**Impact:** Unlocks dynamic exits that adapt to volatility. High value for momentum passports (HiddenGem, Sniper) that currently use fixed TP1/TP2/TP3 cascade.

### 3. Portfolio-Level Risk Manager

**Current state:** Each passport is isolated. 22 passports can all fire on the same symbol simultaneously → 22 × 3% = 66% equity exposed.

**Fix:** Global cap: max N passports can hold the same symbol. When exceeded, lowest-confidence position is rejected.

**Impact:** Protects against correlated losses. Critical for when portfolio has 10+ active passports.

### 4. Sharpe Ratio Integration

**Current state:** Backtester returns `return_pct`, `win_rate`, `profit_factor`, `max_dd`. No Sharpe.

**Fix:** Add `sharpe_ratio` to backtest summary. Formula: `(mean_daily_return - risk_free) / std_daily_return × sqrt(365)`. Risk-free rate = 0 for crypto.

**Impact:** Enables North Star measurement. Research pipeline Stage 1 already computes Sharpe; backtester needs to surface it.

---

## Promotion Pipeline

```
GENERATED ──Stage 1──► BACKTESTED ──Stage 2──► REGIME_VALIDATED ──Stage 3──► ROBUST
     │                                                                        │
     │                                                              Monte Carlo check
     │                                                                        │
     ▼                                                                        ▼
  (discard)                                                            PAPER_LIVE
                                                                          │
                                                                   30d + 7 gates
                                                                          │
                                                                          ▼
                                                                    CANDIDATE
                                                                          │
                                                                    human review
                                                                          │
                                                                          ▼
                                                                    PRODUCTION
                                                                          │
                                                                     monthly review
                                                                          │
                                                                    ┌─────┴─────┐
                                                                 (keep)     RETIRED
```

**Current status:**
- PAPER_LIVE: 22 passports (all paper trading since 2026-04-07)
- CANDIDATE: 0 (none have completed 30d live yet)
- PRODUCTION: 0 (no real money deployed)

**Target:** First PRODUCTION promotion after 2026-05-07 (30d paper trade).

---

## Risk Framework

### What Could Go Wrong

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| All strategies curve-fitted to 2025 data | Medium | Fatal — no real edge | Monte Carlo Stage 3 + out-of-sample testing on 2024 data |
| Binance API changes break data fetching | Low | Blocks all trading | Version-pin API, add fallback data source |
| BTC flash crash wipes all positions | Low | -15% to -30% equity | Portfolio risk manager + max drawdown circuit breaker |
| Regime detector misclassifies → wrong strategy fires | Medium | Losses in wrong regime | Passive mode first (collect data, don't auto-filter) |
| VPS outage during high-vol period | Low-Med | Missed exits, SL not triggered | Health monitoring + Telegram alerts + Binance server-side SL |

### Capital Allocation Plan

**Phase 1 — Paper (now):**
- $500 simulated equity split across all 22 passports
- No real money at risk
- Pure learning and validation

**Phase 2 — Pilot ($100 real):**
- First promoted passport gets $100 real allocation
- All others remain paper
- Minimum 30d before increasing

**Phase 3 — Scale ($500 real):**
- 3+ promoted passports
- $500 total real allocation
- Per-passport sizing based on Sharpe ratio: higher Sharpe = larger allocation

**Phase 4 — Growth:**
- Portfolio Sharpe ≥ 1.0 confirmed across 90d
- Scale to $2000+
- Add second exchange (Bybit) for redundancy

---

## Session History & Milestones

| Session | Date | Key Achievement |
|---------|------|-----------------|
| 1-4 | Mar 31 → Apr 4 | Initial 7 passports, backtester, v0.1→v0.2 optimization (failed) |
| 5 | Apr 5 | New strategy families (DualMA, Donchian, OBV), research engine skeleton |
| 6 | Apr 5 | Research pipeline 4 stages, regime walk-forward |
| 7 | Apr 6 | Cryptopass overhaul: 22 passports, $500 fresh start, BTC Uptrend 0.5 bug fix |
| 8 | Apr 7 | Systematic calc audit: 12 bugs fixed, VPS deployed, 289 tests |
| 9 | Apr 8 | ATR fix, direction_bias, Phase 4 research launched |
| **10** | **Apr 9** | **4-regime design spec, v0.1→v0.2 failure analysis, North Star reframe, strategic roadmap** |

---

## Metrics We Track

| Metric | Where | How Often |
|--------|-------|-----------|
| Per-passport PnL | `state.db` → trade_log | Every trade |
| Equity curve | `state.db` → equity_snapshots | Hourly |
| Backtest results | `research_experiments.db` | Per research run |
| Regime classification | TBD (after 4-regime upgrade) | Every scan cycle |
| Portfolio Sharpe | TBD (needs implementation) | Weekly rollup |
| VPS health | `systemctl status` + Telegram | Continuous |

---

## Open Questions

1. **Should we add a second timeframe (15m) for entry timing?** Current 1H entries have wide SL due to candle size. A 15m confirmation could tighten entries. Trade-off: more complexity + API calls.

2. **Is $500 paper enough to be statistically meaningful?** With 3% risk per trade and 4× leverage, each trade risks $15 of simulated equity. Need ≥100 trades per passport for statistical significance → ~4-6 months at current signal frequency.

3. **When should we consider real money?** Proposed: after at least 1 passport passes all 7 promotion gates + 30d live paper + human review.

4. **Should we add non-BTC regime detection?** ETH, SOL have their own cycles. Currently all passports use BTC trend as the macro filter. ETH-specific regime detection could unlock altcoin-specific strategies.

---

*This document is the strategic source of truth. Update after every major milestone. Tactical details go in `docs/whats-next.md`.*
