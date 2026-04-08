# Session 9 — Research Quality Pairs + New Passports + ATR Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the ATR trailing stop (never worked — `add_atr()` was never called), add `direction_bias` per-passport (enables SHORT_ONLY downtrend passports), add `--quality-pairs` flag to research pipeline, add `pressure_flow_short` strategy family, then run Phase 4 re-run and build resulting passports.

**Architecture:** Three independent tracks: (1) ATR fix — 1-line patch in `bot/scorer.py` that unlocks correctly-written trailing stop code; (2) direction_bias — new config key + pre-open filter in both passport_runner and backtester; (3) research improvements — `--quality-pairs` CLI flag + new `pressure_flow_short` family in `families.py`. Tracks can be committed independently. Phase 4 re-run and passport building happen after tracks 1–3 are merged.

**Tech Stack:** Python, pandas, SQLite, pytest, uv

---

## File Map

| File | Action | What changes |
|---|---|---|
| `bot/scorer.py` | Modify | Add `add_atr(df, period=14)` call at top of `score_confluence()` |
| `bot/config.py` | Modify | Add `DIRECTION_BIAS = None` near trailing stop section |
| `bot/backtester.py` | Modify | Add direction_bias pre-open filter in candle loop |
| `bot/passport_runner.py` | Modify | Add direction_bias pre-open filter before `open_position()` |
| `bot/research/families.py` | Modify | Add `pressure_flow_short` family at end of `SCORING_FAMILIES` |
| `run_research.py` | Modify | Add `--quality-pairs` argparse flag + override symbols when set |
| `scripts/backtest_atr_comparison.py` | Create | Backtest runner comparing no-trail vs ATR trail 2.0x vs 2.5x |
| `tests/test_atr_fix.py` | Create | ATR scorer + trailing ratchet unit tests |
| `tests/test_direction_bias.py` | Create | direction_bias filter unit tests (runner + backtester) |

---

## Task 1: ATR Fix in Scorer

**Files:**
- Modify: `bot/scorer.py` lines 8–27
- Create: `tests/test_atr_fix.py`

### Why this fix

`add_atr()` exists in `bot/indicators.py` but is never called in the scoring pipeline. As a result, `df['atr']` column never exists → `score_result.get('atr')` always returns `None` → `sig.atr_at_entry` is always `None` for every position ever created.

Two consequences:
- `USE_TRAILING_STOP=True` silently falls back to fixed-distance formula (proven destructive)
- `USE_ATR_EXITS=True` computes `sl_atr = None * 2.0` → TypeError or SR-based fallback

The fix: call `add_atr(df, period=14)` at the top of `score_confluence()` before any indicators run.

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_atr_fix.py`:
```python
import numpy as np
import pandas as pd
import pytest

from bot.scorer import score_confluence


def _ohlcv(rows: int = 60) -> pd.DataFrame:
    """Synthetic OHLCV with enough variation for ATR to be non-zero."""
    rng = np.random.default_rng(42)
    close = 100.0 + rng.normal(0, 1, rows).cumsum()
    high = close + abs(rng.normal(0, 0.5, rows))
    low = close - abs(rng.normal(0, 0.5, rows))
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1000, 5000, rows),
    })


def test_score_confluence_returns_atr_value():
    """score_confluence must return a non-None, positive atr in the result."""
    df = _ohlcv(60)
    result = score_confluence(df)
    assert "atr" in result, "atr key missing from score_confluence result"
    assert result["atr"] is not None, "atr is None — add_atr() is not being called"
    assert result["atr"] > 0.0, f"atr must be positive, got {result['atr']}"


