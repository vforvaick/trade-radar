# Per-Passport Regime Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each passport only trades in its assigned market regimes. Wrong-regime trades are hard-gated. Per-regime risk parameters can be tuned per passport.

**Architecture:** Three layers applied in `run_scan_cycle()`: (1) hard gate via `active_regimes` skips scan entirely, (2) `config_overrides` applied as baseline, (3) `regime_params[current_regime]` overlaid on top. All config changes are snapshotted and restored per passport.

**Tech Stack:** Python, pytest, JSON passport configs, bot/config.py mutable globals

**Spec:** `docs/superpowers/specs/2026-04-12-regime-optimization-design.md`

---

**⚠️ IMPORTANT: Config Field Name Corrections**

The spec uses simplified names. The actual `bot/config.py` field names are:
| Spec Name | Actual Config Attribute | Type |
|-----------|----------------------|------|
| `RISK_PER_TRADE` | `RISK_PER_TRADE_PCT` | float (0.5 = 0.5%) |
| `MAX_OPEN_POSITIONS` | `MAX_OPEN_POSITIONS_PER_PASSPORT` | int |
| `CONFIDENCE_THRESHOLD` | `CONFIDENCE_THRESHOLD` | int ✅ |
| `DIRECTION_BIAS` | `DIRECTION_BIAS` | str/None ✅ |
| `USE_TRAILING_STOP` | `USE_TRAILING_STOP` | bool ✅ |
| `ATR_TRAIL_MULTIPLIER` | `ATR_TRAIL_MULTIPLIER` | float ✅ |

All `regime_params` keys in passport JSONs MUST use the **actual** config attribute names since the code does `setattr(config, key, value)`.

---

### Task 1: Passport Model — Load `regime_params`

**Files:**
- Modify: `bot/passport_runner.py:25-44` (Passport class)
- Modify: `tests/test_passport_runner_regime.py` (add new tests)

- [ ] **Step 1: Write failing tests for `regime_params` loading**

Add to `tests/test_passport_runner_regime.py`:

```python
def test_regime_params_loaded_from_json():
    """Passport loads regime_params from JSON config."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestRegimeParams",
        "emoji": "🧪",
        "active_regimes": ["TREND_UP", "TREND_DOWN"],
        "regime_params": {
            "TREND_UP": {"CONFIDENCE_THRESHOLD": 54},
            "TREND_DOWN": {"CONFIDENCE_THRESHOLD": 60}
        },
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_rp.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore") as MockStateStore:
            _make_mock_state_store(MockStateStore)
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    assert passport.regime_params == {
        "TREND_UP": {"CONFIDENCE_THRESHOLD": 54},
        "TREND_DOWN": {"CONFIDENCE_THRESHOLD": 60}
    }


def test_regime_params_defaults_to_empty_dict():
    """Passport without regime_params defaults to empty dict."""
    from bot.passport_runner import PassportRunner

    passport_data = {
        "name": "TestNoRegimeParams",
        "emoji": "🧪",
        "config_overrides": {
            "INDICATOR_WEIGHTS": {
                "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
                "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
                "pressure": 0.0, "candle_direction": 0.0,
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "test_no_rp.json")
        with open(fpath, "w") as f:
            json.dump(passport_data, f)

        with patch("bot.passport_runner.StateStore") as MockStateStore:
            _make_mock_state_store(MockStateStore)
            runner = PassportRunner(tmpdir)

    passport = runner.passports[0]
    assert passport.regime_params == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_passport_runner_regime.py::test_regime_params_loaded_from_json tests/test_passport_runner_regime.py::test_regime_params_defaults_to_empty_dict -v`
Expected: FAIL with `AttributeError: 'Passport' object has no attribute 'regime_params'`

- [ ] **Step 3: Implement `regime_params` in Passport class**

In `bot/passport_runner.py`, modify `Passport.__init__()` (line 37, after `self.active_regimes`):

```python
class Passport:
    """A single strategy passport with its own config and state."""

    def __init__(self, filepath: str):
        with open(filepath) as f:
            data = json.load(f)

        self.name = data["name"]
        self.emoji = data.get("emoji", "📊")
        self.enabled = _is_enabled(data)
        self.description = data.get("description", "")
        self.config_overrides = data.get("config_overrides", {})
        self.active_regimes = data.get("active_regimes", None)
        self.regime_params = data.get("regime_params", {})
        self.position_manager = PositionManager()
        self.equity = config.INITIAL_EQUITY
        self.trade_count = 0
        self.signal_count = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_passport_runner_regime.py::test_regime_params_loaded_from_json tests/test_passport_runner_regime.py::test_regime_params_defaults_to_empty_dict -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/passport_runner.py tests/test_passport_runner_regime.py
git commit -m "feat: load regime_params from passport JSON config"
```

