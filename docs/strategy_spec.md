# 🔬 Pumpradar — Reverse-Engineered Strategy Specification

> Canonical spec generated from `data/validated_ledger.csv` + `data/all_messages.json`.
> Sample period: 2026-02-18 to 2026-03-30
> Interpretation note: indicator counts and distances are observed measurements; threshold and BB-setting statements below are hypotheses inferred from sparse AI Insight text, not ground-truth constants.

## TP/SL Distance Formula

### Overall Distance Averages

- **TP1 distance**: 4.33% from entry
- **TP2 distance**: 6.98% from entry
- **TP3 distance**: 10.69% from entry
- **SL distance**: 3.82% from entry
- **TP1/SL ratio**: 1.13
- **TP spacing ratio (TP2/TP1)**: 1.61
- **TP spacing ratio (TP3/TP2)**: 1.53

## Indicator Parameters (from AI Insight NLP)

### Indicator Frequency in AI Insights

| Indicator | Mentions | % of Signals |
|---|---|---|
| Volume | 37 | 65% |
| Buy/Sell Pressure | 35 | 61% |
| MACD | 20 | 35% |
| RSI | 19 | 33% |
| EMA | 18 | 32% |
| Candle | 16 | 28% |
| Bollinger Band | 9 | 16% |
| Divergence | 7 | 12% |
| ROC | 1 | 2% |

### RSI Values Mentioned
- Values found: [50, 50]
- Hypothesis from observed mentions: **RSI <50 for SHORT, >50 for LONG**

### Bollinger Band Positions
- BB Position values: [0.9]
- BB Position range: 0.90 – 0.90
- Hypothesis from observed BB references: **(20, 2)** standard

### Buy/Sell Pressure Thresholds
- Values: [76.4, 76.9, 69.3, 76.0, 96.0]

## 🎯 Complete Strategy Specification

### Entry Conditions
1. **Multi-indicator confluence** scoring system:
   - EMA trend alignment (9/21/50)
   - MACD signal confirmation
   - RSI position (>50 for LONG, <50 for SHORT)
   - RSI divergence detection
   - Bollinger Band position (20, 2)
   - Volume spike detection
   - Buy/Sell pressure ratio
   - Last candle direction
2. **BTC trend filter** with confidence down-weighting in Uptrend
3. **Confidence threshold** around 54%

### Position Sizing & Leverage
- Risk per trade: 2-3% of equity
- 7x, 5x, and 4x leverage tiers map to confidence and R:R

### Exit Management
```
Signal fires → Enter position 100%
  ├─ TP1 hit → Close 70%, move SL to breakeven
  ├─ TP2 hit → Close 20% more
  └─ TP3 hit → Close final 10%
```

### Risk Management
- Max consecutive losses observed: **4**
- Average time to SL: **10.5h**
- BTC anomaly monitoring for fast market shocks