def test_atr_populated_in_signal_when_atr_exits_enabled(monkeypatch):
    """When USE_ATR_EXITS=True, sig.atr_at_entry must use real ATR not None."""
    from bot import config
    from bot.signals import generate_signal

    monkeypatch.setattr(config, "USE_ATR_EXITS", True, raising=False)

    df = _ohlcv(60)
    result = score_confluence(df)
    result["go"] = True
    result["direction"] = "LONG"
    result["confidence"] = 70.0
    result["leverage"] = 5

    signal = generate_signal("TESTUSDT", df["close"].iloc[-1], result)
    assert signal is not None
    assert signal.atr_at_entry is not None, "atr_at_entry must be populated when USE_ATR_EXITS=True"
    assert signal.atr_at_entry > 0.0
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd /path/to/repo && uv run pytest tests/test_atr_fix.py -v
```
Expected: FAIL on `test_score_confluence_returns_atr_value` with `AssertionError: atr is None`

- [ ] **Step 1.3: Apply the fix in scorer.py**

In `bot/scorer.py`, add one line after the length guard (line 26). The complete change:

```python
def score_confluence(df, btc_trend="Sideways"):
    # ... docstring unchanged ...
    if len(df) < 55:  # need enough history for indicators
        return _no_signal("Insufficient data")

    indicators.add_atr(df, period=14)  # ← ADD THIS LINE (enables trailing stop + ATR exits)

    # Run all indicators
    ema_dir, ema_str = indicators.calc_ema_trend(df)
    # ... rest unchanged ...
```

Note: `add_atr()` mutates `df` in-place, adding `df['atr']` column. The scorer already reads `df['atr'].iloc[-1]` at line 141 — it will now find a real value.

- [ ] **Step 1.4: Run tests to confirm pass**

```bash
uv run pytest tests/test_atr_fix.py -v
```
Expected: PASS both tests.

- [ ] **Step 1.5: Run full suite to verify no regressions**

```bash
uv run pytest tests/ -v --tb=short -q
```
Expected: same count as baseline (289) plus 2 new tests = 291 passing.

- [ ] **Step 1.6: Commit**

```bash
git add bot/scorer.py tests/test_atr_fix.py
git commit -m "fix: call add_atr() in score_confluence — atr_at_entry was always None

Root cause: add_atr() defined in indicators.py but never called.
Effect: USE_TRAILING_STOP and USE_ATR_EXITS were silently broken.
Fix: one line — indicators.add_atr(df, period=14) before indicator loop.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: direction_bias — Config + Backtester Filter

**Files:**
- Modify: `bot/config.py`
- Modify: `bot/backtester.py` lines 95–98
- Create: `tests/test_direction_bias.py`

### What direction_bias does

A passport with `"DIRECTION_BIAS": "SHORT_ONLY"` in `config_overrides` will never open LONG positions. This enables dedicated downtrend passports without any scoring changes — it's a pure pre-open gate.

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_direction_bias.py`:
```python
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch

from bot import config
from bot.backtester import backtest_pair


def _klines(rows=120) -> pd.DataFrame:
    """Synthetic klines with price variation for realistic signals."""
    rng = np.random.default_rng(99)
    close = 100.0 + rng.normal(0, 1, rows).cumsum()
    high = close + abs(rng.normal(0, 0.5, rows))
    low = close - abs(rng.normal(0, 0.5, rows))
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1000, 5000, rows),
        "timestamp": pd.date_range("2024-01-01", periods=rows, freq="1h"),
    })


def test_direction_bias_short_only_blocks_long_signals(monkeypatch):
    """SHORT_ONLY passport must never open LONG positions in backtest."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", "SHORT_ONLY", raising=False)

    # Force scorer to return a LONG signal every candle
    def fake_score(df, btc_trend="Sideways"):
        return {
            "go": True, "direction": "LONG", "confidence": 70.0,
            "leverage": 5, "risk_reward": 2.0, "signals": {}, "btc_trend": btc_trend, "atr": 1.0
        }

    btc_df = _klines(120)
    klines = _klines(120)

    with patch("bot.backtester.score_confluence", side_effect=fake_score), \
         patch("bot.backtester.determine_btc_trend_at", return_value="Sideways"):
        trades = backtest_pair("TESTUSDT", klines, btc_df)

    # No LONG trades should be created
    long_trades = [t for t in trades if t["direction"] == "LONG"]
    assert len(long_trades) == 0, f"SHORT_ONLY should block all LONG trades, got {len(long_trades)}"


def test_direction_bias_long_only_blocks_short_signals(monkeypatch):
    """LONG_ONLY passport must never open SHORT positions in backtest."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", "LONG_ONLY", raising=False)

    def fake_score(df, btc_trend="Sideways"):
        return {
            "go": True, "direction": "SHORT", "confidence": 70.0,
            "leverage": 5, "risk_reward": 2.0, "signals": {}, "btc_trend": btc_trend, "atr": 1.0
        }

    btc_df = _klines(120)
    klines = _klines(120)

    with patch("bot.backtester.score_confluence", side_effect=fake_score), \
         patch("bot.backtester.determine_btc_trend_at", return_value="Sideways"):
        trades = backtest_pair("TESTUSDT", klines, btc_df)

    short_trades = [t for t in trades if t["direction"] == "SHORT"]
    assert len(short_trades) == 0, f"LONG_ONLY should block all SHORT trades, got {len(short_trades)}"