---

### Task 2: Hard Gate Enforcement in `run_scan_cycle()`

**Files:**
- Modify: `bot/passport_runner.py:222-322` (run_scan_cycle method)
- Create: `tests/test_regime_gating.py`

- [ ] **Step 1: Write failing tests for hard gate**

Create `tests/test_regime_gating.py`:

```python
"""Tests for regime hard-gate enforcement in PassportRunner."""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from bot import config


def _make_passport_dir(tmpdir, passports_data):
    """Write passport JSON files to tmpdir. Returns list of filenames."""
    for i, data in enumerate(passports_data):
        fpath = os.path.join(tmpdir, f"passport_{i}.json")
        with open(fpath, "w") as f:
            json.dump(data, f)


def _base_indicators():
    return {
        "ema_trend": 1.0, "macd_signal": 0.0, "rsi_position": 0.0,
        "rsi_divergence": 0.0, "bb_position": 1.0, "volume_spike": 2.0,
        "pressure": 0.0, "candle_direction": 0.0,
    }


def _make_runner(tmpdir):
    """Create PassportRunner with mocked StateStore."""
    from bot.passport_runner import PassportRunner
    with patch("bot.passport_runner.StateStore") as MockSS:
        mock_ss = MockSS.return_value
        mock_ss.get_last_equity.return_value = None
        mock_ss.load_open_positions.return_value = []
        mock_ss.db_path = ":memory:"
        runner = PassportRunner(tmpdir)
    return runner


class TestHardGate:
    """Tests for active_regimes hard gate."""

    def test_passport_skipped_when_regime_not_in_active_regimes(self, capsys):
        """Passport with active_regimes skips scan when current regime doesn't match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "TrendOnly",
                "emoji": "📈",
                "active_regimes": ["TREND_UP", "TREND_DOWN"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            # Set regime to HIGH_VOL_CHOP (not in active_regimes)
            runner.scanner.btc_trend = "HIGH_VOL_CHOP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            results = runner.run_scan_cycle()

            # scan_all should NOT have been called
            runner.scanner.scan_all.assert_not_called()
            captured = capsys.readouterr()
            assert "regime gate" in captured.out.lower() or "skipped" in captured.out.lower()

    def test_passport_scans_when_regime_matches_active_regimes(self):
        """Passport scans normally when current regime is in active_regimes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "TrendOnly",
                "emoji": "📈",
                "active_regimes": ["TREND_UP", "TREND_DOWN"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            results = runner.run_scan_cycle()

            # scan_all SHOULD have been called
            runner.scanner.scan_all.assert_called_once()

    def test_passport_without_active_regimes_always_scans(self):
        """Passport without active_regimes (None) scans in any regime."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "NoGate",
                "emoji": "🌍",
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            for regime in ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"]:
                runner.scanner.btc_trend = regime
                runner.scanner.scan_all = MagicMock(return_value=[])
                runner.run_scan_cycle()
                runner.scanner.scan_all.assert_called()

    def test_passport_with_empty_active_regimes_never_scans(self):
        """Passport with active_regimes=[] never scans (effectively disabled)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "NeverTrade",
                "emoji": "🚫",
                "active_regimes": [],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            runner.run_scan_cycle()
            runner.scanner.scan_all.assert_not_called()

    def test_hard_gate_does_not_affect_disabled_passports(self, capsys):
        """Disabled passports are skipped before regime gate check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "DisabledPassport",
                "emoji": "⏸️",
                "enabled": False,
                "active_regimes": ["TREND_UP"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            runner.run_scan_cycle()
            runner.scanner.scan_all.assert_not_called()
            captured = capsys.readouterr()
            assert "disabled" in captured.out.lower() or "restored positions" in captured.out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_regime_gating.py -v`
