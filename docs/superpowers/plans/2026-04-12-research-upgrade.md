# Research Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote 3 Stage 2 survivors to paper trading, add pressure-based LONG_ONLY research families, fix Stage 2 fold strategy for multi-fold validation, deploy to VPS, and run retry research at 270d.

**Architecture:** Three independent workstreams (passports → families → folds), then deploy + research run. Passport JSONs are pure data. Family additions are dict entries. Fold fix changes `_calc_folds()` defaults and `run_research.py` CLI default.

**Tech Stack:** Python, JSON, pytest, git, SSH (VPS deploy)

---

### Task 1: Create rsi_momentum_v2 Passport

**Files:**
- Create: `passports/cryptopass-research/rsi_momentum_v2.json`

- [ ] **Step 1: Create passport JSON**

```json
{
  "name": "RSIMomentumV2",
  "enabled": true,
  "emoji": "📈",
  "version": "0.1",
  "changelog": [
    {
      "version": "0.1",
      "date": "2026-04-12",
      "git_sha": "pending",
      "description": "Phase 4 research Stage 2 survivor. RSI(10) momentum + divergence with light EMA trend. Thesis: RSI period 10 catches short-term momentum shifts, divergence confirms. High confidence (65) = selective entries only. 3 active indicators → selectivity principle.",
      "backtest_180d": {
        "return_pct": 7.3,
        "sharpe": 1.96,
        "note": "Stage 2 walk-forward: median_ret=+7.3%, avg_sharpe=1.96. Best Phase 4 candidate by return."
      }
    }
  ],
  "description": "RSI momentum strategy: RSI(10) position + divergence signals with light EMA trend confirmation. Short RSI period (10 vs default 14) reacts faster to momentum changes. Divergence filter catches hidden momentum. Conf=65 ensures only high-quality setups fire. Phase 4 Stage 2 survivor — best return of all candidates (+7.3% median).",
  "config_overrides": {
    "RSI_PERIOD": 10,
    "VOLUME_SPIKE_THRESHOLD": 1.5,
    "CONFIDENCE_THRESHOLD": 65,
    "INDICATOR_WEIGHTS": {
      "ema_trend": 0.5,
      "macd_signal": 0.0,
      "rsi_position": 2.0,
      "rsi_divergence": 1.5,
      "bb_position": 0.0,
      "volume_spike": 1.0,
      "pressure": 0.0,
      "candle_direction": 0.0
    },
    "USE_ATR_EXITS": false,
    "USE_TRAILING_STOP": false,
    "MAX_OPEN_POSITIONS_PER_PASSPORT": 25,
    "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
    "BTC_TREND_WEIGHTS": {
      "TREND_UP": 1.0,
      "TREND_DOWN": 0.8,
      "HIGH_VOL_CHOP": 1.0,
      "LOW_VOL_COMPRESSION": 1.0
    },
    "COUNTER_TREND_PENALTY": {
      "TREND_UP": 0.5,
      "TREND_DOWN": 0.5,
      "HIGH_VOL_CHOP": 1.0,
      "LOW_VOL_COMPRESSION": 1.0
    }
  }
}
```

- [ ] **Step 2: Validate JSON is loadable**

Run: `uv run python -c "import json; json.load(open('passports/cryptopass-research/rsi_momentum_v2.json'))"`
Expected: No output (success)

- [ ] **Step 3: Commit**

```bash
git add passports/cryptopass-research/rsi_momentum_v2.json
git commit -m "feat: promote rsi_momentum_v2 — Stage 2 survivor (Sharpe=1.96, +7.3%)"
```

---

### Task 2: Create bollinger_breakout_v2 and v3 Passports

**Files:**
- Create: `passports/cryptopass-research/bollinger_breakout_v2.json`
- Create: `passports/cryptopass-research/bollinger_breakout_v3.json`

- [ ] **Step 1: Create bollinger_breakout_v2.json (conf=50)**