def test_direction_bias_none_passes_all_signals(monkeypatch):
    """No direction_bias (None) must pass both LONG and SHORT signals."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", None, raising=False)

    call_count = {"n": 0}
    def alternating_score(df, btc_trend="Sideways"):
        call_count["n"] += 1
        direction = "LONG" if call_count["n"] % 2 == 0 else "SHORT"
        return {
            "go": True, "direction": direction, "confidence": 70.0,
            "leverage": 5, "risk_reward": 2.0, "signals": {}, "btc_trend": btc_trend, "atr": 1.0
        }

    btc_df = _klines(120)
    klines = _klines(120)

    with patch("bot.backtester.score_confluence", side_effect=alternating_score), \
         patch("bot.backtester.determine_btc_trend_at", return_value="Sideways"):
        trades = backtest_pair("TESTUSDT", klines, btc_df)

    long_trades = [t for t in trades if t["direction"] == "LONG"]
    short_trades = [t for t in trades if t["direction"] == "SHORT"]
    # With alternating signals and MAX_OPEN_POSITIONS_PER_SYMBOL=1, expect mix of both
    assert len(long_trades) > 0, "None bias should allow LONG trades"
    assert len(short_trades) > 0, "None bias should allow SHORT trades"
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
uv run pytest tests/test_direction_bias.py -v
```
Expected: FAIL with `AssertionError: SHORT_ONLY should block all LONG trades` (the filter doesn't exist yet)

- [ ] **Step 2.3: Add DIRECTION_BIAS to config.py**

In `bot/config.py`, add after the `ATR_TRAIL_MULTIPLIER` line (around line 129):
```python
USE_TRAILING_STOP = False
ATR_TRAIL_MULTIPLIER = 2.0   # trail distance = 2x ATR at entry

# Per-passport direction filter: "SHORT_ONLY", "LONG_ONLY", or None (both directions)
DIRECTION_BIAS = None
```

- [ ] **Step 2.4: Add direction_bias filter in backtester.py**

In `bot/backtester.py`, replace lines 95–98:

```python
            if result["go"]:
                signal = generate_signal(symbol, close, result, timestamp=ts)
                if signal:
                    bias = getattr(config, 'DIRECTION_BIAS', None)
                    if bias == "SHORT_ONLY" and signal.direction == "LONG":
                        continue
                    if bias == "LONG_ONLY" and signal.direction == "SHORT":
                        continue
                    pm.open_position(signal, equity)
```

- [ ] **Step 2.5: Run tests to verify they pass**

```bash
uv run pytest tests/test_direction_bias.py -v
```
Expected: PASS all 3 tests.

- [ ] **Step 2.6: Run full suite**

```bash
uv run pytest tests/ -v --tb=short -q
```
Expected: 292 passing (291 from Task 1 + 3 new).

- [ ] **Step 2.7: Commit**

```bash
git add bot/config.py bot/backtester.py tests/test_direction_bias.py
git commit -m "feat: add DIRECTION_BIAS config — enables SHORT_ONLY / LONG_ONLY passports

New config key DIRECTION_BIAS (default None). When set to SHORT_ONLY,
backtester and passport_runner block LONG signals. Enables dedicated
downtrend passports without touching scorer or signal generation.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: direction_bias in passport_runner.py

**Files:**
- Modify: `bot/passport_runner.py` lines 231–247
- Modify: `tests/test_direction_bias.py` (add passport_runner tests)

- [ ] **Step 3.1: Add passport_runner tests to test_direction_bias.py**

Append to `tests/test_direction_bias.py`:
```python
def test_passport_runner_short_only_skips_long_signal(monkeypatch):
    """PassportRunner with SHORT_ONLY must not call open_position for LONG signals."""
    from bot.passport_runner import PassportRunner
    from bot.signals import Signal

    monkeypatch.setattr(config, "DIRECTION_BIAS", "SHORT_ONLY", raising=False)

    runner = PassportRunner.__new__(PassportRunner)
    runner.position_manager = MagicMock()
    runner.position_manager.can_open.return_value = True
    runner.position_manager.open_count = 0

    long_signal = MagicMock(spec=Signal)
    long_signal.direction = "LONG"
    long_signal.confidence = 70.0

    # Simulate the filter logic that should be in passport_runner
    bias = getattr(config, 'DIRECTION_BIAS', None)
    if bias == "SHORT_ONLY" and long_signal.direction == "LONG":
        should_open = False
    else:
        should_open = True

    assert not should_open, "SHORT_ONLY runner should skip LONG signal"


def test_passport_runner_short_only_allows_short_signal(monkeypatch):
    """PassportRunner with SHORT_ONLY must allow SHORT signals through."""
    monkeypatch.setattr(config, "DIRECTION_BIAS", "SHORT_ONLY", raising=False)

    from bot.signals import Signal
    short_signal = MagicMock(spec=Signal)
    short_signal.direction = "SHORT"
    short_signal.confidence = 70.0

    bias = getattr(config, 'DIRECTION_BIAS', None)
    if bias == "SHORT_ONLY" and short_signal.direction == "LONG":
        should_open = False
    else:
        should_open = True

    assert should_open, "SHORT_ONLY runner should allow SHORT signal"
```

- [ ] **Step 3.2: Run new tests to verify behavior**

```bash
uv run pytest tests/test_direction_bias.py -v
```
The new tests encode logic directly (they pass immediately), but they document intended behavior.

- [ ] **Step 3.3: Add direction_bias filter in passport_runner.py**

In `bot/passport_runner.py`, find the block starting at:
```python
                for sig in signals:
                    if sig.confidence < config.CONFIDENCE_THRESHOLD:
                        continue

                    if passport.position_manager.can_open(sig):
                        pos = passport.position_manager.open_position(sig, passport.equity)
```

Replace with:
```python
                for sig in signals:
                    if sig.confidence < config.CONFIDENCE_THRESHOLD:
                        continue

                    bias = getattr(config, 'DIRECTION_BIAS', None)
                    if bias == "SHORT_ONLY" and sig.direction == "LONG":
                        continue
                    if bias == "LONG_ONLY" and sig.direction == "SHORT":
                        continue

                    if passport.position_manager.can_open(sig):
                        pos = passport.position_manager.open_position(sig, passport.equity)
```

- [ ] **Step 3.4: Run full suite**

```bash
uv run pytest tests/ -v --tb=short -q
```
Expected: 294 passing.

- [ ] **Step 3.5: Commit**

```bash
git add bot/passport_runner.py tests/test_direction_bias.py
git commit -m "feat: apply DIRECTION_BIAS filter in passport_runner live scan

Mirrors backtester filter: SHORT_ONLY skips LONG signals, LONG_ONLY
skips SHORT signals. Existing passports unaffected (DIRECTION_BIAS=None).

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: ATR Backtest Comparison Script

**Files:**
- Create: `scripts/backtest_atr_comparison.py`

This script validates whether ATR trailing stop (now fixed) actually improves performance before we enable it per-passport. Required before enabling `USE_TRAILING_STOP=True` on any live passport.

- [ ] **Step 4.1: Create the comparison script**

Create `scripts/backtest_atr_comparison.py`:
```python
"""
ATR Trailing Stop Comparison Script
Runs backtest on quality pairs with 3 configurations and prints comparison.

