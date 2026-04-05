# Pumpradar — Copilot Instructions

## What this project is

**Pumpradar** is an automated Binance Futures paper-trading bot that runs multiple independent strategy "passports" simultaneously. Each passport is a self-contained JSON config with its own indicator weights, thresholds, and trade rules. The bot scans the top-volume altcoin futures pairs on the 1H timeframe, scores confluence across up to 8 technical indicators, and sends trade signals to Telegram.

## North Star & Goals

1. **Find consistently profitable automated strategies** — target: at least 3 passports with >+15% return over 180d, validated across multiple market regimes (bull, bear, sideways).
2. **Build a research engine** that generates, tests, and promotes new passport candidates automatically — reducing manual tuning to exception handling only.
3. **Paper trade first, always** — no real money until a passport has ≥30d of live paper trading with metrics above the PromotionPolicy 7-gate threshold.
4. **Never lose the edge we've already found** — HiddenGem (+25.9%), Sniper (+26.0%), VolumeKing (+9.1%) are the baseline. Any change to their configs requires a backtest showing improvement before deployment.

## Living Documentation (READ THIS FIRST)

These docs are the source of truth. Always read them before starting work, and **update them after every iteration**:

| Doc | Purpose | Update when |
|---|---|---|
| `docs/FINDINGS.md` | All findings, bugs fixed, anti-patterns, proven patterns, backtest results | **After every iteration — non-negotiable** |
| `pumpradar-passports/VERSIONS.md` | Passport version registry | Every passport config change |
| `ops/fight-tres-runbook.md` | VPS deployment and incident procedures | After any infra/deploy change |
| `docs/superpowers/plans/` | Implementation plans and deep-dive analysis | After completing a plan |

**Rule:** If you discover a new bug, fix a regression, find a better parameter combination, or complete a backtest — write it into `docs/FINDINGS.md` before closing the session. Future sessions depend on this.

---

## Build, Test & Run

```bash
# Always use uv — `python` is not in PATH
uv run pytest tests/ -v --tb=short           # full suite (206 tests)
uv run pytest tests/test_backtester_summary.py -v  # single file
uv run pytest tests/ -k "test_list_passports" -v   # single test by name

# Run backtest on new passports (all 14, 90d)
uv run python scripts/run_new_passport_backtest.py --days 90 --pairs 10

# Run research engine (generates + validates new strategies)
uv run python run_research.py --all --max-per-family 5 --days 180

# Live paper trading (VPS only)
python -m bot.main_multi --interval=1h
```

No linter is configured.

## Architecture

This is a Binance Futures paper-trading bot with a multi-passport strategy engine.

### Signal pipeline (one scan cycle)

```
Scanner.scan_all()
  └─ data_fetcher.fetch_klines()          # Binance fapi REST
  └─ scorer.score_confluence()            # 8 indicators → confidence 0–100
       └─ indicators.py                   # calc_ema, calc_macd, calc_rsi, calc_bollinger, etc.
  └─ signals.generate_signal()            # entry + TP1/TP2/TP3/SL levels
  └─ PositionManager.can_open()
  └─ PositionManager.open_position()
```

### Multi-passport isolation

`PassportRunner` in `bot/passport_runner.py` loads every `pumpradar-passports/configs/*.json` at startup. For each passport, before scanning it:
1. Snapshots current `bot/config` module attributes
2. Applies `config_overrides` from the JSON via `setattr(config, k, v)`
3. After scan: **always** restores original values (even on exception)

This means `bot/config.py` is a **mutable global** used as a thread-local-style context. **Never hold a reference to a config value across a passport scan cycle.**

### Scoring engine (`bot/scorer.py`)