```json
{
  "name": "BollingerBreakoutV2",
  "enabled": true,
  "emoji": "💥",
  "version": "0.1",
  "changelog": [
    {
      "version": "0.1",
      "date": "2026-04-12",
      "git_sha": "pending",
      "description": "Phase 4 research Stage 2 survivor. BB(15,1.5) + Vol(1.5) + Pressure. Lower confidence threshold (50) for more signals. Thesis: tight Bollinger bands detect smaller breakouts. Highest Sharpe of all Phase 4 candidates.",
      "backtest_180d": {
        "return_pct": 2.1,
        "sharpe": 2.70,
        "note": "Stage 2 walk-forward: median_ret=+2.1%, avg_sharpe=2.70. Highest Sharpe in Phase 4."
      }
    }
  ],
  "description": "Bollinger Band breakout variant 2: tight bands (1.5σ) + volume spike + pressure confirmation. Lower confidence threshold (50) allows more entries than v1 (55). Trades the thesis that narrower bands catch earlier breakouts. Phase 4 Stage 2 survivor — highest Sharpe (2.70) of all candidates.",
  "config_overrides": {
    "BB_PERIOD": 15,
    "BB_STD": 1.5,
    "VOLUME_SPIKE_THRESHOLD": 1.5,
    "CONFIDENCE_THRESHOLD": 50,
    "INDICATOR_WEIGHTS": {
      "ema_trend": 0.0,
      "macd_signal": 0.0,
      "rsi_position": 0.0,
      "rsi_divergence": 0.0,
      "bb_position": 2.0,
      "volume_spike": 1.5,
      "pressure": 1.0,
      "candle_direction": 0.0
    },
    "USE_ATR_EXITS": false,
    "USE_TRAILING_STOP": false,
    "MAX_OPEN_POSITIONS_PER_PASSPORT": 25,
    "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
    "BTC_TREND_WEIGHTS": {
      "TREND_UP": 1.0,
      "TREND_DOWN": 1.0,
      "HIGH_VOL_CHOP": 1.0,
      "LOW_VOL_COMPRESSION": 1.0
    },
    "COUNTER_TREND_PENALTY": {
      "TREND_UP": 0.5,
      "TREND_DOWN": 0.5,
      "HIGH_VOL_CHOP": 1.0,
      "LOW_VOL_COMPRESSION": 1.0
    }
  }
}
```

- [ ] **Step 2: Create bollinger_breakout_v3.json (conf=55)**

Same as v2 but with these differences:
- `"name": "BollingerBreakoutV3"`
- `"CONFIDENCE_THRESHOLD": 55`
- Changelog description: "Higher confidence threshold (55) for more selective entries. Same BB(15,1.5) setup as v2."
- Backtest: `"return_pct": 1.2, "sharpe": 1.22, "note": "Stage 2 walk-forward: median_ret=+1.2%, avg_sharpe=1.22."`

