# Session 13 — Exhaustive Exploration & Go-to-Market Validation

**Date:** 2026-04-14
**Status:** Approved
**Branch:** `feat/cryptopass-overhaul`

## Problem Statement

45 passports are live paper-trading on VPS. The research engine has explored 82% of the strategy parameter space (1,075 of ~1,311 grid combinations across 28 families), producing 83 Stage 2 survivors. However:

1. **Stage 3 (Monte Carlo) and Stage 4 (Portfolio) have never been run** — we don't know which survivors are robust vs overfit.
2. **13 families have 0 Stage 2 survivors** from 544 combined tests — but the user wants a documented "last chance" before retirement.
3. **No framework exists to promote a passport from paper to real money** — no gates, no kill switch, no production namespace.

**North star:** Find 3 passports with >+15% return over 180d, validated across regimes and paper trading, ready for $100 real-money deployment.

## Approach: Sequential 5-Phase Pipeline

```
Phase 1: Last-Chance Round (Tier C families)
    ↓
Phase 2: Grid Completion (Tier A full, Tier B sampled)
    ↓
Phase 3: Stage 3+4 Deep Validation (all S2 survivors)
    ↓
Phase 4: Go-to-Market Infrastructure
    ↓
Phase 5: Nominee Selection & Deployment Prep
```

---

## Phase 1: Family Triage & Last-Chance Round

### Family Classification

Based on research_experiments.db (1,153 passports tested, 14 experiment runs):

#### Tier A — Strong (5 families, 48 S2 survivors)

| Family | Tested | S1 Pass | S2 Pass | S1 Rate |
|--------|--------|---------|---------|---------|
| rsi_momentum | 53 | 39 | **15** | 74% |
| hidden_gem_variant | 52 | 37 | **10** | 71% |
| rsi_bb_reversal | 52 | 40 | **8** | 77% |
| pressure_flow_short | 30 | 16 | **8** | 53% |
| bollinger_breakout | 52 | 14 | **7** | 27% |

**Action:** Complete full parameter grid + Stage 3+4.

#### Tier B — Promising (10 families, 35 S2 survivors)

| Family | Tested | S2 Pass | Action |
|--------|--------|---------|--------|
| vwap_deviation | 34 | 5 | Sample 20 more combos |
| pivot_bounce | 34 | 5 | Sample 20 more combos |
| keltner_breakout | 34 | 5 | Sample 20 more combos |
| williams_reversal | 34 | 3 | Sample 20 more combos |
| supertrend_follow | 34 | 3 | Sample 20 more combos |
| stochastic_reversal | 34 | 3 | Sample 20 more combos |
| sniper_variant | 52 | 3 | Sample 20 more combos |
| obv_trend | 34 | 3 | Sample 20 more combos |
| donchian_breakout | 34 | 3 | Sample 20 more combos |
| balanced_all | 52 | 2 | Sample 20 more combos |

**Action:** Sample 20 additional combos per family. If new S2 survivors emerge → Stage 3+4. Otherwise → retire.

#### Tier C — Dead (13 families, 0 S2 survivors)

| Family | Tested | S1 Pass | S1 Rate | Notes |
|--------|--------|---------|---------|-------|
| mfi_flow | 52 | 0 | 0% | Completely dead |
| pressure_flow_long | 10 | 0 | 0% | Completely dead |
| pressure_momentum_long | 10 | 0 | 0% | Completely dead |
| pressure_reader | 52 | 1 | 2% | Nearly dead |
| volume_spike_breakout | 52 | 4 | 8% | Very low |
| ema_crossover | 52 | 10 | 19% | S1 pass but 0 S2 |
| hull_ma_crossover | 34 | 9 | 26% | S1 pass but 0 S2 |
| cci_divergence | 34 | 8 | 24% | S1 pass but 0 S2 |
| trend_purist | 52 | 15 | 29% | S1 pass but 0 S2 |
| momentum_heavy | 52 | 13 | 25% | S1 pass but 0 S2 |
| macd_divergence | 52 | 19 | 37% | S1 pass but 0 S2 |
| ichimoku_cloud | 34 | 12 | 35% | S1 pass but 0 S2 |
| heikin_ashi_momentum | 34 | 11 | 32% | S1 pass but 0 S2 |

**Action:** Last-chance round — 10 new combos per family (130 total). Specifically target underexplored parameter corners. If still 0 S2 after last-chance → **RETIRED** with documented verdict in FINDINGS.md.

### Retirement Criteria

A family is **RETIRED** when:
- ≥40 variants tested across all runs AND 0 Stage 2 survivors (including last-chance round)
- OR: all parameter combos exhausted with 0 S2 survivors

Retirement means:
1. Family marked `status: retired` in verdict tracker
2. Documented in FINDINGS.md with full statistics
3. Existing live passports from that family get `enabled: false` after 30d paper observation
4. Family removed from future research runs

---

## Phase 2: Grid Completion & Sampling

### Tier A: Full Grid

For the 5 Tier A families, complete all untested parameter combinations:

| Family | Grid Size | Tested | Remaining |
|--------|-----------|--------|-----------|
| hidden_gem_variant | 324 | 52 | ~272 |
| rsi_momentum | 24 | 53 | ~0 (oversampled) |
| rsi_bb_reversal | 81 | 52 | ~29 |
| pressure_flow_short | 12 | 30 | ~0 (oversampled) |
| bollinger_breakout | 144 | 52 | ~92 |

**Estimated new tests:** ~393 combos

### Tier B: Sampled Grid

For 10 Tier B families: 20 new combos per family = 200 new tests.
Sampling strategy: Latin Hypercube over param_ranges to maximize coverage.

### Execution

```bash
# Step 1: Last-chance (Tier C)
uv run python scripts/exhaust_exploration.py --tier c --last-chance 10

# Step 2a: Grid completion (Tier A)
uv run python scripts/exhaust_exploration.py --tier a --full-grid

# Step 2b: Sampling (Tier B)
uv run python scripts/exhaust_exploration.py --tier b --sample 20

# All steps use VPS prefetch for kline data
```

---

## Phase 3: Stage 3+4 Deep Validation

### Stage 3 — Monte Carlo Robustness

Run on ALL Stage 2 survivors (83 existing + new from Phase 1-2).

- **50 Monte Carlo iterations** per survivor
- **±15% parameter perturbation** on all tunable params
- Pass criteria: **≥70% of MC iterations profitable** (return > 0%)
- Additional metric: **Sharpe stability** — std(Sharpe) across MC runs < 0.5

### Stage 4 — Portfolio Optimization

Run on all Stage 3 survivors:

1. **Correlation matrix** — compute return correlation between all survivors
2. **Orthogonality filter** — remove strategies with correlation > 0.7 (keep higher Sharpe)
3. **Portfolio Sharpe maximization** — equal-weight portfolio of top-N uncorrelated strategies
4. **Final ranking** — sorted by portfolio-contribution Sharpe

### Output

Ranked list of strategies with:
- Individual metrics (return, Sharpe, PF, WR, MaxDD)
- MC robustness score (% profitable iterations)
- Correlation group membership
- Portfolio contribution score

---

## Phase 4: Go-to-Market Infrastructure

### 4.1 GoToMarket Scorecard (`bot/deploy/go_to_market.py`)

Automated 10-gate checker:

```python
GATES = {
    # Backtest gates (from research pipeline)
    "gate_1_return": lambda m: m["return_pct_180d"] > 15.0,
    "gate_2_profit_factor": lambda m: m["profit_factor"] > 1.3,
    "gate_3_max_drawdown": lambda m: m["max_drawdown"] < 40.0,
    "gate_4_min_trades": lambda m: m["total_trades"] >= 50,
    "gate_5_win_rate": lambda m: m["win_rate"] > 35.0,
    "gate_6_mc_robust": lambda m: m["mc_profitable_pct"] >= 70.0,
    "gate_7_orthogonal": lambda m: m["correlation_group_rank"] == 1,

    # Paper trading gates
    "gate_8_paper_days": lambda m: m["paper_days"] >= 30,
    "gate_9_paper_pnl": lambda m: m["paper_pnl"] > 0,
    "gate_10_no_catastrophe": lambda m: m["max_single_loss_pct"] < 10.0,
}
```

**CLI:**
```bash
uv run python -m bot.deploy.go_to_market --check-all
uv run python -m bot.deploy.go_to_market --passport HiddenGem --verbose
```

**Output:** Table showing each passport vs each gate (✅/❌), with a final PASS/FAIL.

### 4.2 Kill Switch (`bot/risk/circuit_breaker.py`)

New module integrated into PositionManager:

```python
class CircuitBreaker:
    def __init__(self, kill_threshold_pct: float = 0.30):
        self.kill_threshold_pct = kill_threshold_pct  # 30% drawdown

    def check(self, passport_name: str, current_equity: float, initial_equity: float) -> bool:
        """Returns True if passport should be killed."""
        drawdown = (initial_equity - current_equity) / initial_equity
        if drawdown >= self.kill_threshold_pct:
            # Disable passport + send Telegram alert
            return True
        return False
```

**Integration points:**
- Called in `PassportRunner.scan_passport()` BEFORE attempting to open positions
- On trigger: set passport `enabled: false` in runtime, log to state_db `system_events`, send Telegram alert
- Does NOT close existing positions (let them hit TP/SL naturally)
- Can be overridden per-passport via `config_overrides.KILL_SWITCH_THRESHOLD`

### 4.3 Production Mode Namespace

Extend `bot/risk/namespace.py`:

```python
# Paper mode (existing)
PAPER_DB = "state.db"

# Production mode (new)
PROD_DB = "state_prod.db"

def get_db_path(mode: str = "paper") -> str:
    if mode == "prod":
        return os.environ.get("CRYPTOPASS_PROD_STATE_DB", PROD_DB)
    return os.environ.get("CRYPTOPASS_STATE_DB", PAPER_DB)
```