- NEUTRAL votes add to `total_weight` but NOT to `long_score`/`short_score` → dilutes `confidence`
- `volume_spike` is directional-confirmation only: below threshold = 0 weight; above = full weight to dominant side (binary cliff)
- BTC Uptrend multiplies final confidence × 0.5 (halves it) — strategies often don't fire in bull markets
- Setting `INDICATOR_WEIGHTS["x"] = 0.0` removes indicator completely (doesn't pollute total_weight)

### Passport JSON schema

```json
{
  "name": "...", "emoji": "...", "version": "0.x",
  "changelog": [{ "version": "0.x", "git_sha": "...", "backtest_180d": {...} }],
  "config_overrides": {
    "INDICATOR_WEIGHTS": {
      "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
      "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
      "pressure": 0.0, "candle_direction": 0.0
    }
  }
}
```

**All 8 `INDICATOR_WEIGHTS` keys are required**, even when `0.0`. Missing keys cause a `KeyError` at scan time. Passports with `"enabled": false` are skipped at load (but open positions are still restored).

### Position lifecycle

```
OPEN → TP1_HIT (70% closed, SL → breakeven) → TP2_HIT (20%) → TP3_HIT/SL_HIT
```
TP cascade percentages: 70 / 20 / 10. After TP1, SL moves to entry price (`sl_is_breakeven = True`).
Risk per trade: 3% of equity. Leverage tiers: 54–60% conf → 4×, 61–69% → 5×, 70%+ → 7×.

### Backtester (`bot/backtester.py`)

- `run_backtest()` runs `_summarize()` **per symbol**, then averages `return_pct` and `max_dd` across active symbols — equal-weight portfolio interpretation
- `backtest_pair()` applies `cfg_override` temporarily via `setattr`; always restores on exit
- Minimum 100 candles per symbol; needs BTC data for `determine_btc_trend_at()` at every candle

### Research engine (`bot/research/`)

4-stage pipeline:
1. `evaluator.py` (Stage 1) — sanity gate: min trades, profit factor > 1.0
2. `evaluator.py` (Stage 2) — regime walk-forward across Bull/Bear/Sideways/HighVol windows
3. `stage3.py` — Monte Carlo parameter perturbation (robustness check)
4. `stage4.py` — orthogonality filter + portfolio construction

`pipeline.py` orchestrates all stages. `tracker.py` persists every experiment to SQLite (`research_experiments.db`). `registry.py` manages passport lifecycle states: `generated → backtested → paper_live → candidate → production → retired → archived`.

### State persistence

- **Live positions:** `bot/state_store.py` → `state.db` (SQLite), tables: `positions`, `equity_snapshots`, `trade_log`
- **Research experiments:** `bot/deploy/state_db.py` → separate SQLite, tables: `passport_state`, `trade_log`, `system_events`
- Paper vs prod isolation via `bot/risk/namespace.py` — separate `.db` files

## Key Conventions

### The Selectivity Principle (most important)

Profitable passports use 2–3 active indicators with others zeroed out. Adding indicators increases NEUTRAL votes → dilutes `total_weight` → lower confidence → more low-quality entries → WR falls.

Proven 180d returns: HiddenGem (EMA+BB+Vol) +25.9%, Sniper (BB+Vol+Candle) +26.0%, VolumeKing +9.1%.
Adding 1 indicator to HiddenGem: +25.9% → -26.8%.

**Never add indicators to a profitable passport without a documented hypothesis.**

### `USE_TRAILING_STOP` is broken — never enable

`trail_dist = abs(entry - original_SL)` is a fixed distance, too tight for 1H crypto candles.
All passports must keep `"USE_TRAILING_STOP": false`. The fix requires an ATR-based formula.

### RSI thresholds are global, not per-passport

`RSI_LONG_THRESHOLD = 50` and `RSI_SHORT_THRESHOLD = 50` are in `bot/config.py` and cannot be overridden per passport. This is why the Reversal strategy is permanently quarantined (`"enabled": false`) — its mean-reversion logic needs RSI < 30 / RSI > 70 but the code hardcodes 50/50.

### Config override safety pattern

When applying passport overrides, always snapshot-then-restore:
```python
original = {k: getattr(config, k) for k in overrides}
try:
    for k, v in overrides.items():
        setattr(config, k, v)
    # ... do work ...
finally:
    for k, v in original.items():
        setattr(config, k, v)
```
`PassportRunner._save_config()` / `_restore_config()` implement this. Any new code that touches `bot/config` during a multi-passport loop must follow this pattern.

### Versioning

Passports use semver `major.minor` in the JSON. Rollback = new version with old params (audit trail preserved). Baseline `v0.1` is always recoverable:
```bash
git show 950e0ec:pumpradar-passports/configs/<file>.json
```

### Environment variables

```
PUMPRADAR_TG_TOKEN   # Telegram bot token
PUMPRADAR_TG_CHAT    # Telegram chat ID
PUMPRADAR_STATE_DB   # SQLite path (default: state.db in cwd)
```
Source from `.env` file (see `ops/env.example`). Never commit secrets.

## VPS Deployment (`fight-tres`)

```bash
ssh fight-tres systemctl status pumpradar.service --no-pager
ssh fight-tres "journalctl -u pumpradar.service -n 100 --no-pager -o short-iso"

# After pushing code:
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && systemctl restart pumpradar.service"
```

Working dir on VPS: `/home/vforvaick/pumpradar-bot`. State DB: `/home/vforvaick/pumpradar-bot/state.db`.
See `ops/fight-tres-runbook.md` for full post-deploy validation checklist.

## Important Files

| File | Purpose |
|---|---|
| `bot/scorer.py` | Confidence scoring — read before changing any indicator weight logic |
| `bot/passport_runner.py` | Multi-passport orchestration + config isolation |
| `bot/config.py` | Mutable global config — single source of truth for all thresholds |
| `bot/backtester.py` | Backtest engine — equal-weight multi-symbol aggregation |
| `bot/position_manager.py` | TP cascade 70/20/10, SL → breakeven logic |
| `bot/research/pipeline.py` | 4-stage research pipeline orchestrator |
| `pumpradar-passports/VERSIONS.md` | Passport version registry |
| `docs/FINDINGS.md` | ⭐ Master findings doc — read first, update last |
| `ops/fight-tres-runbook.md` | VPS deployment and emergency procedures |

## Current Status (as of 2026-04-05 Session 4)

- **Branch:** `fix/strategy-parameter-tuning` — 51 commits ahead of master, PR #1 open
- **Tests:** 206/206 passing
- **Passports:** 19 total (7 original v0.3 + 10 new candidates + reversal_v2 + seasonality_og)
- **VPS:** Running on **old code** (pre-branch). Needs PR merge + deploy to activate all work.
- **Top 90d quality-pair candidates:** MACDDivergence +9.1% (PF=1.39), BBMeanRev +7.7% (PF=1.32)
- **180d v0.1→v0.2:** Momentum BETTER (+10.7pp), Dynamic BETTER (+16.0pp); OG/HiddenGem/Sniper/VolumeKing WORSE — selectivity principle confirmed
- **Research engine:** Fully built (Plans 1–3), never run end-to-end on live data yet
- **Fixed in Session 4:** Trailing stop ATR formula fixed, RSI thresholds now per-passport via config_overrides, weekday filter (SKIP_WEEKDAYS) added