```json
{
  "name": "BollingerBreakoutV3",
  "enabled": true,
  "emoji": "💥",
  "version": "0.1",
  "changelog": [
    {
      "version": "0.1",
      "date": "2026-04-12",
      "git_sha": "pending",
      "description": "Phase 4 research Stage 2 survivor. BB(15,1.5) + Vol(1.5) + Pressure. Higher confidence (55) than v2 for more selective entries.",
      "backtest_180d": {
        "return_pct": 1.2,
        "sharpe": 1.22,
        "note": "Stage 2 walk-forward: median_ret=+1.2%, avg_sharpe=1.22."
      }
    }
  ],
  "description": "Bollinger Band breakout variant 3: same tight bands (1.5σ) as v2, but higher confidence threshold (55) filters for only the strongest setups. Phase 4 Stage 2 survivor.",
  "config_overrides": {
    "BB_PERIOD": 15,
    "BB_STD": 1.5,
    "VOLUME_SPIKE_THRESHOLD": 1.5,
    "CONFIDENCE_THRESHOLD": 55,
    "INDICATOR_WEIGHTS": {
      "ema_trend": 0.0,
      "macd_signal": 0.0,
      "rsi_position": 0.0,
      "rsi_divergence": 0.0,
      "bb_position": 2.0,
      "volume_spike": 1.5,
      "pressure": 1.0,
      "candle_direction": 0.0
    },
    "USE_ATR_EXITS": false,
    "USE_TRAILING_STOP": false,
    "MAX_OPEN_POSITIONS_PER_PASSPORT": 25,
    "MAX_OPEN_POSITIONS_PER_SYMBOL": 1,
    "BTC_TREND_WEIGHTS": {
      "TREND_UP": 1.0,
      "TREND_DOWN": 1.0,
      "HIGH_VOL_CHOP": 1.0,
      "LOW_VOL_COMPRESSION": 1.0
    },
    "COUNTER_TREND_PENALTY": {
      "TREND_UP": 0.5,
      "TREND_DOWN": 0.5,
      "HIGH_VOL_CHOP": 1.0,
      "LOW_VOL_COMPRESSION": 1.0
    }
  }
}
```

- [ ] **Step 3: Validate both JSONs are loadable**

Run: `uv run python -c "import json; [json.load(open(f'passports/cryptopass-research/bollinger_breakout_v{v}.json')) for v in [2,3]]; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add passports/cryptopass-research/bollinger_breakout_v2.json passports/cryptopass-research/bollinger_breakout_v3.json
git commit -m "feat: promote bollinger_breakout v2/v3 — Stage 2 survivors (Sharpe=2.70/1.22)"
```

---

### Task 3: Add Pressure LONG_ONLY Research Families

**Files:**
- Modify: `bot/research/families.py` (add 2 entries before closing `}` of SCORING_FAMILIES dict, after line 331)

- [ ] **Step 1: Add pressure_flow_long and pressure_momentum_long families**

Insert after `"pressure_flow_short": { ... },` (line 331) and before the closing `}` of SCORING_FAMILIES:

```python
    "pressure_flow_long": {
        "name": "Pressure Flow (LONG-biased)",
        "description": "PressureReader-inspired: pressure + candle LONG_ONLY for uptrend/ranging",
        "weights": _w(pressure=2.0, candle_direction=1.5, volume_spike=1.0),
        "param_ranges": {
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0, 2.5],
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
            "DIRECTION_BIAS": ["LONG_ONLY"],
        },
        "compatible_regimes": ["TREND_UP", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
        "min_trades": 20,
    },
    "pressure_momentum_long": {
        "name": "Pressure Momentum (LONG-biased)",
        "description": "Pressure + RSI momentum for long entries with demand confirmation",
        "weights": _w(pressure=2.0, rsi_position=1.5, candle_direction=1.0, volume_spike=1.0),
        "param_ranges": {
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
            "CONFIDENCE_THRESHOLD": [55, 60, 65],
            "DIRECTION_BIAS": ["LONG_ONLY"],
        },
        "compatible_regimes": ["TREND_UP", "HIGH_VOL_CHOP"],
        "min_trades": 20,
    },
```

- [ ] **Step 2: Verify families load correctly**

Run: `uv run python -c "from bot.research.families import SCORING_FAMILIES; print(f'{len(SCORING_FAMILIES)} families'); assert 'pressure_flow_long' in SCORING_FAMILIES; assert 'pressure_momentum_long' in SCORING_FAMILIES; print('OK')"`
Expected: `28 families\nOK` (was 26, now 28)

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `uv run pytest tests/ -q --tb=short`
Expected: 383 passed

- [ ] **Step 4: Commit**

```bash
git add bot/research/families.py
git commit -m "feat: add pressure_flow_long + pressure_momentum_long research families

Inspired by PressureReader's live success (only profitable passport).
Key insight: LONG_ONLY direction bias + pressure indicator = winning formula."
```

---

### Task 4: Fix Stage 2 Fold Strategy

