# Cryptopass — What's Next

> Updated: 2026-04-09 (Session 10b — Counter-trend penalty, portfolio triage, Phase 4 results)
> Branch: `master` — 339 tests passing, VPS deployed with CTP + 9 passports disabled
> Strategic direction: see `docs/STRATEGIC_ROADMAP.md` for North Star and long-term vision

---

## 🟢 Right Now (Completed This Session)

### ✅ Counter-Trend Penalty (COUNTER_TREND_PENALTY)
**The key architectural fix.** Scorer now penalizes signals opposing BTC trend direction.
- SHORT during TREND_UP → confidence × 0.5 (effectively blocked for trend-followers)
- Mean-reversion passports override to 1.0 (trade freely counter-trend)
- Applied to both `scorer.py` and `extended_scorer.py`
- Spec: `docs/superpowers/specs/2026-04-09-counter-trend-penalty-design.md`

### ✅ Portfolio Triage — 9 Passports Disabled
All PF < 0.30 disabled: HiddenGem, Sniper, VolumeKing, DualMA, MinimalEdge, TrendMomentum, Donchian, OBV Trend, PureTrend. 12 active passports remain.

### ✅ 4-Regime Upgrade
ADX+volatility 4-regime classifier replaces old EMA 9/21 system. Deployed to VPS.

### Phase 4 Research — Completed but Partial
107 generated → 24 Stage 1 → **0 Stage 2** (Binance API timeout killed all Stage 2 evaluations)

**Stage 1 standouts (need Stage 2 re-run):**
| Strategy | Return | Max DD | Sharpe |
|---|---|---|---|
| rsi_bb_reversal (BB=15, STD=1.5, conf=65) | **+7.1%** | 14.9% | 1.51 |
| vwap_deviation (conf=65) | +3.6% | 11.4% | 0.86 |
| stochastic_reversal (conf=65) | +3.5% | 11.4% | 0.85 |

**Action:** Re-run research with better network conditions or VPN.

---

## 🔴 Immediate Priorities

### 1. Deploy CTP to VPS
VPS SSH was unreachable during deployment. Code is pushed to origin/master — just needs:
```bash
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && sudo systemctl restart cryptopass.service"
```

### 2. Re-run Phase 4 Research (Stage 2 only)
All 24 Stage 1 survivors need Stage 2 regime walk-forward. Binance connectivity was down.
Options:
- Wait for stable connectivity and retry locally
- Use cached data if available in research_experiments.db
- Investigate adding retry logic to research pipeline

### 3. Market Condition Coverage Gap
Confirmed strategies for 2 of 4 BTC regimes:
- ✅ **TREND_UP** → Now properly handled: trend-followers trade with-trend only (CTP blocks counter-trend)
- ✅ **HIGH_VOL_CHOP** → BBMeanRev, MACDDivergence (mean-reversion, CTP=1.0)
- ❌ **TREND_DOWN** → Need short-biased strategies. rsi_bb_reversal is a candidate.
- ❌ **LOW_VOL_COMPRESSION** → Untested. BB Squeeze Breakout hypothesis ready.

### 4. ATR-Based Trailing Stop Fix
`USE_TRAILING_STOP` still broken. Fix: `trail_dist = ATR(14) × multiplier`.
**Impact:** Unlocks dynamic exits for momentum passports.

---

## 🟡 30-Day Paper Trade Countdown
Started: 2026-04-07. Target end: 2026-05-07.
Current status: -59% portfolio but this is pre-CTP + pre-triage. Fresh evaluation from today forward.

**PromotionPolicy 7-gate threshold:**
- PF ≥ 1.2, WR ≥ 40%, MaxDD < 15%, ≥ 30 trades, ≥ 30 days, Return > 0%, No bug flags

**Watch list (12 active passports):**
| Passport | Type | CTP Override | Key Watch |
|---|---|---|---|
| BBMeanRev | Mean-rev | 1.0 | Best candidate, needs sideways/chop |
| MACDDivergence | Mean-rev | 1.0 | Strong Stage 2 history |
| RSIContrarian | Mean-rev | 1.0 | Contrarian play |
| PressureReader | Trend | default (0.5) | Only profitable live (+$12) |
| BreakoutVol | Trend | default (0.5) | VPS equity $420, watching |
| Momentum | Trend | default (0.5) | Historical +10.7pp improvement |