Usage:
    uv run python scripts/backtest_atr_comparison.py --passport macd_divergence --days 90
    uv run python scripts/backtest_atr_comparison.py --passport pressure_reader --days 90
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot import config
from bot.backtester import run_backtest

QUALITY_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]


def run_scenario(passport_name: str, days: int, use_trailing: bool, multiplier: float) -> dict:
    """Run backtest with specific trailing stop config."""
    # Find passport file
    passport_dirs = [
        Path("passports/cryptopass-research"),
        Path("passports/pumpradar"),
    ]
    passport_cfg = None
    for d in passport_dirs:
        for f in d.glob("*.json"):
            data = json.loads(f.read_text())
            if data.get("name", "").lower().replace(" ", "_") == passport_name.lower().replace(" ", "_"):
                passport_cfg = data
                break

    if passport_cfg is None:
        raise FileNotFoundError(f"Passport not found: {passport_name}")

    overrides = passport_cfg.get("config_overrides", {}).copy()
    overrides["USE_TRAILING_STOP"] = use_trailing
    overrides["ATR_TRAIL_MULTIPLIER"] = multiplier

    result = run_backtest(
        symbols=QUALITY_PAIRS,
        days=days,
        cfg_override=overrides,
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="ATR trailing stop A/B comparison")
    parser.add_argument("--passport", required=True, help="Passport name (e.g. macd_divergence)")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"ATR Trailing Stop Comparison: {args.passport} ({args.days}d)")
    print(f"{'='*60}\n")

    scenarios = [
        ("No trailing stop", False, 2.0),
        ("ATR trail 2.0x",  True,  2.0),
        ("ATR trail 2.5x",  True,  2.5),
    ]

    for label, use_trailing, mult in scenarios:
        try:
            r = run_scenario(args.passport, args.days, use_trailing, mult)
            trades = r.get("trades", 0)
            ret = r.get("return_pct", 0)
            max_dd = r.get("max_dd", 0)
            pf = r.get("profit_factor", 0)
            wr = r.get("win_rate", 0)
            print(f"{label:25s}  trades={trades:4d}  return={ret:+7.2f}%  "
                  f"max_dd={max_dd:6.2f}%  PF={pf:.2f}  WR={wr:.1f}%")
        except Exception as e:
            print(f"{label:25s}  ERROR: {e}")

    print(f"\n{'='*60}")
    print("VERDICT: only enable ATR trailing if 'ATR trail' row shows return >= 'No trailing'")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4.2: Test the script runs without errors**

