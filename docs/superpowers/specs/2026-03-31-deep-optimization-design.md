# Deep Optimization Pipeline — Pumpradar Strategy

> Design Spec v1.0 | 2026-03-31
>
> **Historical drift note:** This spec is a historical design record, not the authoritative implementation state. It may be superseded by current code and [`docs/crypto_signal_handover.md`](../../crypto_signal_handover.md). Current code uses `score_confluence()`/`cfg_override`, JSON passport outputs, and fixed weight profiles in `bot/discovery_engine.py`; treat the sections below as planning context unless you verify them against the live modules.

## Goal

Expand and sharpen the Pumpradar Replication strategy by systematically exploring new dimensions (indicators, timeframes, exit variants, regime filters) using a 6-layer sequential optimization pipeline. The end result: **1 sharpened master passport + 2-3 forked variant passports** (Conservative, Balanced, Aggressive).

## Baseline (Current Best)

From initial grid search (30 days × 15 pairs × 1H):

| Rank | Return | WR | Trades | Key Param |
|---|---|---|---|---|
| #1 | +49.1% | 49.0% | 618 | EMA 8/21/55, Vol 2.0× |
| #2 | +49.1% | 49.5% | 610 | EMA 9/21/50, Vol 2.0× |
| #3 | +11.5% | 49.0% | 692 | EMA 9/21/55, Vol 1.5× |

> ⚠️ 30 days is too short. All layers below use **180 days** minimum.

---

## Layer 1 — Timeframe Resolution

**Question:** Is 1H really optimal, or would 15m (more signals) or 4H (higher quality) beat it?

| Timeframe | Test | Expectation |
|---|---|---|
| 15m | Same indicator stack | More trades, lower WR, scalper profile |
| 1H | Baseline | Current benchmark |
| 4H | Same indicator stack | Fewer trades, higher WR, swing profile |

**Output:** Lock the winning timeframe for Layer 2+. If multiple TFs are close, keep top 2 for multi-TF confirmation testing in Layer 5.

---

## Layer 2 — Indicator Weight Optimization

Historical planning assumption: **equal weights** for all 8 indicators. That is not the full current implementation picture.

**New approach:** Assign individual weights per indicator and optimize them.

| Indicator | Weight Range to Test |
|---|---|
| `volume_spike` | 0.5 – 3.0 |
| `pressure` | 0.5 – 2.0 |
| `ema_trend` | 0.5 – 3.0 |
| `macd_signal` | 0.5 – 2.0 |
| `rsi_position` | 0.5 – 2.0 |
| `bb_position` | 0.0 – 2.0 |
| `rsi_divergence` | 0.0 – 2.0 |
| `candle_direction` | 0.0 – 1.0 |

Also test **indicator dropout**: what happens if we remove BB entirely? Or RSI Divergence? Identify which indicators actually carry signal vs noise.

Current code note: discovery uses five fixed weight profiles, including `Equal`, `Volume-Heavy`, `Trend-Purist`, `Reversal`, and `Minimal`, rather than a fully free-form weight search in production.

**Output:** Ranked indicator importance + optimal weight vector.

---

## Layer 3 — New Indicator Injection

Add one new indicator at a time to the winning stack from Layer 2. Keep only if it improves return AND doesn't degrade WR.

| New Indicator | Rationale |
|---|---|
| **ATR (Average True Range)** | Dynamic SL/TP sizing instead of fixed % — adapts to volatility |
| **Stochastic RSI** | More sensitive momentum oscillator, catches reversals earlier |
| **ADX (Average Directional Index)** | Measures trend strength — avoid ranging markets |
| **OBV (On-Balance Volume)** | Volume-price divergence detection |
| **VWAP** | Institutional reference price — strong support/resistance |
| **Ichimoku Cloud** | Multi-dimensional trend/support in one indicator |

**Output:** Updated indicator stack (8 original ± additions/removals).

---

## Layer 4 — Exit Strategy Variants

The 70/20/10 cascade is the **core edge**. But is it optimal?

### 4a: TP Split Ratios

| Variant | TP1 | TP2 | TP3 | Hypothesis |
|---|---|---|---|---|
| Current | 70% | 20% | 10% | Secure profits fast |
| Conservative | 80% | 15% | 5% | Even more secure |
| Balanced | 50% | 30% | 20% | More upside exposure |
| Aggressive | 40% | 30% | 30% | Moonbag heavy |

### 4b: TP Distance Methods

