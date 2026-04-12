# Passport Version Registry

> **Session 7 (2026-04-06):** All passports reset to v1.0 fresh start under Cryptopass.
> Directory: `passports/pumpradar/` (7 OG) + `passports/cryptopass-research/` (15 custom)
> Initial equity: $500 per passport. PnL now includes leverage multiplier + trading fees.

> Auto-maintained alongside passport JSON configs.
> Source of truth for tracking strategy evolution and performance.

## How Versioning Works

- Each passport JSON contains a `version` field (semver: `major.minor`) and a `changelog` array.
- `major` bumps when the strategy's **thesis changes** (e.g., trend-following → mean-reversion).
- `minor` bumps when **parameters are tuned** within the same thesis (weights, thresholds, filters).
- Backtest results fill in `backtest_180d` in the changelog entry after validation runs.
- Git history is the authoritative rollback mechanism — `git show <sha>:pumpradar-passports/configs/<file>`.

## Version Comparison Quick Reference

> Results from 180d validation run: Apr 5, `logs/passport_validation_20260405_110244.log`

> ⚠️ Run-to-run variance warning: 180d results swing ±23pp depending on which top-10 pairs Binance returns that day. OG Apr 4 run showed HiddenGem +25.9%; Apr 5 run shows +2.5%. Only quality-pair results (BTC/ETH/SOL/AAVE/BNB) are stable.

| Passport      | v0.1 Return | v0.1 WR | v0.2 Return | v0.2 WR | Δ Return  | Status        |
|---------------|-------------|---------|-------------|---------|-----------|---------------|
| 🏆 OG         | -21.7%      | 39.1%   | -30.6%      | 38.1%   | -8.9pp    | WORSE         |
| 💎 HiddenGem  | +2.5%       | 33.3%   | -20.9%      | 32.1%   | -23.4pp   | WORSE         |
| 🚀 Momentum   | -21.8%      | 39.7%   | -11.0%      | 37.9%   | +10.7pp   | BETTER ✅     |
| 🎯 Dynamic    | -27.1%      | 39.6%   | -11.1%      | 37.9%   | +16.0pp   | BETTER ✅     |
| 🔄 Reversal   | n/a (quarantined) | —  | n/a         | —       | —         | NOT TESTED    |
| 🎯 Sniper     | +2.5%       | 33.3%   | -8.4%       | 32.0%   | -10.9pp   | WORSE         |
| 📢 VolumeKing | -13.1%      | 31.8%   | -17.9%      | 32.3%   | -4.8pp    | WORSE         |
| 📊 MACDDivergence | +9.1% (90d) | 41.5% | — | — | — | Paper live ✅ |
| 🔄 BBMeanRev | +7.7% (90d) | 47.3% | — | — | — | Paper live ✅ |

## Per-Passport Changelog Summary

### 🏆 OG (`og_original.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Raised VOLUME_SPIKE_THRESHOLD 1.5→2.0 per grid search optimization (+49% vs +11%) |

### 💎 HiddenGem (`hidden_gem.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Added pressure=0.5 tiebreaker, raised ema_trend 1.0→1.5, added CONFIDENCE_THRESHOLD 58 |

### 🚀 Momentum (`momentum.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | EMA emphasis (ema=2.0), reduced noise indicators, raised threshold 54→60, capped positions 50→30 |

### 🎯 Dynamic (`dynamic_exit.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Disabled trailing stop (proven -63pp impact), aligned entry weights with Momentum v0.2 |