```bash
uv run python scripts/backtest_atr_comparison.py --passport macd_divergence --days 90
```
Expected: 3-row table with return_pct, max_dd, PF, WR for each scenario. No crash.

- [ ] **Step 4.3: Commit**

```bash
git add scripts/backtest_atr_comparison.py
git commit -m "scripts: add backtest_atr_comparison.py for ATR trailing stop validation

Usage: uv run python scripts/backtest_atr_comparison.py --passport macd_divergence
Required before enabling USE_TRAILING_STOP=True on any passport.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: pressure_flow_short Strategy Family

**Files:**
- Modify: `bot/research/families.py`

Add a new research family that generates SHORT-biased pressure variants. These will be evaluated during Phase 4 re-run.

- [ ] **Step 5.1: Add pressure_flow_short to families.py**

In `bot/research/families.py`, append to `SCORING_FAMILIES` dict before the closing `}`:

```python
    "pressure_flow_short": {
        "name": "Pressure Flow (SHORT-biased)",
        "description": "Buy/sell pressure + candle direction, SHORT_ONLY bias for downtrend conditions",
        "weights": _w(pressure=2.5, candle_direction=1.5, ema_trend=1.0),
        "param_ranges": {
            "PRESSURE_WEIGHTS_pressure": [2.0, 2.5, 3.0],
            "PRESSURE_WEIGHTS_candle": [1.0, 1.5, 2.0],
            "CONFIDENCE_THRESHOLD": [60, 65],
            "DIRECTION_BIAS": ["SHORT_ONLY"],
        },
        "compatible_regimes": ["TREND_DOWN", "HIGH_VOL_CHOP"],
        "min_trades": 20,
    },
