# Passport Version Registry

> **Session 7 (2026-04-06):** All passports reset to v1.0 fresh start under Cryptopass.
> **Session 12 (2026-04-14):** 19 new passports added (12 research winners + 7 Gen2 forks). 17 disabled passports re-enabled. Total: 45 active passports.
> Directory: `passports/pumpradar/` (7 OG) + `passports/cryptopass-research/` (38 custom)
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

## Session 11f — Phase 2: Per-Regime Parameter Tuning (2026-04-13)

All 26 passports now have thesis-driven `regime_params` for per-regime behavior tuning.

### Design Rules Applied
- **TREND_DOWN:** +4 confidence, 0.3% risk, max 15 positions, SHORT_ONLY for directional strategies
- **HIGH_VOL_CHOP:** +4 confidence, 0.3% risk, max 10 positions
- **TREND_UP:** LONG_ONLY for directional strategies, standard params otherwise
- **LOW_VOL_COMPRESSION:** Standard params (clean signals, no adjustment needed)

### Category Assignments
| Category | Passports | DIRECTION_BIAS? |
|----------|-----------|-----------------|
| Trend-Following (11) | DualMA, MinimalEdge, OBV Trend, PureTrend, TrendConfirm, TrendMomentum, Dynamic, HiddenGem, Momentum, Sniper, VolumeKing | ✅ LONG_ONLY / SHORT_ONLY |
| Mean-Reversion (4) | BBMeanRev, RSIContrarian, ReversalV2, Reversal | ❌ Always BOTH |
| Breakout (5) | BollingerBreakout (v1/v2/v3), BreakoutVol, Donchian | ❌ Always BOTH |
| Hybrid-Directional (5) | BalancedSelective, PressureReader, RSIMomentumV2, OG Seasonal, OG | ✅ LONG_ONLY / SHORT_ONLY |
| Hybrid-Neutral (1) | MACDDivergence | ❌ Always BOTH |

---

## Session 12 — Full Passport Expansion (2026-04-14)

### Re-enablement of 17 Disabled Passports

All passports disabled by triage commit `9f8b289` are now re-enabled. Safety net: confidence cap (80) + regime gating + `MAX_OPEN_POSITIONS_PER_SYMBOL=1`.

| Passport | Category | Re-enable Rationale |
|----------|----------|---------------------|
| Pumpradar HiddenGem | Trend-Following | Confidence cap prevents overtrade; regime gate filters choppy regime |
| Pumpradar Sniper | Trend-Following | Same as HiddenGem |
| Pumpradar VolumeKing | Trend-Following | Same as HiddenGem |
| Pumpradar Momentum | Trend-Following | v0.2 improved -11.0% (vs v0.1 -21.8%); acceptable risk |
| Pumpradar Dynamic | Trend-Following | v0.2 improved -11.1% (vs v0.1 -27.1%); acceptable risk |
| Pumpradar Reversal | Mean-Reversion | v0.4 has regime gating + threshold 85; controlled exposure |
| BalancedSelective | Hybrid | Previously stable; regime gating added |
| BollingerBreakout | Breakout | Phase 4 champion: +23.3% 180d walk-forward |
| BollingerBreakoutV2 | Breakout | Sharpe=2.70; different threshold variant |
| BollingerBreakoutV3 | Breakout | Sharpe=1.22; different threshold variant |
| DonchianBreakout | Breakout | Borderline 90d: +0.56%, PF=1.016; regime gate provides downside protection |
| DualMA | Trend-Following | Gen2 fork provides control comparison; re-enable both |
| MinimalEdge | Trend-Following | Gen2 fork provides control comparison; re-enable both |
| OBVTrend | Trend-Following | Gen2 fork provides control comparison; re-enable both |
| PureTrend | Trend-Following | Gen2 fork provides control comparison; re-enable both |
| TrendConfirm | Trend-Following | Regime-gated; acceptable risk |
| TrendMomentum | Trend-Following | Gen2 fork provides control comparison; re-enable both |

### New Passports — 12 Research Winners

Phase 4 walk-forward (180d, quality pairs) survivors promoted to paper trading. All use 2–3 active indicators (selectivity principle preserved).

