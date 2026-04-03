# Strategy Discovery Engine + Persistent State

---

## Feature A: Strategy Discovery Engine

> [!IMPORTANT]  
> **Revised:** Bukan sekedar backtest existing 7 passport. Pipeline ini **menemukan varian baru** via automated combinatorics + walk-forward filtering, lalu auto-generate passport JSON untuk yang lolos.

### Architecture

```mermaid
graph LR
    A["Parameter Space<br/>(weights × exits × thresholds)"] --> B["Grid Search Engine<br/>180 days, 15 pairs"]
    B --> C["Walk-Forward Filter<br/>Train 120d → Test 60d"]
    C -->|Overfit Score < 0.4| D["✅ Winners"]
    C -->|Overfit Score ≥ 0.4| E["❌ Killed"]
    D --> F["Auto-generate<br/>Passport JSONs"]
    F --> G["Deploy to<br/>paper trading"]
```

### Parameter Search Space

| Dimension | Values | Count |
|-----------|--------|-------|
| Volume Threshold | 1.5, 2.0, 2.5, 3.0 | 4 |
| Confidence Threshold | 50, 54, 60, 65, 70 | 5 |
| Weight Profiles | 5 presets (see below) | 5 |
| Exit Strategy | Fixed%, ATR, Trailing, ATR+Trailing | 4 |
| **Total combinations** | | **400** |

**Weight Profiles:**
1. **Equal** — semua 1.0
2. **Volume-Heavy** — volume 3.0, pressure 2.0, sisanya 1.0
3. **Trend-Purist** — ema 2.0, macd 2.0, candle 1.5, sisanya 0.5
4. **Reversal** — rsi 2.0, bb 2.0, divergence 2.0, ema/macd 0.0
5. **Minimal** — hanya volume + ema + bb (sisanya 0.0)

> 400 combos × ~2 min/backtest = ~13 jam. Bisa chunked overnight.

---

### Task A1: Discovery Engine Core

#### [NEW] [discovery_engine.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/discovery_engine.py)

```python
class StrategyDiscoveryEngine:
    def __init__(self, symbols, interval, days=180)
    
    def generate_search_space(self) -> list[dict]
        """Generate all parameter combinations."""
    
    def run_discovery(self, max_workers=1) -> list[dict]
        """Run full grid search. Returns sorted results."""
    
    def _backtest_config(self, config_override) -> dict
        """Single backtest run with config. Returns summary + config."""
```

- Reuses existing [backtest_pair()](file:///Users/faiqnau/fight/trading/crypto-signal/bot/backtester.py#36-127) + [_summarize()](file:///Users/faiqnau/fight/trading/crypto-signal/bot/backtester.py#200-234) from [backtester.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/backtester.py)
- Progress reporting: `[Discovery] 42/400 (10.5%) — Best so far: +67% (Vol2.5, Trend-Purist, ATR+Trail)`
- Saves intermediate results to `discovery_results.json` (crash-safe resume)
- Outputs top 20 results sorted by **Sharpe Ratio** (not just return)

#### [MODIFY] [backtester.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/backtester.py)

- Add **Sharpe Ratio** and **Calmar Ratio** to [_summarize()](file:///Users/faiqnau/fight/trading/crypto-signal/bot/backtester.py#200-234)
- Add **Sortino Ratio** (penalizes downside vol only, better for asymmetric strategies)

---

### Task A2: Walk-Forward Validator

#### [NEW] [walk_forward.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/walk_forward.py)

Takes the top N results from discovery and stress-tests them:

```python
def walk_forward_validate(config_override, symbols, interval, 
                          train_days=120, test_days=60) -> dict:
    """
    Returns:
        train_result: backtest on day 1-120
        test_result:  backtest on day 121-180 (never seen during training)
        overfit_score: |train_sharpe - test_sharpe| / train_sharpe
        verdict: KEEP / TUNE / KILL
    """
```

Verdict rules:
- `overfit_score < 0.3` AND `test_return > 0` → ✅ **KEEP**
- `overfit_score 0.3-0.6` AND `test_return > 0` → ⚠️ **TUNE**
- `overfit_score > 0.6` OR `test_return < 0` → ❌ **KILL**

---

### Task A3: Auto-Passport Generator + Report

#### [NEW] [run_discovery.py](file:///Users/faiqnau/fight/trading/crypto-signal/run_discovery.py)

CLI runner:
1. Runs discovery engine (400 combos, ~13 hours overnight)
2. Takes top 20, runs walk-forward validation (~40 min)
3. For each ✅ **KEEP** result → auto-generates passport JSON in `pumpradar-passports/configs/discovered/`
4. Outputs comparison report + sends summary to Telegram

Auto-generated passport example:
```json
{
    "name": "Discovery #7 — VolHeavy ATR Trail",
    "emoji": "🔬",
    "description": "Auto-discovered: Vol 2.5, Trend-Purist weights, ATR+Trailing. Sharpe 2.3, WF-validated.",
    "config_overrides": { ... },
    "metadata": {
        "discovered_at": "2026-03-31",
        "train_return": "+67%",
        "test_return": "+41%",
        "overfit_score": 0.22
    }
}
```

---

## Feature B: Persistent State (unchanged)

### Task B1: StateStore Module

#### [NEW] [state_store.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/state_store.py)

SQLite with 3 tables: [positions](file:///Users/faiqnau/fight/trading/crypto-signal/bot/position_manager.py#62-92), `equity_snapshots`, `trade_log`.

```python
class StateStore:
    def __init__(self, db_path="state.db")
    def save_position(self, passport_name, signal, risk_amount, tg_msg_id=None)
    def update_position(self, pos_id, **kwargs)
    def load_open_positions(self, passport_name=None) -> list[dict]
    def save_equity(self, passport_name, equity)
    def get_last_equity(self, passport_name) -> float
    def log_trade(self, passport_name, trade_data)
    def get_signal_message_id(self, symbol, passport_name) -> int | None
```

### Task B2: Integrate into PassportRunner + Notifier

#### [MODIFY] [passport_runner.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/passport_runner.py)
- Startup: load open positions + equity from DB
- On signal: `save_position()` + store `tg_message_id`
- On TP/SL: [update_position()](file:///Users/faiqnau/fight/trading/crypto-signal/bot/position_manager.py#62-92) + `log_trade()` + `save_equity()`

#### [MODIFY] [notifier.py](file:///Users/faiqnau/fight/trading/crypto-signal/bot/notifier.py)
- Startup: restore `signal_message_ids` from DB

---

## Execution Order

| Phase | Task | Effort | Notes |
|-------|------|--------|-------|
| 1 | **B1** — StateStore | ~150 LOC | Foundation, no deps |
| 2 | **B2** — Integrate persistence | ~80 LOC | Immediate value |
| 3 | **A1** — Discovery Engine | ~200 LOC | Can run overnight |
| 4 | **A2** — Walk-Forward Validator | ~120 LOC | Filters overfit |
| 5 | **A3** — Auto-Passport + Report | ~100 LOC | Deploy winners |

## Verification

### Persistent State
- Start → generate signals → kill → restart → verify state restored
- Verify TG reply threading survives restart

### Discovery Engine
- Smoke test: `python run_discovery.py --combos 10 --days 30 --pairs 3` (~5 min)
- Full run: `python run_discovery.py --days 180 --pairs 15` (overnight)
- Check auto-generated passports are valid JSON and loadable by PassportRunner