---

## 🔵 Medium-Term (Next 2-4 Sessions)

### 5. Research Engine — Re-run with CTP
The research pipeline doesn't use CTP yet (it uses `extended_scorer.py` which now HAS CTP).
A re-run post-CTP will show different results — trend-following strategies that bled from counter-trend signals will perform better.

### 6. New Strategy Families
From 151 Trading Strategies journal + web research:
| Strategy | Type | Effort | Status |
|---|---|---|---|
| Funding Rate Carry | Mean-rev | Medium | Needs API endpoint |
| OI + Liquidation Clusters | Reversal | Medium | Needs OI endpoint |
| Multi-timeframe Confluence | Trend | Medium | Needs multi-TF fetcher |
| Short-Only Passport | Directional | Low | CTP now handles this better |

### 7. Promote rsi_momentum to Paper Trading
Apr 7 Stage 2 survivor: +16.6% return, PF 1.94, Sharpe 1.24. Strongest research candidate ever.
Needs: validation re-run with CTP, passport JSON creation, deploy to VPS.

---

## ⚪ Long-Term (Future Sessions)

### 8. Promote First Strategy to Production
### 9. Grafana Dashboard — Equity Curves
### 10. Cross-Passport Portfolio Risk Limit
### 11. Multi-Timeframe Confluence

---

## 🔧 Known Technical Debt

| Issue | File | Severity | Notes |
|---|---|---|---|
| `USE_TRAILING_STOP` formula broken | `bot/position_manager.py` | HIGH | ATR-based fix designed |
| ~~3-regime detector simplistic~~ | `bot/regime_detector.py` | ✅ DONE | 4-regime upgrade (Session 10) |
| ~~Directional gap in scorer~~ | `bot/scorer.py` | ✅ DONE | COUNTER_TREND_PENALTY (Session 10b) |
| No Sharpe ratio in backtester | `bot/backtester.py` | MEDIUM | Research pipeline has it |
| No portfolio-level risk cap | `bot/risk/` | MEDIUM | 12 passports can fire same symbol |
| ReversalV2 negative returns | passports | MEDIUM | Needs hard EMA pre-filter |
| Research pipeline no retry on network errors | `bot/research/pipeline.py` | MEDIUM | Stage 2 dies on Binance timeouts |
| `datetime.utcnow()` deprecation | `bot/regime_detector.py` | LOW | Use `datetime.now(UTC)` |

---

## 📊 Baseline Metrics to Beat

| Passport | Period | Return | PF | WR | MaxDD |
|---|---|---|---|---|---|
| MACDDivergence v0.1 | 90d quality-pair | +9.1% | 1.39 | 41.5% | — |
| BBMeanRev v0.1 | 90d quality-pair | +7.7% | 1.32 | 47.3% | — |
| rsi_momentum (research) | 180d walk-forward | +16.6% | 1.94 | — | — |

**Minimum bar:** return > +7%, PF > 1.2, WR > 35%, MaxDD < 20% on 90d quality pairs.

---

## 🗓️ Session Log

| Session | Date | What Was Done |
|---|---|---|
| 1-4 | 2026-03-31 → 04-04 | Initial passport design, v0.1→v0.2 optimization |
| 5 | 2026-04-05 | New strategy families, research engine built |
| 6 | 2026-04-05 | Research pipeline Stages 1-4 |
| 7 | 2026-04-06 | Cryptopass overhaul, $500 fresh start, BTC Uptrend bug fix |
| 8 | 2026-04-07 | Systematic calc audit: 12 bugs fixed, 49 new tests |
| 9 | 2026-04-08 | ATR fix, direction_bias, Phase 4 launched |
| **10** | **2026-04-09** | **4-regime upgrade, v0.1→v0.2 analysis, North Star reframe, strategic roadmap** |
| **10b** | **2026-04-09** | **COUNTER_TREND_PENALTY, 9 passports disabled, Phase 4 results (network killed Stage 2)** |