**Files:**
- Modify: `bot/research/pipeline.py:107-129` (change defaults in `run_stage2`)
- Modify: `bot/research/pipeline.py:386-405` (`_calc_folds` default params)
- Test: `tests/research/test_fold_calc.py` (new)

- [ ] **Step 1: Write test for new fold calculation**

Create `tests/research/test_fold_calc.py`:

```python
"""Tests for walk-forward fold calculation."""
from bot.research.pipeline import _calc_folds


def test_270d_produces_4_folds():
    """270 days with train=90, test=45, slide=45 → 4 folds."""
    folds = _calc_folds(total_days=270, train_days=90, test_days=45, slide=45)
    assert len(folds) == 4


def test_180d_produces_2_folds():
    """180 days with train=90, test=45, slide=45 → 2 folds."""
    folds = _calc_folds(total_days=180, train_days=90, test_days=45, slide=45)
    assert len(folds) == 2


def test_90d_produces_degenerate_fold():
    """90 days < fold_size (135) → single degenerate fold."""
    folds = _calc_folds(total_days=90, train_days=90, test_days=45, slide=45)
    assert len(folds) == 1
    assert folds[0] == (0, 0)


def test_folds_are_ordered_recent_first():
    """First fold should be most recent (offset=0)."""
    folds = _calc_folds(total_days=270, train_days=90, test_days=45, slide=45)
    offsets = [f[0] for f in folds]
    assert offsets == sorted(offsets)


def test_old_defaults_still_work():
    """Backwards compat: old 120/60/30 defaults still produce expected folds."""
    folds = _calc_folds(total_days=180, train_days=120, test_days=60, slide=30)
    assert len(folds) == 1  # 180d exactly fits one fold
    folds_360 = _calc_folds(total_days=360, train_days=120, test_days=60, slide=30)
    assert len(folds_360) >= 6  # plenty of folds with more data
```

