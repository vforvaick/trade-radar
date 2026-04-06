# 🎫 Strategy Passport — Pumpradar Replication

> Version 1.0 | Derived from 49 trades, Feb–Mar 2026

---

## Identity

| Field | Value |
|---|---|
| Name | PumpRadar Replica |
| Market | Crypto Futures (USDT Perpetuals) |
| Exchange | Binance Futures |
| Style | Momentum/Mean-Reversion Confluence |
| Direction | Bi-directional (LONG + SHORT) |
| Timeframe | **TBD** — likely 1H or 4H (to be backtested) |
| Universe | All USDT perps on Binance (~200+ pairs) |

---

## Entry Rules

### Indicators (by importance)

| # | Indicator | Settings (estimated) | Signal |
|---|---|---|---|
| 1 | **Volume Spike** | vs 20-period avg | Spike > 1.5× avg = bullish |
| 2 | **Buy/Sell Pressure** | Order flow ratio | > 60% buy = LONG, > 60% sell = SHORT |
| 3 | **MACD** | (12, 26, 9) standard | Signal line cross confirmation |
| 4 | **RSI** | Period 14 | > 50 = LONG, < 50 = SHORT |
| 5 | **EMA Trend** | 9 / 21 / 50 (TBD) | All aligned = strong signal |
| 6 | **Candle Direction** | Last candle | Confirms or warns |
| 7 | **Bollinger Band** | (20, 2) | Position 0–1 for stretch detection |
| 8 | **RSI Divergence** | Period 14 | Bearish/bullish divergence detection |

### Confluence Scoring

```
Score = count of aligned indicators / total indicators × 100

GO threshold:  score ≥ 54%
NO-GO:         score < 54%
```

### BTC Context Filter

| BTC Trend | Action |
|---|---|
| Sideways | ✅ Trade freely (79% of historical signals) |
| Downtrend | ✅ Trade (75% WR historically — best!) |
| Uptrend | ⚠️ Cautious (33% WR — worst) |

---

## Position Sizing

### Leverage Tiers (mapped to R:R)

| Confidence | R:R | Leverage | SL Distance | TP1 Distance |
|---|---|---|---|---|
| 54–60% | 1:1.25 | **4x** | ~3.5% | ~3.0% |
| 61–69% | 1:1.43 | **5x** | ~4.1% | ~3.5% |
| 70–75% | 1:2.08 | **7x** | ~3.8% | ~4.8% |

### Risk Per Trade
- **Fixed 3% of equity** per trade
- Max simultaneous positions: **3–5** (observed from data)
- Position size = [(equity × 0.03) / SL_distance × leverage](file:///Users/faiqnau/fight/trading/crypto-signal/analyze_stats.py#37-39)

---

## Exit Rules (The Core Edge)

### Take Profit Cascade

```
TP1 = Entry ± (SL_distance × R:R_ratio × 0.48)     ~4.33% avg
TP2 = Entry ± (TP1_distance × 1.61)                 ~6.98% avg
TP3 = Entry ± (TP2_distance × 1.53)                 ~10.69% avg
```

### Scaling Out

```
Entry → 100% position
  │
  ├─ TP1 Hit ──→ CLOSE 70%
  │              MOVE SL → Entry (breakeven)
  │              30% rides risk-free
  │
  ├─ TP2 Hit ──→ CLOSE 20% more
  │              10% becomes "moonbag"
  │
  └─ TP3 Hit ──→ CLOSE final 10% ("Jackpot")
```

### Stop Loss
- **Fixed**: SL_distance from entry (~3.82% avg, unleveraged)
- After TP1: SL moves to **breakeven**

---

## Risk Management

| Rule | Value |
|---|---|
| Max risk/trade | 3% of equity |
| Max consecutive losses observed | 4 |
| Worst single loss | -47.6% (leveraged, 7x) |
| BTC anomaly alert | If BTC moves >1.5% in <5 min |
| Anomaly action | Consider manual close of at-risk positions |

### Day-of-Week Filter (optional)

| Day | Win Rate | Recommendation |
|---|---|---|
| Monday | 71.4% | ✅ Trade |
| Thursday | 100% | ✅ Trade |
| Sunday | 75.0% | ✅ Trade |
| Wednesday | 16.7% | ❌ Skip |
| Friday | 11.1% | ❌ Skip |

> ⚠️ Small sample sizes — validate with more data before hardcoding

---

## Performance Benchmark

| Metric | Value |
|---|---|
| Win Rate | 57.1% |
| Profit Factor | 1.50 |
| Expectancy/trade | +3.41% (leveraged) |
| Avg time to TP1 | 4.3h |
| Avg time to SL | 10.5h |
| Simulated return (6w) | **+29.6%** |
| SHORT win rate | 65.2% (better than LONG 50%) |

---

## Known Gaps (to resolve via backtesting)

| # | Gap | Priority | Resolution |
|---|---|---|---|
| 1 | **Candle timeframe** | 🔴 High | Backtest 15m, 1H, 4H with indicator stack |
| 2 | **EMA periods** | 🟡 Medium | Try 9/21/50 vs 9/21/55 vs 8/21/55 |
| 3 | **Volume spike threshold** | 🟡 Medium | Test 1.5×, 2×, 2.5× vs 20-period avg |
| 4 | **Pressure calculation** | 🟡 Medium | Orderbook-based vs candle body ratio |
| 5 | **Pair filtering** | 🟢 Low | Min volume, min market cap filters |
| 6 | **Day filter robustness** | 🟢 Low | Need 3+ months of data to confirm |
