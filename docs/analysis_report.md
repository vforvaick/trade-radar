# 📊 Pumpradar Signal — Statistical Deep Dive

> Canonical report generated from `data/validated_ledger.csv` and `data/all_messages.json`.
> Analysis of 49 resolved trades (8 still open)
> Period: 2026-02-18 to 2026-03-30
> Methodology: fixed 3% risk-per-trade simulation with 70/20/10 TP cascade and SL-at-risk accounting.

## Overall Performance

| Metric | Value |
|---|---|
| Total resolved | 49 |
| Wins (TP1+) | 28 (57.1%) |
| Losses (SL) | 21 (42.9%) |
| Avg TP1 profit | +20.6% (leveraged) |
| Avg SL loss | -19.6% (leveraged) |
| Profit factor | 1.50 |

## Win Rate by Direction

| Direction | Trades | Wins | Win Rate |
|---|---|---|---|
| LONG | 26 | 13 | 50.0% |
| SHORT | 23 | 15 | 65.2% |

## Equity Curve Simulation

### Results (starting $1,000, 3% risk per trade)

| Strategy | Final Equity | Return | Max Drawdown | Trades |
|---|---|---|---|---|
| All signals | $1,296 | +29.6% | 13.6% | 49 |

## Drawdown & Consecutive Loss Analysis

- Max consecutive losses: **4**
- Consecutive loss streaks: Counter({1: 5, 4: 2, 3: 2, 2: 1})

## Market Validation Summary

- Entries validated against Binance: **0/57**
- Missed TP3s (price reached but not announced): **0**
- Validation note: local Binance Futures requests currently return HTTP 403 for all symbols, so `entry_valid` should be regenerated from an allowed egress host before using market-revalidation metrics.