# Go-to-Market: Real Money Deployment Guide

## Overview

This document tracks passport readiness for real-money deployment on Binance Futures.

## The 10 Gates

Every passport must pass ALL 10 gates before receiving real money.

### Backtest Gates (Research Pipeline)
| Gate | Metric | Threshold | Source |
|------|--------|-----------|--------|
| 1 | 180d Return | > 15% | `run_research.py --full-4stage` |
| 2 | Profit Factor | > 1.3 | Stage 1 evaluator |
| 3 | Max Drawdown | < 40% | Stage 1 evaluator |
| 4 | Min Trades | ≥ 50 | Stage 1 evaluator |
| 5 | Win Rate | > 35% | Stage 1 evaluator |
| 6 | MC Robustness | ≥ 70% profitable | Stage 3 evaluator |
| 7 | Orthogonality | Rank 1 in group | Stage 4 evaluator |

### Paper Trading Gates
| Gate | Metric | Threshold | Source |
|------|--------|-----------|--------|
| 8 | Paper Duration | ≥ 30 days | `state.db` equity_snapshots |
| 9 | Paper PnL | > $0 (any profit) | `state.db` equity_snapshots |
| 10 | No Catastrophe | Max single loss < 10% equity | `state.db` positions |

## Running the Scorecard

```bash
# Check all passports
uv run python -c "
from bot.deploy.go_to_market import GoToMarketScorecard
sc = GoToMarketScorecard()
# See go_to_market.py for evaluate_from_db() usage
"

# Check specific passport
uv run python -c "
from bot.deploy.go_to_market import GoToMarketScorecard
sc = GoToMarketScorecard()
result = sc.evaluate_from_db('PressureReader')
print(result.format_table())
"
```

## Kill Switch

- **Threshold:** 30% drawdown from initial equity ($100 → kill at $70)
- **Action:** Passport disabled, Telegram alert sent
- **Recovery:** Manual re-enable only after review
- **Override:** Per-passport via `config_overrides.KILL_SWITCH_THRESHOLD`

## Deployment Checklist

```
□ Passport passes all 10 gates
□ Kill switch threshold confirmed
□ Production state DB initialized (state_prod.db)
□ Binance API keys configured for REAL trading
□ Telegram alerts verified (test notification sent)
□ Daily report cron job enabled
□ Manual confirmation before first real trade
□ Initial equity deposited ($100 per passport)
```

## Current Candidates

| Passport | Gates Passed | Status | Notes |
|----------|-------------|--------|-------|
| (to be populated after exploration completes) | | | |

## History

- **2026-04-14:** Framework created (Session 13)