#### 📈 RSIMomentumGen2 (`rsi_momentum_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. RSI position(2.0) + RSI divergence(1.5) + EMA context(0.5). 180d median: +6.6%, PF=1.51, Sharpe=1.52. Folds: [+10.2%, +3.0%]. Active regimes: null (all). Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, `rsi_momentum` family
- **Indicators:** rsi_position(2.0), rsi_divergence(1.5), ema_trend(0.5)
- **Thesis:** RSI momentum + divergence confirmation as primary; EMA as lightweight trend context
- **Active Regimes:** All (null)

#### 🔻 PressureFlowShort (`pressure_flow_short.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. Pressure(2.5) + candle_direction(1.5) + EMA(1.0). SHORT_ONLY. 180d median: +4.1%, PF=1.92, Sharpe=0.75. Folds: [-1.1%, +9.3%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, `pressure_flow_short` family (added in Session 9)
- **Indicators:** pressure(2.5), candle_direction(1.5), ema_trend(1.0)
- **Thesis:** Sustained selling pressure + bearish candle confirmation. SHORT_ONLY direction bias.
- **Active Regimes:** All (null)

#### 🔄 RSIBBReversal (`rsi_bb_reversal.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. RSI(2.0) + BB(2.0) + Volume(1.0). Mean-reversion. 180d median: +3.8%, PF=1.33, Sharpe=0.96. Folds: [+3.4%, +4.2%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, RSI+BB reversal family
- **Indicators:** rsi_position(2.0), bb_position(2.0), volume_spike(1.0)
- **Thesis:** RSI oversold/overbought at Bollinger Band extremes with volume confirmation
- **Active Regimes:** All (null)

#### 💎 HiddenGemGen2 (`hidden_gem_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. EMA(1.0) + BB(1.0) + Volume(2.0). Tuned params: EMA(8/45), BB(18), vol_thresh=1.5x. 180d median: +3.0%, PF=1.11, Sharpe=1.36. Folds: [-4.0%, +10.0%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, enhanced HiddenGem; parent: HiddenGem v0.1 (EMA+BB+Vol selectivity)
- **Indicators:** ema_trend(1.0), bb_position(1.0), volume_spike(2.0)
- **Thesis:** Same 3-indicator combo as parent HiddenGem but with research-optimized EMA(8/45) and BB(18) periods
- **Active Regimes:** All (null)

#### 📍 PivotBounce (`pivot_bounce.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. Pivot(2.0) + BB(1.5) + RSI(1.0). 180d median: +2.3%, PF=2.06, Sharpe=1.28. Folds: [-1.7%, +6.4%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, new family (uses extended `pivot_points` indicator)
- **Indicators:** pivot_points(2.0), bb_position(1.5), rsi_position(1.0)
- **Thesis:** Enter near classical S1/S2 or R1/R2 pivot levels with RSI + BB confirmation
- **Active Regimes:** All (null)

#### 🌀 StochReversal (`stoch_reversal.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. StochRSI(2.5) + RSI(1.5) + BB(1.0). 180d median: +2.3%, PF=2.06, Sharpe=1.28. Folds: [-1.7%, +6.4%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, new family (uses extended `stochrsi` indicator)
- **Indicators:** stochrsi(2.5), rsi_position(1.5), bb_position(1.0)
- **Thesis:** StochRSI crossover from oversold/overbought as primary signal with RSI + BB confirmation
- **Active Regimes:** All (null)

#### 📊 VWAPDeviation (`vwap_deviation_strat.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. VWAP(2.5) + BB(1.5) + RSI(1.0). 180d median: +2.3%, PF=2.06, Sharpe=1.28. Folds: [-1.7%, +6.4%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, new family (uses extended `vwap_deviation` indicator)
- **Indicators:** vwap_deviation(2.5), bb_position(1.5), rsi_position(1.0)
- **Thesis:** Mean-reversion when price deviates >1.5σ from rolling VWAP
- **Active Regimes:** All (null)

#### 📉 WilliamsReversal (`williams_reversal.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. Williams%R(2.5) + RSI(1.5) + BB(1.0). 180d median: +2.3%, PF=2.06, Sharpe=1.28. Folds: [-1.7%, +6.4%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, new family (uses extended `williams_r` indicator)
- **Indicators:** williams_r(2.5), rsi_position(1.5), bb_position(1.0)
- **Thesis:** Williams %R extremes (<-80 LONG, >-20 SHORT) with RSI + BB confirmation
- **Active Regimes:** All (null)