### 🔄 Reversal (`reversal.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial deployment — overtrade issue discovered in live (337 signals/3 days), quarantined |
| v0.2    | 2026-04-04 | Tightened quarantine: threshold 60→85, vol 2.0→2.5x, positions 20→5, sideways 80→90; keep disabled |
| v0.3    | 2026-04-07 | Add BTC_TREND_WEIGHTS Uptrend:1.0 — mean-reversion has no BTC direction dependency (still disabled) |
| v0.4    | 2026-04-09 | Migrate BTC_TREND_WEIGHTS to 4-regime format (TREND_UP/TREND_DOWN/HIGH_VOL_CHOP/LOW_VOL_COMPRESSION), all 1.0 | (`sniper.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Added MACD confirmation (1.0), raised ema 1.0→1.5, lowered threshold 70→65 for achievable signals |

### 📢 VolumeKing (`volume_king.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-03-31 | Initial production deployment — exact v0.1 baseline |
| v0.2    | 2026-04-04 | Lowered vol threshold 2.5→2.0, reduced vol weight 3.0→2.5, added MACD=0.5 and pressure=0.5 |

### 🔄 Reversal v2 (`reversal_v2.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-05 | Rebuilt from scratch: RSI 30/70 true mean-reversion, threshold 70, enabled=false pending backtest |
| v0.2    | 2026-04-06 | RSI thresholds per-passport (RSI_LONG_THRESHOLD=30, RSI_SHORT_THRESHOLD=70), enabled=true |
| v0.3    | 2026-04-07 | Add BTC_TREND_WEIGHTS Uptrend:1.0 — RSI mean-reversion has no BTC direction dependency |
| v0.4    | 2026-04-09 | Migrate BTC_TREND_WEIGHTS to 4-regime format, all 1.0 | (`macd_divergence.json`)

| Version | Date | Description |
|---------|------|-------------|
| v0.1 | 2026-04-05 | Enabled for paper trading — quality-pair 90d: +9.1%, PF=1.39, WR=41.5%, 123 trades |
| v0.2 | 2026-04-07 | Add BTC_TREND_WEIGHTS Uptrend:1.0 — MACD divergence + RSI is sideways-focused, remove 0.8 uptrend penalty |
| v0.3 | 2026-04-09 | Migrate BTC_TREND_WEIGHTS to 4-regime format, all 1.0 | (`bb_mean_rev.json`)

| Version | Date | Description |
|---------|------|-------------|
| v0.1 | 2026-04-05 | Enabled for paper trading — quality-pair 90d: +7.7%, PF=1.32, WR=47.3%, 131 trades |
| v0.2 | 2026-04-07 | Add BTC_TREND_WEIGHTS Uptrend:1.0 — BB mean-reversion has no BTC direction dependency, remove 0.8 uptrend penalty |
| v0.3 | 2026-04-09 | Migrate BTC_TREND_WEIGHTS to 4-regime format, all 1.0 | (`rsi_contrarian.json`)

| Version | Date | Description |
|---------|------|-------------|
| v0.1 | 2026-04-05 | Enabled for paper trading — quality-pair 90d: +0.5%, PF=1.02, WR=36.1%, 97 trades. Marginal but enabled. |
| v0.2 | 2026-04-07 | Add BTC_TREND_WEIGHTS Uptrend:1.0 — RSI contrarian has no BTC direction dependency, remove 0.8 uptrend penalty |
| v0.3 | 2026-04-09 | Migrate BTC_TREND_WEIGHTS to 4-regime format, all 1.0 | (`seasonality_og.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-05 | OG params + SKIP_WEEKDAYS=[2,4] skip Wed/Fri, leverages +81.1% weekday edge, enabled=true |

### 📈 DualMA Crossover (`dual_ma.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-05 | EMA(10/20) crossover + volume confirmation. 90d quality-pair: -8.96%, PF=0.806, 137 trades, WR=29.9%. Disabled. |

### 🔔 Donchian Breakout (`donchian_breakout.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-05 | Donchian(20) breakout + EMA gate + volume. 90d quality-pair: +0.56%, PF=1.016, 111 trades, WR=34.2%, MaxDD=17.71%. Marginal — disabled pending trending-market re-test. |

### 🌊 OBV Trend (`obv_trend.json`)

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-05 | OBV > EMA(20) trend signal + volume. 90d quality-pair: -11.45%, PF=0.771, 149 trades, WR=28.2%. Disabled. |

### 💥 BollingerBreakout (`bollinger_breakout.json`) — NEW

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-10 | Phase 4 research Stage 2 survivor. BB(15,1.5σ)+Vol(1.5)+Pressure. 180d walk-forward: +23.3% return, Sharpe=1.69, PF=2.77, 415 trades, WR=38.1%. 3 active indicators. |

### 📈 RSIMomentumV2 (`rsi_momentum_v2.json`) — NEW

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-12 | Phase 4 Stage 2 survivor. RSI(10) + divergence + light EMA. Sharpe=1.96, median_ret=+7.3%. |

### 💥 BollingerBreakoutV2 (`bollinger_breakout_v2.json`) — NEW

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-12 | Phase 4 Stage 2 survivor. BB(15,1.5) conf=50. Sharpe=2.70, median_ret=+2.1%. |

### 💥 BollingerBreakoutV3 (`bollinger_breakout_v3.json`) — NEW

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-12 | Phase 4 Stage 2 survivor. BB(15,1.5) conf=55. Sharpe=1.22, median_ret=+1.2%. |

## Session 11e: Per-Passport Regime Optimization (2026-04-12)

All 26 passports updated with `active_regimes` and `regime_params` fields.
Phase 1: hard gate only (regime_params={} for all). Per-regime tuning deferred to Phase 2.

### Regime Assignments

| Category | Passports | Active Regimes |
|----------|-----------|----------------|
| Trend-Following (11) | HiddenGem, Sniper, VolumeKing, Momentum, DualMA, PureTrend, TrendMomentum, TrendConfirm, MinimalEdge, OBV Trend, Dynamic | TREND_UP, TREND_DOWN |
| Mean-Reversion (3) | BBMeanRev, RSIContrarian, ReversalV2 | HIGH_VOL_CHOP, LOW_VOL_COMPRESSION |
| Breakout (5) | BollingerBreakout, BollingerBreakoutV2, BollingerBreakoutV3, BreakoutVol, Donchian | LOW_VOL_COMPRESSION, TREND_UP, TREND_DOWN |
| Hybrid (6) | PressureReader, MACDDivergence, RSIMomentumV2, OG, OG Seasonal, BalancedSelective | varies per passport |
| Disabled (1) | Reversal | HIGH_VOL_CHOP, LOW_VOL_COMPRESSION |

### Version Bumps (batch)
- Pumpradar passports: v0.2→v0.3 or v0.3→v0.4
- Cryptopass-research passports: v0.1→v0.2 or v0.2→v0.3

### Config Default Change
- `ATR_TRAIL_MULTIPLIER`: 2.0 → 2.5 (wider trailing stop, still disabled globally)

---

## Rollback Instructions

```bash
# See any passport at a prior version
git show 950e0ec:pumpradar-passports/configs/og_original.json

# Roll back a single passport
git checkout 950e0ec -- pumpradar-passports/configs/og_original.json
git commit -m "revert(og): roll back to v0.1 — v0.2 underperformed in backtest"

# Roll back all passports to v0.1 baseline
git checkout 950e0ec -- pumpradar-passports/configs/
git commit -m "revert: roll back all passports to v0.1 baseline"
```