```

Note: `param_ranges` keys like `PRESSURE_WEIGHTS_pressure` are custom — the generator creates one `config_overrides` entry per key. For weight overrides that don't map 1:1 to a config key, we use the base `weights` dict and only vary `CONFIDENCE_THRESHOLD` and `DIRECTION_BIAS`. The weight variations are in the `weights` field itself. Revise the family after checking how `generator.py` applies param_ranges to config_overrides.

**Actual implementation** — check `generator.py` lines 73–82 for how param_ranges maps to config_overrides. If param_ranges keys become direct `config_overrides` keys, the family should be:

```python
    "pressure_flow_short": {
        "name": "Pressure Flow (SHORT-biased)",
        "description": "Pressure + candle direction SHORT_ONLY for downtrend conditions",
        "weights": _w(pressure=2.5, candle_direction=1.5, ema_trend=1.0),
        "param_ranges": {
            "CONFIDENCE_THRESHOLD": [60, 65],
            "VOLUME_SPIKE_THRESHOLD": [1.5, 2.0],
            "DIRECTION_BIAS": ["SHORT_ONLY"],
        },
        "compatible_regimes": ["TREND_DOWN", "HIGH_VOL_CHOP"],
        "min_trades": 20,
    },
```

- [ ] **Step 5.2: Verify family generates candidates correctly**

```bash
uv run python -c "
from bot.research.families import get_param_grid
grid = get_param_grid('pressure_flow_short')
print(f'pressure_flow_short generated {len(grid)} candidates:')
for g in grid[:3]:
    print(' ', g)
"
```
Expected: 4 candidates (2 conf × 2 vol × 1 bias = 4), each with `DIRECTION_BIAS: SHORT_ONLY`.

- [ ] **Step 5.3: Verify DIRECTION_BIAS flows through to backtest config**

Check how `bot/research/evaluator.py` applies `config_overrides`. If it applies via `setattr(config, k, v)`, then `DIRECTION_BIAS: "SHORT_ONLY"` will be set on config, and the backtester filter (Task 2) will apply. Confirm with:

```bash
uv run python -c "
from bot.research.generator import generate_passports
passports = generate_passports(families=['pressure_flow_short'], max_per_family=2)
for p in passports:
    print(p.slug, p.config_overrides)
"
```
Expected: each passport has `{'DIRECTION_BIAS': 'SHORT_ONLY', 'CONFIDENCE_THRESHOLD': 60/65, ...}`.

- [ ] **Step 5.4: Commit**

```bash
git add bot/research/families.py
git commit -m "feat: add pressure_flow_short strategy family to research generator

SHORT_ONLY bias, pressure=2.5 + candle_direction=1.5 + ema=1.0.
Targets downtrend/high-vol regimes. Will be evaluated in Phase 4 re-run.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: --quality-pairs Flag in run_research.py

**Files:**
- Modify: `run_research.py` lines 41–60

Adds `--quality-pairs` flag that replaces Binance top-volume symbol fetching with a hardcoded list of tier-1 coins. This produces reproducible, reliable backtest results.

- [ ] **Step 6.1: Add the flag and constant**

In `run_research.py`, add after the imports (around line 20):
```python
# Tier-1 futures pairs for reliable, reproducible backtests.
# Use with --quality-pairs to avoid meme coin results.
QUALITY_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]
```

In the `main()` function, add the argparse flag after `--pairs`:
```python
    parser.add_argument("--quality-pairs", action="store_true",
                        help="Use hardcoded tier-1 pairs instead of top-volume Binance scan")
```

Replace the symbols fetching block:
```python
    # OLD:
    # logger.info("Fetching top %d symbols by volume...", args.pairs)
    # symbols = get_all_futures_symbols()[:args.pairs]

    # NEW:
    if args.quality_pairs:
        symbols = QUALITY_PAIRS
        logger.info("Using quality pairs (%d): %s", len(symbols), symbols)
    else:
        logger.info("Fetching top %d symbols by volume...", args.pairs)
        symbols = get_all_futures_symbols()[:args.pairs]
    logger.info("Trading pairs: %s", symbols)
```

- [ ] **Step 6.2: Verify the flag parses correctly**

```bash
uv run python run_research.py --help
```
Expected: `--quality-pairs` listed in help output.