#### 🚀 SupertrendFollow (`supertrend_follow.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. Supertrend(3.0) + EMA(1.5). Low return but very high Sharpe. 180d median: +0.9%, PF=1.02, Sharpe=2.06. Folds: [-2.5%, +4.3%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, new family (uses extended `supertrend` indicator)
- **Indicators:** supertrend(3.0), ema_trend(1.5)
- **Thesis:** ATR-based Supertrend flip as direction signal with EMA trend confirmation. Consistent small gains.
- **Active Regimes:** All (null)

#### 🔔 DonchianBreakoutGen2 (`donchian_breakout_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. Donchian(2.5) + EMA(1.5) + Volume(1.0). 180d median: +0.6%, PF=1.01, Sharpe=2.30. Folds: [-3.8%, +4.9%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4; parent: DonchianBreakout v0.1 (marginal 90d, +0.56%)
- **Indicators:** donchian(2.5), ema_trend(1.5), volume_spike(1.0)
- **Thesis:** Donchian channel breakout using research-built indicator (vs OG's approximate EMA gate)
- **Active Regimes:** All (null)

#### 📐 KeltnerBreakout (`keltner_breakout.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. Keltner(2.5) + EMA(1.0) + Volume(2.0). 180d median: +0.6%, PF=1.01, Sharpe=2.30. Folds: [-3.8%, +4.9%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4, new family (uses extended `keltner` indicator)
- **Indicators:** keltner(2.5), ema_trend(1.0), volume_spike(2.0)
- **Thesis:** Keltner channel breakout with EMA + volume confirmation. Volatility-based channel vs BB's std-dev channel.
- **Active Regimes:** All (null)

#### 📶 OBVTrendGen2 (`obv_trend_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Phase 4 winner. OBV(2.5) + EMA(1.5) + Volume(1.0). Breakeven median, very high Sharpe. 180d median: +0.0%, PF=1.00, Sharpe=2.21. Folds: [-4.4%, +4.4%]. Status: New — awaiting paper trade validation. |

- **Lineage:** Research Phase 4; parent: OBVTrend v0.1 (-11.45% 90d, disabled)
- **Indicators:** obv_trend(2.5), ema_trend(1.5), volume_spike(1.0)
- **Thesis:** OBV linear regression trend signal (research indicator) vs OG's simple OBV>EMA signal
- **Active Regimes:** All (null); needs regime tuning in future session

---

### New Passports — 7 Gen2 Enhanced Forks

Big-loss passports forked into Gen2 variants applying the selectivity principle. Each Gen2 documents its thesis change from the parent.

#### ⚡ DynamicGen2 (`dynamic_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Enhanced fork of Pumpradar Dynamic. 8→3 indicators (selectivity). EMA(1.0)+BB(1.5)+Vol(2.0). Regime-gated TREND_UP/DOWN. Status: New — awaiting paper trade validation. |

- **Lineage:** Fork of Pumpradar Dynamic (`dynamic_exit.json`)
- **Thesis change:** Parent had all 8 indicators active = diluted confidence = low WR. Gen2 applies selectivity: 3 indicators only.
- **Indicators:** ema_trend(1.0), bb_position(1.5), volume_spike(2.0)
- **Active Regimes:** TREND_UP (LONG_ONLY), TREND_DOWN (SHORT_ONLY, conf+4, risk=0.3%)

#### 💨 MomentumGen2 (`momentum_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Enhanced fork of Pumpradar Momentum. 8→3 indicators. EMA(1.5)+RSI(2.0)+Pressure(1.5). TREND_UP/DOWN. Status: New — awaiting paper trade validation. |

- **Lineage:** Fork of Pumpradar Momentum (`momentum.json`)
- **Thesis change:** Parent v0.2 used EMA(2.0) alone as primary. Gen2 adds RSI momentum + pressure flow — momentum + flow confirmation combo.
- **Indicators:** ema_trend(1.5), rsi_position(2.0), pressure(1.5)
- **Active Regimes:** TREND_UP (LONG_ONLY), TREND_DOWN (SHORT_ONLY, conf+4, risk=0.3%)

#### 🎯 BollingerBreakoutGen4 (`bollinger_breakout_gen4.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Enhanced fork of BollingerBreakout v1/v2/v3. All 3 prior versions negative. Gen4: conf=65, BB(20,2.0σ)+Vol(1.5)+Pressure(1.5). Regime-gated. Status: New — awaiting paper trade validation. |

- **Lineage:** Fork of BollingerBreakout v1/v2/v3
- **Thesis change:** v1/v2/v3 used BB(15,1.5σ) breakout — too tight. Gen4 switches to standard BB(20,2.0σ) for cleaner breakouts. Adds regime gating for TREND_UP/DOWN/HIGH_VOL_CHOP.
- **Indicators:** bb_position(2.0), volume_spike(1.5), pressure(1.5)
- **Active Regimes:** TREND_UP (LONG_ONLY), TREND_DOWN (SHORT_ONLY, conf+4, risk=0.3%), HIGH_VOL_CHOP (conf+4, risk=0.3%)

#### 🌊 TrendMomentumGen2 (`trend_momentum_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Enhanced fork of TrendMomentum. Dropped MACD, kept EMA(2.0)+RSI(2.0). TREND_UP/DOWN. Status: New — awaiting paper trade validation. |

- **Lineage:** Fork of TrendMomentum (`trend_momentum.json`)
- **Thesis change:** Parent used EMA+MACD+RSI. MACD is noisy on 1H. Gen2 drops MACD entirely — cleaner 2-indicator momentum signal.
- **Indicators:** ema_trend(2.0), rsi_position(2.0)
- **Active Regimes:** TREND_UP (LONG_ONLY), TREND_DOWN (SHORT_ONLY, conf+4, risk=0.3%)

#### ✌️ DualMAGen2 (`dual_ma_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Enhanced fork of DualMA Crossover. Added BB(1.0) for mean-reversion context. EMA(1.5)+BB(1.0)+Vol(1.5). TREND_UP/DOWN. Status: New — awaiting paper trade validation. |

- **Lineage:** Fork of DualMA Crossover (`dual_ma.json`)
- **Thesis change:** Parent used only EMA+Volume (90d: -8.96%, WR=29.9%). Gen2 adds BB as mean-reversion context — avoids chasing trend entries at Bollinger extremes.
- **Indicators:** ema_trend(1.5), bb_position(1.0), volume_spike(1.5)
- **Active Regimes:** TREND_UP (LONG_ONLY), TREND_DOWN (SHORT_ONLY, conf+4, risk=0.3%)

#### 🎲 MinimalEdgeGen2 (`minimal_edge_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Enhanced fork of MinimalEdge. Added candle_direction(1.0) for entry timing. EMA(1.5)+Vol(1.5)+Candle(1.0). TREND_UP/DOWN. Status: New — awaiting paper trade validation. |

- **Lineage:** Fork of MinimalEdge (`minimal_edge.json`)
- **Thesis change:** Parent uses EMA+Volume (2 indicators). Gen2 adds candle_direction as timing filter — tests whether 3 indicators with entry timing beat 2 without.
- **Indicators:** ema_trend(1.5), volume_spike(1.5), candle_direction(1.0)
- **Active Regimes:** TREND_UP (LONG_ONLY), TREND_DOWN (SHORT_ONLY, conf+4, risk=0.3%)

#### 🎋 PureTrendGen2 (`pure_trend_gen2.json`)

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-14 | Enhanced fork of PureTrend. Added Supertrend(2.5) for ATR-based confirmation. EMA(1.5)+Supertrend(2.5). TREND_UP/DOWN. Status: New — awaiting paper trade validation. |

- **Lineage:** Fork of PureTrend (`pure_trend.json`)
- **Thesis change:** Parent is EMA-only (1 effective indicator, minimal edge). Gen2 adds Supertrend — ATR-based trend confirmation that adapts to volatility, providing a second independent signal source.
- **Indicators:** ema_trend(1.5), supertrend(2.5)
- **Active Regimes:** TREND_UP (LONG_ONLY), TREND_DOWN (SHORT_ONLY, conf+4, risk=0.3%)

---

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