| Method | Description |
|---|---|
| Current | Fixed R:R multiplier from passport |
| ATR-based | Current code uses `SL=2*ATR` and `TP1=4*ATR`; TP2/TP3 are derived from `TP2_RATIO` and `TP3_RATIO` |
| Fibonacci | TP levels at 1.618, 2.618, 4.236 extensions |

### 4c: Trailing Stop

| Variant | Description |
|---|---|
| No trail (current) | Fixed SL → breakeven after TP1 |
| ATR trail | After TP1, trail SL by 1.5×ATR |
| Percentage trail | After TP2, trail SL by 2% below latest high |

**Output:** Best exit combination per variant profile.

---

## Layer 5 — Market Regime & Session Filters

### 5a: Volatility Regime

| Regime | Condition | Action |
|---|---|---|
| Low vol | ATR < 50th percentile | Tighten TP/SL, lower leverage |
| Normal | ATR 50-80th | Standard params |
| High vol | ATR > 80th | Widen TP/SL OR skip trades entirely |

### 5b: Session Filter

| Session | Hours (UTC) | Hypothesis |
|---|---|---|
| Asia | 00:00–08:00 | Lower volume, more fakeouts |
| Europe | 08:00–16:00 | Momentum breakouts |
| US | 13:00–21:00 | Highest volume, strongest moves |

### 5c: Multi-Timeframe Confirmation

Enter on winning TF only if higher TF (4H or Daily) trend agrees. Expected: fewer trades, higher WR.

**Output:** Regime-adaptive parameter sets.

---

## Layer 6 — Robustness Validation (Anti-Overfitting)

> [!CAUTION]
> This is the most critical layer. Without it, all "gains" could be curve-fitting.

### 6a: Walk-Forward Validation

```
180 days total:
├── Train: Day 1–120 (optimize parameters)
└── Test:  Day 121–180 (validate on unseen data)

Result valid ONLY if test performance ≥ 70% of train performance.
```

Current code note: [`bot/walk_forward.py`](../../bot/walk_forward.py) does not enforce that 70% rule. It calculates a Sharpe-delta style `overfit_score` and returns `KEEP` when `overfit_score < 0.3` with positive test return, `TUNE` when `overfit_score <= 0.6` with positive test return, otherwise `KILL`.

### 6b: Monte Carlo Simulation

Randomize trade execution order 1000× times. If strategy is robust, the distribution of returns should be tight (low variance).

### 6c: Cross-Pair Validation

Train on top 10 pairs → test on 10 different pairs. Strategy must generalize.

### 6d: Stress Test

Test against known crash periods (if data available) to measure max drawdown under extreme conditions.

**Output:** Confidence interval for each strategy variant.

---

## Final Tournament

Top performers from Layer 6 compete:

```
Layer 6 survivors (4-6 strategies)
    │
    ├── Run identical 60-day out-of-sample test
    │
    ├── Rank by: Sharpe Ratio > Return > Max DD
    │
        └── Fork top 3 into passport variants:
        ├── pumpradar-conservative.json  (high WR, low leverage)
        ├── pumpradar-balanced.json      (current sweet spot)
        └── pumpradar-aggressive.json    (max return, higher risk)
```

---

## Implementation: Backtester V2 Upgrades Needed

| Feature | Current | Needed |
|---|---|---|
| Backtest duration | 30 days | 180 days |
| Indicator weights | Equal (1.0) | Configurable per-indicator |
| New indicators | — | ATR, StochRSI, ADX, OBV, VWAP |
| Exit variants | Fixed 70/20/10 | Configurable split + trailing |
| Walk-forward | — | Train/test split mode |
| Monte Carlo | — | Trade-order randomization |
| Results export | stdout | CSV + JSON for analysis |
| Multi-config batch | 5 combos | 50-100 combos via YAML |

Current code note: generated discovery outputs are JSON records/passports, not Markdown strategy docs. Use the live `bot/discovery_engine.py` and `bot/passport_runner.py` outputs as the implementation reference.

---

## Execution Order

1. Upgrade `backtester.py` with V2 features (configurable weights, new indicators, walk-forward mode, CSV export)
2. Run Layer 1 (timeframe) → lock TF
3. Run Layer 2 (weights) → lock weight vector
4. Run Layer 3 (new indicators) → lock final stack
5. Run Layer 4 (exit variants) → lock exit params per profile
6. Run Layer 5 (regime filters) → adaptive rules
7. Run Layer 6 (robustness) → validate everything
8. Tournament → fork passports