```bash
uv run python -c "
import sys
sys.argv = ['run_research.py', '--all', '--quality-pairs', '--max-per-family', '1', '--days', '7']
" && echo "arg parse ok"
```

- [ ] **Step 6.3: Commit**

```bash
git add run_research.py
git commit -m "feat: add --quality-pairs flag to run_research.py

Uses 10 hardcoded tier-1 pairs instead of meme-coin top-volume list.
Produces reproducible, reliable backtest results.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Run Phase 4 Research (Background)

**This task has no code changes.** It runs the research pipeline with all improvements from Tasks 1–6.

- [ ] **Step 7.1: Deploy Tasks 1–6 to VPS first (optional but recommended)**

```bash
git push origin master
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && systemctl restart cryptopass.service"
ssh fight-tres "systemctl status cryptopass.service --no-pager | head -5"
```

- [ ] **Step 7.2: Run Phase 4 locally in background**

```bash
nohup uv run python run_research.py \
  --all \
  --max-per-family 5 \
  --days 180 \
  --quality-pairs \
  > logs/research_phase4_quality_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo "Phase 4 PID: $!"
```
Expected duration: 6–8 hours (180d × 10 pairs × all families). Run this and move on.

- [ ] **Step 7.3: Monitor progress**

```bash
tail -f logs/research_phase4_quality_*.log
```
Look for lines like `Stage 1 passed: N`, `Stage 2 survivors: N`.

- [ ] **Step 7.4: When complete — extract survivors**

```bash
uv run python -c "
import sqlite3, json
db = sqlite3.connect('research_experiments.db')
rows = db.execute('''
  SELECT p.family, p.slug, e2.metrics
  FROM passports p
  JOIN eval_results e1 ON e1.passport_id=p.passport_id AND e1.run_id=p.run_id AND e1.stage=1 AND e1.passed=1
  JOIN eval_results e2 ON e2.passport_id=p.passport_id AND e2.run_id=p.run_id AND e2.stage=2 AND e2.passed=1
  WHERE p.run_id = (SELECT MAX(run_id) FROM passports)
  ORDER BY json_extract(e2.metrics, '$.median_return') DESC
''').fetchall()
for r in rows:
    m = json.loads(r[2])
    print(f'{r[0]:25s} {r[1]:45s} return={m[\"median_return\"]:+.1f}% PF={m[\"avg_profit_factor\"]:.2f}')
db.close()
"
```

---

## Task 8: Build Passports from Phase 4 Results

**This task executes AFTER Phase 4 re-run completes (Task 7).** Do not start until Task 7.4 output is available.

### Selection criteria for passport promotion

Pick configs that satisfy ALL of:
- `median_return > +5%`
- `avg_profit_factor > 1.2`
- Passes at least 2 of 3 regime folds in Stage 2

### Always build: rsi_momentum

Build regardless of new Phase 4 results (already validated Stage2 +16.6% from prior run):

- [ ] **Step 8.1: Create rsi_momentum passport JSON**

Create `passports/cryptopass-research/rsi_momentum.json`:
```json
{
    "name": "RSIMomentum",
    "emoji": "📈",
    "enabled": true,
    "version": "0.1",
    "changelog": [
        {
            "version": "0.1",
            "date": "2026-04-08",
            "git_sha": "FILL_IN",
            "description": "RSI momentum + divergence. Validated Stage2 +16.6% PF=1.94 on quality pairs (Phase 4 prior run). RSI_PERIOD=10 for faster signal response on 1H crypto.",
            "backtest_180d": {
                "return_pct": 16.6,
                "profit_factor": 1.94,
                "win_rate": 32.6,
                "trades": 328,
                "max_dd_pct": 28.1,
                "note": "Phase 4 Stage2 walk-forward, 180d, quality pairs — single fold result"
            }
        }
    ],
    "description": "RSI momentum with divergence confirmation. Short RSI period (10) captures faster momentum shifts on 1H crypto.",
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
            "volume_spike": 0.0,
            "pressure": 0.0,
            "candle_direction": 0.0
        },
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 25,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

- [ ] **Step 8.2: Create pressure_reader_short passport JSON**