**Passport-level mode flag:**
```json
{
  "name": "HiddenGem",
  "trading_mode": "prod",  // "paper" (default) or "prod"
  "initial_equity": 100.0,
  "kill_switch_threshold": 0.30
}
```

**Safety:** Production passports use Binance REAL API endpoints. Paper passports use simulated execution. The namespace ensures zero cross-contamination of state.

### 4.4 Daily Telegram Report (`bot/reporting/daily_report.py`)

Automated daily summary sent to Telegram group at 00:00 UTC:

```
📊 Cryptopass Daily Report — 2026-04-15

=== PRODUCTION (Real Money) ===
💰 Total Equity: $297.40 / $300.00 (-0.9%)
📈 HiddenGem: $101.20 (+1.2%) | 2 trades | WR 50%
📉 BBMeanRev: $96.10 (-3.9%) | 3 trades | WR 33%
📈 PressureReader: $100.10 (+0.1%) | 1 trade | WR 100%

=== PAPER TRADING (Top 10) ===
🔥 BreakoutVol: +36.2% | 45 trades | WR 42%
💪 PressureReader: +22.4% | 78 trades | WR 44%
📊 BBMeanRev: +3.0% | 31 trades | WR 47%
...

=== GATE PROGRESS (Top Candidates) ===
RSIMomentumGen2: 7/10 gates ✅ (missing: Gate 8, 9, 10 — paper)
BollingerBreakout: 6/10 gates ✅ (missing: Gate 6, 7, 8, 9)

=== ALERTS ===
⚠️ Kill switch triggered: DynamicGen2 (equity $68 < $70)
🔴 Family retired: mfi_flow (0/62 S2 survivors)
```

**Trigger:** Cron job on VPS or integrated into scan cycle (every 24h).

### 4.5 Family Verdict Tracker

New SQLite table in `research_experiments.db`:

```sql
CREATE TABLE family_verdicts (
    family TEXT PRIMARY KEY,
    tier TEXT NOT NULL,              -- 'A', 'B', 'C'
    total_tested INTEGER DEFAULT 0,
    s1_survivors INTEGER DEFAULT 0,
    s2_survivors INTEGER DEFAULT 0,
    s3_survivors INTEGER DEFAULT 0,
    s4_survivors INTEGER DEFAULT 0,
    last_chance_tested INTEGER DEFAULT 0,
    last_chance_s2 INTEGER DEFAULT 0,
    verdict TEXT DEFAULT 'exploring', -- 'exploring', 'exhausted', 'retired'
    verdict_reason TEXT,
    verdict_date TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## Phase 5: Nominee Selection & Deployment

### Selection Process

After Phases 1-4 complete:

1. Run `go_to_market.py --check-all` to see which passports pass all 10 gates
2. If ≥3 passports pass → select top 3 by portfolio Sharpe contribution
3. If <3 pass → identify which gates are blocking, evaluate if adjustable
4. Selected passports get `trading_mode: "prod"` in their JSON config

### Deployment Checklist

```
□ Passport passes all 10 gates
□ Kill switch threshold configured ($70/passport = 30% drawdown)
□ Production state DB initialized (state_prod.db)
□ Binance API keys configured for REAL trading
□ Telegram alerts verified (test notification sent)
□ Daily report cron job enabled
□ Manual confirmation by user before first real trade
□ Initial equity deposited ($100 per passport)
```

### Post-Deployment Monitoring

- **Daily:** Telegram report (automated)
- **Weekly:** Manual review of all production trades
- **Monthly:** Re-run backtest with latest data, compare vs live performance
- **Kill switch:** Automatic disable at 30% drawdown

---

## Deliverables Summary

| # | Deliverable | New/Modified File | Priority |
|---|------------|-------------------|----------|
| 1 | Family Verdict Tracker | `research_experiments.db` (new table) | Phase 1 |
| 2 | Exploration Runner | `scripts/exhaust_exploration.py` | Phase 1-2 |
| 3 | Stage 3+4 Execution | `bot/research/pipeline.py` (verify works) | Phase 3 |
| 4 | GoToMarket Scorecard | `bot/deploy/go_to_market.py` | Phase 4 |
| 5 | Kill Switch | `bot/risk/circuit_breaker.py` | Phase 4 |
| 6 | Production Namespace | `bot/risk/namespace.py` (extend) | Phase 4 |
| 7 | Daily Telegram Report | `bot/reporting/daily_report.py` | Phase 4 |
| 8 | Docs Update | FINDINGS.md, VERSIONS.md, GO_TO_MARKET.md | Phase 5 |

---

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Exploration approach | Sequential (A) | Most rigorous, retirement verdicts inform go-to-market |
| Tier C retirement | Last-chance round (10 combos/family) | Exhaust before dropping |
| Paper trading minimum | 30 days + 7 PromotionPolicy gates | Consistent with existing framework |
| Real money capital | $100/passport, no auto-scale | Proof of concept, manual scaling |
| Kill switch | 30% drawdown ($70 equity) | Auto-disable, don't close positions |
| Daily report | Telegram summary all passports | Added at user request |
