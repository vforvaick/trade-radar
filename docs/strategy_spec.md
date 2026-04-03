# 🔬 Pumpradar — Reverse-Engineered Strategy Specification

## TP/SL Distance Formula

### Distance by R:R Tier

| R:R | Avg TP1% | Avg TP2% | Avg TP3% | Avg SL% | TP1/SL | TP2/TP1 | TP3/TP2 |
|---|---|---|---|---|---|---|---|
| 1:1.25 | 3.01% | 4.37% | 6.63% | 3.49% | 0.86 | 1.45 | 1.52 |
| 1:1.43 | 3.52% | 5.87% | 8.79% | 4.10% | 0.86 | 1.66 | 1.50 |
| 1:1.87 | 3.43% | 5.13% | 8.55% | 2.73% | 1.26 | 1.50 | 1.67 |
| 1:1.88 | 6.40% | 9.58% | 15.99% | 5.12% | 1.25 | 1.50 | 1.67 |
| 1:2.08 | 4.76% | 7.94% | 11.92% | 3.81% | 1.25 | 1.67 | 1.50 |
| 1:2.87 | 0.80% | 1.04% | 1.45% | 0.36% | 2.20 | 1.30 | 1.39 |

### Overall Distance Averages

- **TP1 distance**: 4.33% from entry
- **TP2 distance**: 6.98% from entry
- **TP3 distance**: 10.69% from entry
- **SL distance**: 3.82% from entry
- **TP1/SL ratio**: 1.13
- **TP spacing ratio (TP2/TP1)**: 1.61
- **TP spacing ratio (TP3/TP2)**: 1.53

### TP/SL Distance by Leverage

| Leverage | Avg TP1% | Avg SL% | Unleveraged TP1% | Unleveraged SL% |
|---|---|---|---|---|
| 3x | 19.77% | 15.81% | 19.77% | 15.81% |
| 4x | 3.01% | 3.49% | 3.01% | 3.49% |
| 5x | 5.14% | 4.72% | 5.14% | 4.72% |
| 6x | 9.47% | 7.58% | 9.47% | 7.58% |
| 7x | 3.04% | 2.42% | 3.04% | 2.42% |

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
- Likely RSI threshold: **<50 for SHORT, >50 for LONG**

### Bollinger Band Positions
- BB Position values: [0.9]
- BB Position range: 0.90 – 0.90
- Likely BB settings: **(20, 2)** standard

### Buy/Sell Pressure Thresholds
- Values: [76.4, 76.9, 69.3, 76.0, 96.0]

## Confidence Score Analysis

| Outcome | Avg Confidence | Min | Max |
|---|---|---|---|
| Wins | 62.2% | 54% | 70% |
| Losses | 65.9% | 65% | 75% |

## Leverage ↔ R:R ↔ Confidence Mapping

| Leverage | Avg Confidence | Primary R:R | Count |
|---|---|---|---|
| 3x | 65% | 1:2.08 | 1 |
| 4x | 62% | 1:1.25 | 6 |
| 5x | 62% | 1:1.43 | 19 |
| 6x | nan% | 1:2.08 | 1 |
| 7x | 66% | 1:2.08 | 22 |

## 🎯 Complete Strategy Specification

### Entry Conditions
1. **Multi-indicator confluence** scoring system:
   - EMA trend alignment (likely 9/21/55 or 9/21/50)
   - MACD signal confirmation
   - RSI position (>50 for LONG, <50 for SHORT)
   - RSI divergence detection (bearish/bullish)
   - Bollinger Band position (standard 20,2)
   - Volume spike detection (vs recent average)
   - Buy/Sell pressure ratio
   - Last candle direction
2. **BTC trend filter**: Prefer Sideways (79% of signals)
3. **Confidence threshold**: Minimum ~54%, likely filtered at 50%

### Position Sizing & Leverage
- Risk per trade: Fixed % of portfolio (recommended 2-3%)
- Leverage tiers mapped to confidence/R:R:
  - **7x**: R:R 1:2.08 (highest confidence)
  - **5x**: R:R 1:1.43 (medium confidence)
  - **4x**: R:R 1:1.25 (lower confidence)

### Take Profit & Stop Loss
- **TP1**: ~4.33% from entry
- **TP2**: ~6.98% from entry (TP2/TP1 ratio: 1.61x)
- **TP3**: ~10.69% from entry (TP3/TP2 ratio: 1.53x)
- **SL**: ~3.82% from entry

### Exit Management (The Core Edge)
```
Signal fires → Enter position 100%
  ├─ TP1 hit → Close 70%, move SL to breakeven
  │   Remaining 30% rides risk-free
  ├─ TP2 hit → Close 20% more, keep 10% moonbag
  │   Remaining 10% rides to TP3
  └─ TP3 hit → Close final 10% (Jackpot)
```

### Risk Management
- Max consecutive losses observed: **4**
- Average time to SL: **10.5h** (longer than TP1)
- BTC anomaly monitoring: Alert if BTC moves >1.5% in <5 min
- Manual close recommended during anomalies