Expected: Most tests PASS accidentally (scanner.scan_all mock), but `test_passport_skipped_when_regime_not_in_active_regimes` should show scan_all was called (because hard gate isn't enforced yet).

- [ ] **Step 3: Implement hard gate in `run_scan_cycle()`**

In `bot/passport_runner.py`, modify `run_scan_cycle()`. Replace lines 235-241 (the enabled check + the beginning of the scan loop body) with:

```python
        for passport in self.passports:
            if not passport.enabled:
                print(
                    f"\n[{passport.emoji} {passport.name}] Scan disabled; monitoring restored positions only.",
                    flush=True,
                )
                continue

            # === HARD GATE: skip passport if current regime not in active_regimes ===
            current_regime = self.scanner.btc_trend
            if passport.active_regimes is not None and current_regime not in passport.active_regimes:
                logger.info(
                    "Passport %s regime-gated: %s not in %s",
                    passport.name, current_regime, passport.active_regimes,
                )
                print(
                    f"\n[{passport.emoji} {passport.name}] ⏸️ Regime gate — "
                    f"{current_regime} not in {passport.active_regimes}. Skipped.",
                    flush=True,
                )
                continue

            print(f"\n[{passport.emoji} {passport.name}] Scanning...", flush=True)
```

Also remove the old Phase 1 "logged only, not enforced" code from `_load_passports()` (lines 139-144):

```python
                # active_regimes is now enforced in run_scan_cycle() (no longer Phase 1 log-only)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_regime_gating.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run existing regime tests to ensure no regression**

Run: `uv run pytest tests/test_passport_runner_regime.py -v`
Expected: ALL PASS (existing tests should still work)

- [ ] **Step 6: Commit**

```bash
git add bot/passport_runner.py tests/test_regime_gating.py
git commit -m "feat: enforce active_regimes hard gate in run_scan_cycle()"
```

---

### Task 3: Regime Params Overlay in `run_scan_cycle()`

**Files:**
- Modify: `bot/passport_runner.py:222-322` (run_scan_cycle), `bot/passport_runner.py:482-497` (_save_config)
- Add tests to: `tests/test_regime_gating.py`

- [ ] **Step 1: Write failing tests for regime_params overlay**

Add to `tests/test_regime_gating.py`:

```python
class TestRegimeParamsOverlay:
    """Tests for regime_params config overlay."""

    def test_regime_params_override_config_overrides(self):
        """regime_params[current_regime] overrides config_overrides values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "OverlayTest",
                "emoji": "🔧",
                "active_regimes": ["TREND_UP", "HIGH_VOL_CHOP"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 54,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "HIGH_VOL_CHOP": {"CONFIDENCE_THRESHOLD": 65}
                }
            }])
            runner = _make_runner(tmpdir)

            # In TREND_UP: no regime_params entry → uses config_overrides (54)
            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])
            original_threshold = config.CONFIDENCE_THRESHOLD

            runner.run_scan_cycle()

            # After scan cycle, config should be restored
            assert config.CONFIDENCE_THRESHOLD == original_threshold

    def test_regime_params_applied_during_scan(self):
        """regime_params values are active during scan_all() call."""
        captured_threshold = {}

        def capture_scan():
            captured_threshold["value"] = config.CONFIDENCE_THRESHOLD
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "CaptureTest",
                "emoji": "📸",
                "active_regimes": ["HIGH_VOL_CHOP"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 54,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "HIGH_VOL_CHOP": {"CONFIDENCE_THRESHOLD": 65}
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "HIGH_VOL_CHOP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            # During scan, threshold should have been 65 (from regime_params)
            assert captured_threshold["value"] == 65

    def test_regime_params_restored_after_scan(self):
        """Config is fully restored after scan cycle, including regime_params keys."""
        original_threshold = config.CONFIDENCE_THRESHOLD

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "RestoreTest",
                "emoji": "♻️",
                "active_regimes": ["TREND_UP"],
                "config_overrides": {
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "TREND_UP": {
                        "CONFIDENCE_THRESHOLD": 70,
                        "MAX_OPEN_POSITIONS_PER_PASSPORT": 3
                    }
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = MagicMock(return_value=[])

            runner.run_scan_cycle()

            # Config must be fully restored
            assert config.CONFIDENCE_THRESHOLD == original_threshold
            assert config.MAX_OPEN_POSITIONS_PER_PASSPORT == 50  # global default

    def test_regime_params_empty_dict_uses_config_overrides_only(self):
        """Empty regime_params means only config_overrides apply."""
        captured_threshold = {}

        def capture_scan():
            captured_threshold["value"] = config.CONFIDENCE_THRESHOLD
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "EmptyRP",
                "emoji": "📦",
                "active_regimes": ["TREND_UP"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 58,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {}
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            # Should use config_overrides value (58), not global default (54)
            assert captured_threshold["value"] == 58

    def test_regime_params_missing_regime_key_uses_config_overrides(self):
        """When current regime has no entry in regime_params, use config_overrides only."""
        captured_threshold = {}

        def capture_scan():
            captured_threshold["value"] = config.CONFIDENCE_THRESHOLD
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "MissingKey",
                "emoji": "🔑",
                "active_regimes": ["TREND_UP", "TREND_DOWN"],
                "config_overrides": {
                    "CONFIDENCE_THRESHOLD": 56,
                    "INDICATOR_WEIGHTS": _base_indicators()
                },
                "regime_params": {
                    "TREND_DOWN": {"CONFIDENCE_THRESHOLD": 62}
                }
            }])
            runner = _make_runner(tmpdir)

            # In TREND_UP: no regime_params entry → uses 56 from config_overrides
            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            assert captured_threshold["value"] == 56

    def test_all_supported_regime_params_keys_work(self):
        """All 6 supported keys can be set via regime_params."""
        captured_config = {}

        def capture_scan():
            captured_config["CONFIDENCE_THRESHOLD"] = config.CONFIDENCE_THRESHOLD
            captured_config["MAX_OPEN_POSITIONS_PER_PASSPORT"] = config.MAX_OPEN_POSITIONS_PER_PASSPORT
            captured_config["RISK_PER_TRADE_PCT"] = config.RISK_PER_TRADE_PCT
            captured_config["DIRECTION_BIAS"] = config.DIRECTION_BIAS
            captured_config["USE_TRAILING_STOP"] = config.USE_TRAILING_STOP
            captured_config["ATR_TRAIL_MULTIPLIER"] = config.ATR_TRAIL_MULTIPLIER
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_passport_dir(tmpdir, [{
                "name": "AllKeys",
                "emoji": "🔑",
                "active_regimes": ["TREND_UP"],
                "config_overrides": {"INDICATOR_WEIGHTS": _base_indicators()},
                "regime_params": {
                    "TREND_UP": {
                        "CONFIDENCE_THRESHOLD": 70,
                        "MAX_OPEN_POSITIONS_PER_PASSPORT": 3,
                        "RISK_PER_TRADE_PCT": 0.3,
                        "DIRECTION_BIAS": "LONG_ONLY",
                        "USE_TRAILING_STOP": True,
                        "ATR_TRAIL_MULTIPLIER": 3.0
                    }
                }
            }])
            runner = _make_runner(tmpdir)

            runner.scanner.btc_trend = "TREND_UP"
            runner.scanner.scan_all = capture_scan

            runner.run_scan_cycle()

            assert captured_config["CONFIDENCE_THRESHOLD"] == 70
            assert captured_config["MAX_OPEN_POSITIONS_PER_PASSPORT"] == 3
            assert captured_config["RISK_PER_TRADE_PCT"] == 0.3
            assert captured_config["DIRECTION_BIAS"] == "LONG_ONLY"
            assert captured_config["USE_TRAILING_STOP"] is True
            assert captured_config["ATR_TRAIL_MULTIPLIER"] == 3.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_regime_gating.py::TestRegimeParamsOverlay -v`
Expected: Several failures — `regime_params` is not applied during scan yet.

- [ ] **Step 3: Implement regime_params overlay in `run_scan_cycle()`**

In `bot/passport_runner.py`, modify `run_scan_cycle()`. The section after applying overrides (around line 249-250) becomes:

```python
            # Save original config (include regime_params keys for restoration)
            regime_override_keys = set()
            current_regime = self.scanner.btc_trend
            if passport.regime_params:
                regime_overrides = passport.regime_params.get(current_regime, {})
                regime_override_keys = set(regime_overrides.keys())
            all_override_keys = set(passport.config_overrides.keys()) | regime_override_keys
            original_config = self._save_config(all_override_keys)

            # Apply passport overrides (layer 2: passport baseline)
            self._apply_overrides(passport.config_overrides)

            # Apply regime-specific overrides (layer 3: regime tuning)
            if passport.regime_params:
                regime_overrides = passport.regime_params.get(current_regime, {})
                if regime_overrides:
                    logger.info(
                        "Passport %s applying regime_params for %s: %s",
                        passport.name, current_regime, regime_overrides,
                    )
                self._apply_overrides(regime_overrides)

            self._apply_regime_guardrails(passport)
```

Replace the old lines 245-250:
```python
            # Save original config
            original_config = self._save_config(passport.config_overrides.keys())

            # Apply passport overrides
            self._apply_overrides(passport.config_overrides)
            self._apply_regime_guardrails(passport)
```

With:
```python
            # Save original config (include regime_params keys for restoration)
            current_regime = self.scanner.btc_trend
            regime_overrides = {}
            if passport.regime_params:
                regime_overrides = passport.regime_params.get(current_regime, {})
            all_override_keys = set(passport.config_overrides.keys()) | set(regime_overrides.keys())
            original_config = self._save_config(all_override_keys)

            # Apply passport overrides (layer 2: passport baseline)
            self._apply_overrides(passport.config_overrides)

            # Apply regime-specific overrides (layer 3: regime tuning)
            if regime_overrides:
                logger.info(
                    "Passport %s applying regime_params for %s: %s",
                    passport.name, current_regime, regime_overrides,
                )
                self._apply_overrides(regime_overrides)

            self._apply_regime_guardrails(passport)
```

Note: `current_regime` is already computed earlier for the hard gate check. Move the `current_regime = self.scanner.btc_trend` line BEFORE the passport loop (after `self.scanner.update_btc_trend()` on line 233), and reference it in both the hard gate and the regime_params overlay.

The full updated `run_scan_cycle()` top section should be:

```python
    def run_scan_cycle(self) -> List[Dict]:
        """
        Run a full scan cycle across all passports.
        Each passport gets its own config overrides applied temporarily.
        Regime gating: passports only scan in their declared active_regimes.
        Regime params: per-regime config tuning applied on top of config_overrides.

        Returns list of (signal, passport) tuples for signals found.
        """
        all_results = []
        cycle_signal_count = 0

        # Refresh BTC trend once (shared across passports)
        self.scanner.update_btc_trend()
        current_regime = self.scanner.btc_trend

        for passport in self.passports:
            if not passport.enabled:
                print(
                    f"\n[{passport.emoji} {passport.name}] Scan disabled; monitoring restored positions only.",
                    flush=True,
                )
                continue

            # === HARD GATE: skip passport if current regime not in active_regimes ===
            if passport.active_regimes is not None and current_regime not in passport.active_regimes:
                logger.info(
                    "Passport %s regime-gated: %s not in %s",
                    passport.name, current_regime, passport.active_regimes,
                )
                print(
                    f"\n[{passport.emoji} {passport.name}] ⏸️ Regime gate — "
                    f"{current_regime} not in {passport.active_regimes}. Skipped.",
                    flush=True,
                )
                continue

            print(f"\n[{passport.emoji} {passport.name}] Scanning...", flush=True)

            # Save original config (include regime_params keys for full restoration)
            regime_overrides = {}
            if passport.regime_params:
                regime_overrides = passport.regime_params.get(current_regime, {})
            all_override_keys = set(passport.config_overrides.keys()) | set(regime_overrides.keys())
            original_config = self._save_config(all_override_keys)

            # Apply passport overrides (layer 2: passport baseline)
            self._apply_overrides(passport.config_overrides)

            # Apply regime-specific overrides (layer 3: regime tuning)
            if regime_overrides:
                logger.info(
                    "Passport %s applying regime_params for %s: %s",
                    passport.name, current_regime, regime_overrides,
                )
                self._apply_overrides(regime_overrides)

            self._apply_regime_guardrails(passport)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_regime_gating.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regression check**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ALL tests pass (339+ tests)

- [ ] **Step 6: Commit**

```bash
git add bot/passport_runner.py tests/test_regime_gating.py
git commit -m "feat: apply regime_params overlay in run_scan_cycle()

Config resolution: global → config_overrides → regime_params[regime].
All keys snapshotted and restored after each passport scan."
```

---

### Task 4: Update All 26 Passport JSONs

**Files:**
- Modify: all 26 files in `passports/pumpradar/*.json` and `passports/cryptopass-research/*.json`
- Create: `scripts/update_passport_regimes.py` (helper script, delete after use)

- [ ] **Step 1: Write and run the batch update script**

Create `scripts/update_passport_regimes.py`:

```python
"""Batch-update all passport JSONs with active_regimes and regime_params.

Regime assignments from approved design spec:
- Trend-Following: TREND_UP, TREND_DOWN
- Mean-Reversion: HIGH_VOL_CHOP, LOW_VOL_COMPRESSION
- Breakout: LOW_VOL_COMPRESSION, TREND_UP, TREND_DOWN
- Hybrid: varies per passport

Phase 1: regime_params is empty for all (defer per-regime tuning to Phase 2).
         The hard gate (active_regimes) is the big win.
"""
import json
import os
import sys

# Regime assignments keyed by passport name
REGIME_ASSIGNMENTS = {
    # Trend-Following
    "Pumpradar HiddenGem": ["TREND_UP", "TREND_DOWN"],
    "Pumpradar Sniper": ["TREND_UP", "TREND_DOWN"],
    "Pumpradar VolumeKing": ["TREND_UP", "TREND_DOWN"],
    "Pumpradar Momentum": ["TREND_UP", "TREND_DOWN"],
    "DualMA Crossover": ["TREND_UP", "TREND_DOWN"],
    "PureTrend": ["TREND_UP", "TREND_DOWN"],
    "TrendMomentum": ["TREND_UP", "TREND_DOWN"],
    "TrendConfirm": ["TREND_UP", "TREND_DOWN"],
    "MinimalEdge": ["TREND_UP", "TREND_DOWN"],
    "OBV Trend": ["TREND_UP", "TREND_DOWN"],
    "Pumpradar Dynamic": ["TREND_UP", "TREND_DOWN"],

    # Mean-Reversion
    "BBMeanRev": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
    "RSIContrarian": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
    "Pumpradar ReversalV2": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],

    # Breakout
    "BollingerBreakout": ["LOW_VOL_COMPRESSION", "TREND_UP", "TREND_DOWN"],
    "BollingerBreakoutV2": ["LOW_VOL_COMPRESSION", "TREND_UP", "TREND_DOWN"],
    "BollingerBreakoutV3": ["LOW_VOL_COMPRESSION", "TREND_UP", "TREND_DOWN"],
    "BreakoutVol": ["TREND_UP", "TREND_DOWN", "LOW_VOL_COMPRESSION"],
    "Donchian Breakout": ["LOW_VOL_COMPRESSION", "TREND_UP", "TREND_DOWN"],

    # Hybrid / Flexible
    "PressureReader": ["TREND_UP", "HIGH_VOL_CHOP"],
    "MACDDivergence": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP"],
    "RSIMomentumV2": ["TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP"],
    "Pumpradar OG": ["TREND_UP", "HIGH_VOL_CHOP"],
    "Pumpradar OG Seasonal": ["TREND_UP", "HIGH_VOL_CHOP"],
    "BalancedSelective": ["TREND_UP", "HIGH_VOL_CHOP"],

    # Disabled (add for completeness if ever re-enabled)
    "Pumpradar Reversal": ["HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"],
}


def update_passport(filepath):
    with open(filepath) as f:
        data = json.load(f)

    name = data["name"]
    if name not in REGIME_ASSIGNMENTS:
        print(f"  ⚠️  UNKNOWN passport: {name} — SKIPPED")
        return False

    regimes = REGIME_ASSIGNMENTS[name]
    data["active_regimes"] = regimes
    data["regime_params"] = {}

    # Bump minor version
    old_version = data.get("version", "0.1")
    parts = old_version.split(".")
    new_minor = int(parts[-1]) + 1
    new_version = f"{parts[0]}.{new_minor}"
    data["version"] = new_version

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"  ✅ {name}: active_regimes={regimes}, version {old_version}→{new_version}")
    return True


def main():
    dirs = ["passports/pumpradar", "passports/cryptopass-research"]
    updated = 0
    for d in dirs:
        print(f"\n📁 {d}/")
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(d, fname)
            if update_passport(fpath):
                updated += 1

    print(f"\n✅ Updated {updated} passports")


if __name__ == "__main__":
    main()
```

Run: `uv run python scripts/update_passport_regimes.py`
Expected: 26 passports updated with active_regimes and version bumps.

- [ ] **Step 2: Verify all passports have valid active_regimes**

Run:
```bash
uv run python -c "
import json, os
VALID = {'TREND_UP','TREND_DOWN','HIGH_VOL_CHOP','LOW_VOL_COMPRESSION'}
for d in ['passports/pumpradar','passports/cryptopass-research']:
    for f in sorted(os.listdir(d)):
        if not f.endswith('.json'): continue
        data = json.load(open(os.path.join(d,f)))
        ar = data.get('active_regimes')
        rp = data.get('regime_params')
        name = data['name']
        assert ar is not None, f'{name}: missing active_regimes'
        assert isinstance(ar, list), f'{name}: active_regimes not a list'
        assert all(r in VALID for r in ar), f'{name}: invalid regime in {ar}'
        assert isinstance(rp, dict), f'{name}: regime_params not a dict'
        print(f'✅ {name}: {ar}')
print('All passports validated!')
"
```
Expected: All 26 passports valid.

- [ ] **Step 3: Commit passport updates**

```bash
git add passports/pumpradar/*.json passports/cryptopass-research/*.json
git commit -m "feat: add active_regimes to all 26 passports

Regime assignments per approved design spec:
- 11 trend-following → TREND_UP, TREND_DOWN
- 3 mean-reversion → HIGH_VOL_CHOP, LOW_VOL_COMPRESSION
- 5 breakout → LOW_VOL_COMPRESSION, TREND_UP, TREND_DOWN
- 6 hybrid → varies per passport
- 1 disabled (Reversal) → HIGH_VOL_CHOP, LOW_VOL_COMPRESSION

Phase 1: regime_params={} for all (hard gate only).
Per-regime tuning deferred to Phase 2."
```

- [ ] **Step 4: Delete the helper script**

```bash
rm scripts/update_passport_regimes.py
git add -u scripts/
git commit -m "chore: remove one-time passport update script"
```

---

### Task 5: Config Default — ATR Trail Multiplier

**Files:**
- Modify: `bot/config.py:128`

- [ ] **Step 1: Update ATR_TRAIL_MULTIPLIER default**

In `bot/config.py`, change line 128:

From:
```python
ATR_TRAIL_MULTIPLIER = 2.0   # trail distance = 2x ATR at entry
```

To:
```python
ATR_TRAIL_MULTIPLIER = 2.5   # trail distance = 2.5x ATR at entry (widened from 2.0 to avoid whipsaws)
```

- [ ] **Step 2: Verify no test breaks**

Run: `uv run pytest tests/test_atr_fix.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add bot/config.py
git commit -m "feat: widen ATR_TRAIL_MULTIPLIER default 2.0 → 2.5

Wider trailing stop reduces whipsaw risk on 1H crypto timeframe.
Still disabled globally (USE_TRAILING_STOP=False); opt-in per passport."
```

---

### Task 6: Integration Test — All Passports Load + Regime Schema Valid

**Files:**
- Create: `tests/test_regime_gating_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_regime_gating_integration.py`:

```python
"""Integration tests: verify all production passport JSONs have valid regime config."""
import json
import os
import pytest

VALID_REGIMES = {"TREND_UP", "TREND_DOWN", "HIGH_VOL_CHOP", "LOW_VOL_COMPRESSION"}
VALID_REGIME_PARAM_KEYS = {
    "CONFIDENCE_THRESHOLD", "MAX_OPEN_POSITIONS_PER_PASSPORT",
    "RISK_PER_TRADE_PCT", "DIRECTION_BIAS",
    "USE_TRAILING_STOP", "ATR_TRAIL_MULTIPLIER",
}
PASSPORT_DIRS = ["passports/pumpradar", "passports/cryptopass-research"]


def _all_passport_paths():
    paths = []
    for d in PASSPORT_DIRS:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                paths.append(os.path.join(d, fname))
    return paths


@pytest.fixture(params=_all_passport_paths(), ids=lambda p: os.path.basename(p))
def passport_data(request):
    with open(request.param) as f:
        return json.load(f)


def test_passport_has_active_regimes(passport_data):
    """Every passport must declare active_regimes (list or null)."""
    ar = passport_data.get("active_regimes")
    # Must be present (not missing from JSON)
    assert "active_regimes" in passport_data, f"{passport_data['name']}: missing active_regimes key"
    if ar is not None:
        assert isinstance(ar, list), f"{passport_data['name']}: active_regimes must be list or null"
        for r in ar:
            assert r in VALID_REGIMES, f"{passport_data['name']}: invalid regime '{r}'"


def test_passport_regime_params_schema(passport_data):
    """regime_params must be a dict with valid regime keys and valid param keys."""
    rp = passport_data.get("regime_params", {})
    assert isinstance(rp, dict), f"{passport_data['name']}: regime_params must be dict"

    for regime, params in rp.items():
        assert regime in VALID_REGIMES, f"{passport_data['name']}: invalid regime key '{regime}' in regime_params"
        assert isinstance(params, dict), f"{passport_data['name']}: regime_params[{regime}] must be dict"

        # Regime params keys should only be known config keys
        for key in params:
            assert key in VALID_REGIME_PARAM_KEYS, (
                f"{passport_data['name']}: unknown regime_params key '{key}' "
                f"in {regime}. Valid: {VALID_REGIME_PARAM_KEYS}"
            )


def test_passport_regime_params_only_for_active_regimes(passport_data):
    """regime_params keys should only reference regimes in active_regimes."""
    ar = passport_data.get("active_regimes")
    rp = passport_data.get("regime_params", {})

    if ar is None or not rp:
        return  # No constraint when active_regimes is null or regime_params empty

    for regime in rp:
        assert regime in ar, (
            f"{passport_data['name']}: regime_params has key '{regime}' "
            f"but active_regimes is {ar}"
        )


def test_all_8_indicator_weights_present(passport_data):
    """All 8 INDICATOR_WEIGHTS keys must be present (existing invariant)."""
    required_keys = {
        "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
        "bb_position", "volume_spike", "pressure", "candle_direction",
    }
    co = passport_data.get("config_overrides", {})
    iw = co.get("INDICATOR_WEIGHTS", {})

    # Filter out non-weight keys like REVERSAL_MODE
    weight_keys = {k for k in iw if k in required_keys}
    missing = required_keys - weight_keys
    assert not missing, f"{passport_data['name']}: missing INDICATOR_WEIGHTS: {missing}"
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/test_regime_gating_integration.py -v`
Expected: ALL PASS (26 passports × 4 tests each)

- [ ] **Step 3: Commit**

```bash
git add tests/test_regime_gating_integration.py
git commit -m "test: integration tests for passport regime schema validation"
```

---

### Task 7: Documentation Updates

**Files:**
- Modify: `passports/VERSIONS.md`
- Modify: `docs/FINDINGS.md`

- [ ] **Step 1: Update VERSIONS.md with regime optimization version bumps**

Add a new section to `passports/VERSIONS.md` documenting the regime optimization batch update. Include each passport's version bump and new `active_regimes`.

Format per passport:
```markdown
### [Passport Name] v[old] → v[new]
- **Change:** Added `active_regimes` and `regime_params` (Phase 1: hard gate only)
- **active_regimes:** [list of regimes]
- **regime_params:** `{}` (Phase 1)
```

- [ ] **Step 2: Update FINDINGS.md with Session 11e section**

Add to `docs/FINDINGS.md`:

```markdown
## Session 11e: Per-Passport Regime Optimization (2026-04-12)

### What Changed
- **Regime hard gate enforced:** Each passport now only scans in its declared `active_regimes`. Previously all 25 scanned in all regimes.
- **Regime params overlay:** `regime_params` dict in passport JSON allows per-regime config tuning (confidence threshold, position limits, risk, direction bias, trailing stop).
- **Config resolution order:** global defaults → config_overrides → regime_params[current_regime]
- **ATR_TRAIL_MULTIPLIER:** Default widened from 2.0 → 2.5

### Impact
- In current regime (HIGH_VOL_CHOP): only 9 of 25 passports active (was 25)
- Estimated loss prevention: ~60% of wrong-regime losses avoided
- Pareto ratio: ~1:100 (lose ~$50 upside, save ~$4,000-6,000 downside)

### Regime Assignments
- 11 trend-following → TREND_UP, TREND_DOWN
- 3 mean-reversion → HIGH_VOL_CHOP, LOW_VOL_COMPRESSION
- 5 breakout → LOW_VOL_COMPRESSION + TREND_UP + TREND_DOWN
- 6 hybrid → varies per passport

### New Tests
- `test_regime_gating.py`: Hard gate + regime_params overlay (11 tests)
- `test_regime_gating_integration.py`: Schema validation for all 26 passports (4 tests × 26)
```

- [ ] **Step 3: Commit documentation**

```bash
git add passports/VERSIONS.md docs/FINDINGS.md
git commit -m "docs: document regime optimization in VERSIONS.md and FINDINGS.md"
```

---

### Task 8: Full Test Suite + Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ALL tests pass (350+ tests after new additions)

- [ ] **Step 2: Verify regime gating works end-to-end with a dry run**

Run:
```bash
uv run python -c "
from bot.passport_runner import PassportRunner
from unittest.mock import patch

# Load real passports
with patch('bot.passport_runner.StateStore') as MockSS:
    mock_ss = MockSS.return_value
    mock_ss.get_last_equity.return_value = None
    mock_ss.load_open_positions.return_value = []
    mock_ss.db_path = ':memory:'
    runner = PassportRunner('passports')

# Simulate each regime and count active passports
for regime in ['TREND_UP', 'TREND_DOWN', 'HIGH_VOL_CHOP', 'LOW_VOL_COMPRESSION']:
    active = sum(
        1 for p in runner.passports
        if p.enabled and (p.active_regimes is None or regime in p.active_regimes)
    )
    total = sum(1 for p in runner.passports if p.enabled)
    names = [p.name for p in runner.passports
             if p.enabled and (p.active_regimes is None or regime in p.active_regimes)]
    print(f'{regime}: {active}/{total} active')
    for n in names:
        print(f'  - {n}')
    print()
"
```

Expected output:
```
TREND_UP: 22/25 active (all except 3 mean-reversion)
TREND_DOWN: 19/25 active (trend + breakout + some hybrid)
HIGH_VOL_CHOP: 9/25 active (mean-rev + hybrid)
LOW_VOL_COMPRESSION: 8/25 active (mean-rev + breakout)
```

- [ ] **Step 3: Final commit — version tag**

```bash
git tag -a v0.12.0-regime-gating -m "Per-passport regime gating: hard gate + regime_params overlay"
```