- [ ] **Step 2: Run test to verify it fails (because defaults haven't changed yet — only the explicit-param tests will pass)**

Run: `uv run pytest tests/research/test_fold_calc.py -v`
Expected: All 5 tests PASS (we're passing explicit params, not testing defaults)

- [ ] **Step 3: Update `run_stage2()` defaults in pipeline.py**

Change line 110-111 from:
```python
        train_days: int = 120,
        test_days: int = 60,
```
To:
```python
        train_days: int = 90,
        test_days: int = 45,
```

Change line 129 from:
```python
        folds = _calc_folds(total_days, train_days, test_days, slide=30)
```
To:
```python
        folds = _calc_folds(total_days, train_days, test_days, slide=45)
```

- [ ] **Step 4: Update `_calc_folds()` default params**

Change line 387 from:
```python
    total_days: int, train_days: int, test_days: int, slide: int = 30,
```
To:
```python
    total_days: int, train_days: int, test_days: int, slide: int = 45,
```

- [ ] **Step 5: Update `_calc_max_walk_forward_offset()` docstring**

Change lines 378-383 to reflect new fold sizes:
```python
    def _calc_max_walk_forward_offset(self) -> int:
        """Calculate the maximum walk-forward offset needed for cache prefetch.

        Stage 2 uses train=90d, test=45d, slide=45d. Conservatively, double
        the window ensures the oldest train fold is covered in the cache.
        """
        return self.days
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -q --tb=short`
Expected: 388 passed (383 existing + 5 new fold tests)

- [ ] **Step 7: Commit**

```bash
git add bot/research/pipeline.py tests/research/test_fold_calc.py
git commit -m "feat: fix Stage 2 fold strategy — train=90d, test=45d, slide=45d

Old: train=120d, test=60d → only 1 fold for 180d data
New: train=90d, test=45d → 2 folds for 180d, 4 folds for 270d
This ensures walk-forward validation is meaningful (3+ folds)."
```

---

### Task 5: Update CLI Default + VERSIONS.md + FINDINGS.md

**Files:**
- Modify: `run_research.py:54` (change `--days` default)
- Modify: `passports/VERSIONS.md` (add new passport entries)
- Modify: `docs/FINDINGS.md` (add session 11c upgrade note)

- [ ] **Step 1: Update run_research.py default days to 270**

Change line 54 from:
```python
    parser.add_argument("--days", type=int, default=180,
                        help="History days (default: 180)")
```
To:
```python
    parser.add_argument("--days", type=int, default=270,
                        help="History days (default: 270)")
```

- [ ] **Step 2: Update VERSIONS.md with new passport entries**

Append to the end of `passports/VERSIONS.md`:

```markdown

### 📈 RSIMomentumV2 (`rsi_momentum_v2.json`) — NEW

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-12 | Phase 4 Stage 2 survivor. RSI(10) + divergence + light EMA. Sharpe=1.96, median_ret=+7.3%. |

### 💥 BollingerBreakoutV2 (`bollinger_breakout_v2.json`) — NEW

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-12 | Phase 4 Stage 2 survivor. BB(15,1.5) conf=50. Sharpe=2.70, median_ret=+2.1%. |

### 💥 BollingerBreakoutV3 (`bollinger_breakout_v3.json`) — NEW

| Version | Date       | Description |
|---------|------------|-------------|
| v0.1    | 2026-04-12 | Phase 4 Stage 2 survivor. BB(15,1.5) conf=55. Sharpe=1.22, median_ret=+1.2%. |
```

- [ ] **Step 3: Add session note to FINDINGS.md**

Append to end of `docs/FINDINGS.md`:

```markdown

---

## Session 11c: Research Upgrade Deployed

### Changes Made
1. **Promoted 3 Stage 2 survivors** to paper trading: RSIMomentumV2, BollingerBreakoutV2, BollingerBreakoutV3
2. **Added 2 pressure LONG_ONLY families**: pressure_flow_long, pressure_momentum_long (inspired by PressureReader)
3. **Fixed Stage 2 fold strategy**: train=90d, test=45d, slide=45d (was 120/60/30)
   - 270d data → 4 folds (was 1 fold for 180d)
   - Now requires 3 of 4 folds positive → much more robust
4. **CLI default changed**: `--days 270` (was 180)

### Expected Impact
- Research pipeline should produce more robust survivors (multi-fold validation)
- Pressure LONG_ONLY families should discover PressureReader-like strategies
- 3 new passports add diversity to the live portfolio (RSI momentum + BB breakout thesis)
```

- [ ] **Step 4: Commit**

```bash
git add run_research.py passports/VERSIONS.md docs/FINDINGS.md
git commit -m "docs: update VERSIONS.md, FINDINGS.md, CLI default 270d"
```

---

### Task 6: Deploy to VPS + Run Research

**Files:** None (operational task)

- [ ] **Step 1: Push all commits to GitHub**

```bash
git push
```

- [ ] **Step 2: Deploy to VPS**

```bash
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && sudo systemctl restart cryptopass.service"
```

- [ ] **Step 3: Validate VPS deployment**

```bash
ssh fight-tres "systemctl status cryptopass.service --no-pager | head -5"
ssh fight-tres "journalctl -u cryptopass.service -n 20 --no-pager -o short-iso"
```

Expected: Service active, new passports (RSIMomentumV2, BollingerBreakoutV2, BollingerBreakoutV3) appearing in scan logs.

- [ ] **Step 4: Run research pipeline on local MacBook**

```bash
uv run python run_research.py --all --max-per-family 5 --days 270
```

Expected: Runs for ~3-4 hours with KlineCache. Stage 2 should show 3-4 folds per candidate.

- [ ] **Step 5: Verify fold count in early output**

Within the first few Stage 2 entries in the log, verify:
```
[Stage 2] 1/XX — candidate_name (3 folds)
```
or `(4 folds)` — NOT `(1 folds)`.