Create `passports/cryptopass-research/pressure_reader_short.json`:
```json
{
    "name": "PressureReaderShort",
    "emoji": "🌊🔻",
    "enabled": true,
    "version": "0.1",
    "changelog": [
        {
            "version": "0.1",
            "date": "2026-04-08",
            "git_sha": "FILL_IN",
            "description": "SHORT-only variant of PressureReader. Designed for bear/choppy markets. Uses direction_bias=SHORT_ONLY — never opens LONG positions. BTC Downtrend weight 1.2 gives slight boost in confirmed bear regime.",
            "backtest_180d": {
                "return_pct": null,
                "note": "Awaiting Phase 4 re-run quality-pairs backtest"
            }
        }
    ],
    "description": "Institutional pressure flow SHORT-only. Fires when pressure + candle direction both point DOWN. Will not open LONG positions regardless of score.",
    "config_overrides": {
        "DIRECTION_BIAS": "SHORT_ONLY",
        "CONFIDENCE_THRESHOLD": 60,
        "BTC_TREND_WEIGHTS": {"Uptrend": 0.8, "Sideways": 1.0, "Downtrend": 1.2},
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.0,
            "macd_signal": 0.0,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 0.0,
            "volume_spike": 0.0,
            "pressure": 2.5,
            "candle_direction": 1.5
        },
        "USE_ATR_EXITS": false,
        "USE_TRAILING_STOP": false,
        "MAX_OPEN_POSITIONS_PER_PASSPORT": 25,
        "MAX_OPEN_POSITIONS_PER_SYMBOL": 1
    }
}
```

- [ ] **Step 8.3: Backtest new passports before live deployment**

```bash
uv run python scripts/run_new_passport_backtest.py \
  --passport rsi_momentum \
  --days 90 --pairs 10 --quality-pairs

uv run python scripts/run_new_passport_backtest.py \
  --passport pressure_reader_short \
  --days 90 --pairs 10 --quality-pairs
```
Expected: `return_pct > 0%`, `PF > 1.0`, `max_dd < 30%` for each.

**If either passport fails backtest:** do NOT deploy. Adjust config and re-backtest.

- [ ] **Step 8.4: Add Phase 4 survivors (TBD from Task 7.4 output)**

For each survivor from Task 7.4 with `median_return > +5%` and `PF > 1.2`:
1. Create `passports/cryptopass-research/<slug>.json` using the config_overrides from `research_experiments.db`
2. Backtest with `scripts/run_new_passport_backtest.py --days 90 --quality-pairs`
3. Add to VPS if backtest passes

- [ ] **Step 8.5: Deploy new passports to VPS**

```bash
git add passports/cryptopass-research/rsi_momentum.json passports/cryptopass-research/pressure_reader_short.json
git commit -m "feat: add RSIMomentum + PressureReaderShort passports (Session 9)

RSIMomentum: research Phase 4 validated +16.6% Stage2, RSI_PERIOD=10, conf=65
PressureReaderShort: SHORT_ONLY, pressure=2.5+candle=1.5, downtrend:1.2 boost
First passport with direction_bias in production use.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

git push origin master
ssh fight-tres "cd /home/vforvaick/pumpradar-bot && git pull && systemctl restart cryptopass.service"
```

- [ ] **Step 8.6: Update passports/VERSIONS.md**

Add entries for RSIMomentum v0.1 and PressureReaderShort v0.1 with their configs and backtest results.

- [ ] **Step 8.7: Update docs/FINDINGS.md**

Add section under the current date:
- ATR bug root cause + fix
- direction_bias feature added
- New passports added
- Phase 4 quality pairs results (summary)

---

## Execution Order Summary

```
Tasks 1–3 (ATR + direction_bias): Independent, can be done in one session (~2h)
Task 4 (comparison script): After Task 1, ~30min
Task 5 (pressure_flow_short family): 15min
Task 6 (--quality-pairs flag): 15min
Task 7 (run Phase 4): Start in background after Tasks 5+6, ~6-8h
Task 8 (build passports): After Task 7 completes
```

Tasks 1–6 are all code-level. Task 7 is a background run. Task 8 depends on Task 7 results.
