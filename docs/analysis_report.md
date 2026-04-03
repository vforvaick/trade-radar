# 📊 Pumpradar Signal — Statistical Deep Dive

> Analysis of 49 resolved trades (8 still open)
> Period: 2026-02-18 to 2026-03-30

## Overall Performance

| Metric | Value |
|---|---|
| Total resolved | 49 |
| Wins (TP1+) | 28 (57.1%) |
| Losses (SL) | 21 (42.9%) |
| TP1 hit | 28 (57.1%) |
| TP2 hit | 22 (44.9%) |
| TP3 hit | 9 (18.4%) |
| Avg TP1 profit | +20.6% (leveraged) |
| Avg SL loss | -19.6% (leveraged) |
| Profit factor | 1.50 |
| Expectancy/trade | +3.41% |

## Win Rate by Direction

| Direction | Trades | Wins | Win Rate |
|---|---|---|---|
| LONG | 26 | 13 | 50.0% |
| SHORT | 23 | 15 | 65.2% |

## Win Rate by Leverage

| Leverage | Trades | Wins | Win Rate | Avg TP1 Profit | Avg SL Loss |
|---|---|---|---|---|---|
| 3x | 1 | 0 | 0.0% | +nan% | -nan% |
| 4x | 6 | 5 | 83.3% | +11.5% | -14.4% |
| 5x | 19 | 11 | 57.9% | +21.4% | -22.4% |
| 6x | 1 | 1 | 100.0% | +56.8% | -nan% |
| 7x | 22 | 11 | 50.0% | +20.7% | -17.8% |

## Win Rate by Confidence Bucket

| Confidence | Trades | Wins | Win Rate |
|---|---|---|---|
| 54-60% | 4 | 4 | 100.0% |
| 61-69% | 18 | 8 | 44.4% |
| 70-75% | 2 | 1 | 50.0% |

## Win Rate by BTC Trend

| BTC Trend | Trades | Wins | Win Rate |
|---|---|---|---|
| Sideways | 38 | 21 | 55.3% |
| Downtrend | 8 | 6 | 75.0% |
| Uptrend | 3 | 1 | 33.3% |

## Win Rate by Risk/Reward Ratio

| R:R | Trades | Wins | Win Rate |
|---|---|---|---|
| 1:1.87 | 3 | 1 | 33.3% |
| 1:1.88 | 5 | 1 | 20.0% |
| 1:1.43 | 9 | 8 | 88.9% |
| 1:1.25 | 6 | 5 | 83.3% |
| 1:2.08 | 25 | 13 | 52.0% |
| 1:2.87 | 1 | 0 | 0.0% |

## Time Analysis

### Win Rate by Hour (UTC)

| Hour (UTC) | Trades | Wins | Win Rate |
|---|---|---|---|
| 00:00 | 2 | 2 | 100.0% |
| 01:00 | 2 | 2 | 100.0% |
| 08:00 | 6 | 3 | 50.0% |
| 09:00 | 2 | 0 | 0.0% |
| 10:00 | 4 | 4 | 100.0% |
| 11:00 | 7 | 3 | 42.9% |
| 14:00 | 3 | 1 | 33.3% |
| 16:00 | 2 | 1 | 50.0% |
| 18:00 | 2 | 0 | 0.0% |
| 19:00 | 5 | 3 | 60.0% |
| 23:00 | 4 | 3 | 75.0% |

### Win Rate by Day of Week

| Day | Trades | Wins | Win Rate |
|---|---|---|---|
| Monday | 14 | 10 | 71.4% |
| Tuesday | 4 | 2 | 50.0% |
| Wednesday | 6 | 1 | 16.7% |
| Thursday | 6 | 6 | 100.0% |
| Friday | 9 | 1 | 11.1% |
| Saturday | 2 | 2 | 100.0% |
| Sunday | 8 | 6 | 75.0% |

## Duration Analysis

| Metric | Mean | Median |
|---|---|---|
| Time to TP1 | 4.3h | 2.6h |
| Time to SL | 10.5h | 4.2h |

## Drawdown & Consecutive Loss Analysis

- Max consecutive losses: **4**
- Consecutive loss streaks: Counter({1: 5, 4: 2, 3: 2, 2: 1})

## Equity Curve Simulation

### Results (starting $1,000, 3% risk per trade)

| Strategy | Final Equity | Return | Max Drawdown | Trades |
|---|---|---|---|---|
| All signals | $627 | +-37.3% | 37.3% | 49 |
| Confidence ≥65% | $746 | +-25.4% | 25.4% | 20 |
| 7x leverage only | $761 | +-23.9% | 25.1% | 22 |

## Market Validation Summary

- Entries validated against Binance: **49/57** (86%)
- Average slippage on unmatched entries: **0.29%**
- Missed TP3s (price reached but not announced): **0**
- **Conclusion: Signal prices are legitimate** — entries are achievable at or very near claimed prices
