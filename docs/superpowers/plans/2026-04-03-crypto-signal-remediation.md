# Crypto Signal Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the live multi-passport bot on `fight-tres`, restore durable state, make backtest/discovery trustworthy, and make deployment/test operations reproducible.

**Architecture:** First freeze a safe deployment baseline and disable the runaway strategy path. Then fix local-vs-server drift, SQLite state persistence, backtest/discovery correctness, packaging/tests, and observability/security. Every task below is independently reviewable and should be executed in small test-first commits.

**Tech Stack:** Python, SQLite, systemd, pytest, Binance Futures HTTP API, Telegram Bot API, Telethon scripts, shell over SSH.

**Verification note:** Before any `pytest` invocation below, install the local dev/test dependencies in the repo venv first, for example:

```bash
.venv/bin/python -m pip install -e '.[dev]'
```

If the project uses a different extras name in `pyproject.toml`, use the matching editable install command instead.

---

## Production Findings Snapshot

Historical note: this snapshot captures the **pre-v2** server state that motivated the remediation work. It is retained as incident context, not as the current post-cutover service state; use `ops/fight-tres-runbook.md` and `docs/crypto_signal_handover.md` for the latest deployment status.

These findings were verified directly on `fight-tres` via one-shot SSH and `journalctl` before the v2 cutover:

- `pumpradar.service` has been active since `2026-03-31 11:46:01 UTC` and runs `/home/vforvaick/pumpradar-bot/.venv/bin/python -m bot.main_multi --interval=1h ...` from `/home/vforvaick/pumpradar-bot`.
- Server code is still the old in-memory version: `/home/vforvaick/pumpradar-bot/bot/state_store.py` is absent, `/home/vforvaick/pumpradar-bot/state.db` is absent, and server `bot/passport_runner.py` does not restore positions/equity from SQLite.
- First summary after deployment, `2026-03-31 11:53:02 UTC`, opened 31 Dynamic, 2 HiddenGem, 28 Momentum, 34 OG, 43 Reversal positions with all equities still at `$1,000`.
- By `2026-03-31 12:51:51 UTC`, one hour later, Dynamic was `-7.2%`, HiddenGem `-3.0%`, Momentum `-1.2%`, OG `-3.4%`, Reversal `-6.0%`.
- Latest summary observed at `2026-04-03 09:48:49 UTC`: Dynamic `831 (-16.9%) / 34 signals / 25 trades / 9 open`; HiddenGem `970 (-3.0%) / 2 / 1 / 1`; Momentum `905 (-9.5%) / 32 / 23 / 9`; OG `1052 (+5.2%) / 63 / 34 / 29`; Reversal `407 (-59.3%) / 337 / 152 / 185`; Sniper `1000 / 0 / 0 / 0`; VolumeKing `1000 / 0 / 0 / 0`.
- Later events at `2026-04-03 10:00:20-10:00:21 UTC` moved Dynamic to `$896` and OG to `$1,128` via ONGUSDT TP events, but no summary block had printed yet after those events.
- Multi-perspective read: strategy-wise Reversal is the clear loss driver and overtrading path; runtime-wise too many open Reversal positions amplify 1m polling load; deployment-wise server is behind local v2 and embeds Telegram credentials in systemd `ExecStart`; data/science-wise current discovery/backtest path is not trustworthy due known code bugs and config-key mismatches.

## File Map

- Runtime and persistence: `bot/main_multi.py`, `bot/passport_runner.py`, `bot/state_store.py`, `bot/position_manager.py`, `bot/notifier.py`
- Signal and risk model: `bot/scorer.py`, `bot/signals.py`, `bot/config.py`, `bot/indicators.py`, `bot/scanner.py`
- Backtest and discovery: `bot/backtester.py`, `bot/discovery_engine.py`, `bot/walk_forward.py`, `run_discovery.py`
- Packaging/tests/scripts/docs: `pyproject.toml` or root requirements files, `tests/`, `scripts/*.py`, `docs/*.md`, `.gitignore`
- Deployment/runbook: `ops/pumpradar.service`, `ops/fight-tres-runbook.md` or equivalent checked-in docs

---

### Task 1: Freeze a Safe Production Baseline and Quarantine Reversal

**Files:**
- Create: `ops/fight-tres-runbook.md`
- Create: `ops/pumpradar.service`
- Modify: `pumpradar-passports/configs/reversal.json`
- Modify: `docs/crypto_signal_handover.md`

- [ ] **Step 1: Capture exact server state and config drift in a checked-in runbook**

  Write `ops/fight-tres-runbook.md` with concrete commands and current observations:

  ```markdown
  # fight-tres Pumpradar Runbook

  ## Current Service State

  - Service: `pumpradar.service`
  - Host alias: `fight-tres`
  - Working directory: `/home/vforvaick/pumpradar-bot`
  - Start time observed: `2026-03-31 11:46:01 UTC`

  ## Read-only inspection

  ```bash
  ssh fight-tres systemctl status pumpradar.service --no-pager
  ssh fight-tres systemctl show pumpradar.service --property=Id,ActiveState,SubState,ExecStart,WorkingDirectory,MainPID,User,FragmentPath,UnitFileState,StateChangeTimestamp
  ssh fight-tres journalctl -u pumpradar.service -n 300 --no-pager -o short-iso
  ssh fight-tres find /home/vforvaick/pumpradar-bot -maxdepth 2 -type f
  ```

  ## Emergency rollback

  If Reversal keeps expanding open positions, stop the service, disable Reversal in config, restart, and confirm summary recovers.
  ```

- [ ] **Step 2: Run a source-control baseline check before any code edits**

  Run:

  ```bash
  git rev-parse --is-inside-work-tree
  ```

  Expected: `true`

  If this prints a git error, stop implementation work and establish the canonical repo/worktree first. Do not keep patching an untracked workspace while the live bot is running from a different copy.

- [ ] **Step 3: Quarantine the Reversal passport before redeploying structural fixes**

  Modify `pumpradar-passports/configs/reversal.json` to make the strategy opt-in only during research. One acceptable implementation is to add an explicit disabled flag:

  ```json
  {
      "name": "Pumpradar Reversal",
      "emoji": "🔄",
      "enabled": false,
      "description": "Mean reversion strategy kept disabled in production until regime filters and drawdown controls are fixed.",
      "config_overrides": {
          "INDICATOR_WEIGHTS": {
              "REVERSAL_MODE": true,
              "ema_trend": 0.0,
              "macd_signal": 0.0,
              "rsi_position": 2.0,
              "rsi_divergence": 2.0,
              "bb_position": 2.0,
              "volume_spike": 0.0,
              "pressure": 0.0,
              "candle_direction": 0.0
          }
      }
  }
  ```

  This requires Task 2 to teach `PassportRunner` to skip disabled passports.

- [ ] **Step 4: Verify the runbook and quarantine decision are reflected in docs**

  Update `docs/crypto_signal_handover.md` to explicitly note that Reversal should stay disabled in production until the fixes in Tasks 2, 3, and 7 are deployed.

- [ ] **Step 5: Commit**

  ```bash
  git add ops/fight-tres-runbook.md ops/pumpradar.service docs/crypto_signal_handover.md pumpradar-passports/configs/reversal.json
  git commit -m "docs: capture fight-tres baseline and quarantine reversal"
  ```

---

### Task 2: Deploy Durable State and Fix Multi-Passport Resume Semantics

**Files:**
- Modify: `bot/state_store.py`
- Modify: `bot/passport_runner.py`
- Modify: `bot/main_multi.py`
- Modify: `bot/notifier.py`
- Create: `tests/test_state_store.py`
- Create: `tests/test_passport_runner_resume.py`

- [ ] **Step 1: Write a failing persistence test for save/load resume**

  Create `tests/test_state_store.py`:

  ```python
  from datetime import datetime

  from bot.signals import Signal
  from bot.state_store import StateStore


  def test_save_and_reload_open_position_with_numpy_safe_json(tmp_path):
      db_path = tmp_path / "state.db"
      store = StateStore(db_path=str(db_path))

      signal = Signal(
          symbol="BTCUSDT",
          direction="LONG",
          entry_price=100.0,
          tp1=110.0,
          tp2=120.0,
          tp3=130.0,
          sl=95.0,
          leverage=5,
          confidence=66.7,
          risk_reward=1.43,
          signals={"volume_spike": {"spike": True, "ratio": 2.5}},
          btc_trend="Sideways",
          timestamp=datetime(2026, 4, 3, 8, 0, 0),
      )

      pos_id = store.save_position("Pumpradar OG", signal, 1000.0, 30.0, tg_msg_id=123)
      rows = store.load_open_positions("Pumpradar OG")

      assert pos_id > 0
      assert len(rows) == 1
      assert rows[0]["symbol"] == "BTCUSDT"
      assert rows[0]["tg_msg_id"] == 123
      assert "\"timestamp\": \"2026-04-03T08:00:00\"" in rows[0]["signal_json"]
  ```

- [ ] **Step 2: Run the test and verify it fails on current edge cases**

  Run:

  ```bash
  .venv/bin/python -m pytest tests/test_state_store.py -q
  ```

  Expected before fix: failure when signal JSON contains numpy scalar types or if import/package wiring is still broken.

- [ ] **Step 3: Make `StateStore` robust and give the DB an explicit path**

  Modify `bot/state_store.py` so JSON serialization normalizes numpy scalars and DB location is deterministic:

  ```python
  import os

  def _json_default(value):
      if hasattr(value, "item"):
          return value.item()
      if isinstance(value, datetime):
          return value.isoformat()
      raise TypeError(f"Unsupported JSON value: {type(value)!r}")

  class StateStore:
      def __init__(self, db_path=None):
          self.db_path = db_path or os.environ.get(
              "PUMPRADAR_STATE_DB",
              os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "state.db")),
          )
          self._init_db()
  ```

  Use `json.dumps(sig_dict, default=_json_default)` and `json.dumps(trade_data, default=_json_default)`.

- [ ] **Step 4: Write a failing resume test for `PassportRunner`**

  Create `tests/test_passport_runner_resume.py` with a temp passport config and preloaded DB rows:

  ```python
  import json
  from datetime import datetime

  from bot.passport_runner import PassportRunner
  from bot.signals import Signal
  from bot.state_store import StateStore


  def test_runner_restores_equity_and_open_positions(tmp_path, monkeypatch):
      cfg_dir = tmp_path / "configs"
      cfg_dir.mkdir()
      (cfg_dir / "og.json").write_text(json.dumps({"name": "Pumpradar OG", "emoji": "🏆", "config_overrides": {}}))

      db_path = tmp_path / "state.db"
      store = StateStore(db_path=str(db_path))
      signal = Signal(
          symbol="BTCUSDT",
          direction="LONG",
          entry_price=100.0,
          tp1=110.0,
          tp2=120.0,
          tp3=130.0,
          sl=95.0,
          leverage=5,
          confidence=70.0,
          risk_reward=1.43,
          signals={},
          btc_trend="Sideways",
          timestamp=datetime(2026, 4, 3, 8, 0, 0),
      )
      store.save_position("Pumpradar OG", signal, 1234.0, 37.02, tg_msg_id=77)
      store.save_equity("Pumpradar OG", 1234.0)

      monkeypatch.setenv("PUMPRADAR_STATE_DB", str(db_path))
      runner = PassportRunner(str(cfg_dir), interval="1h")

      passport = runner.passports[0]
      assert passport.equity == 1234.0
      assert passport.position_manager.open_count == 1
      assert passport.position_manager.positions[0].pos_id == 1
  ```

- [ ] **Step 5: Implement resume-safe passport loading and disabled-passport skipping**

  Modify `bot/passport_runner.py` to:

  - instantiate `StateStore`
  - skip configs where `enabled` is explicitly `false`
  - restore `equity`, `open_positions`, and `pos_id`
  - persist `tg_msg_id` after signal send

  Keep a small helper like:

  ```python
  def _is_enabled(data: dict) -> bool:
      return data.get("enabled", True) is not False
  ```

- [ ] **Step 6: Fix Telegram message-id restore key mismatch**

  Ensure one canonical passport key is used everywhere. Example:

  ```python
  passport_key = passport.name
  passport_label = f"{passport.emoji} [{passport.name}]"
  msg_id = notifier._send(sig_msg)
  notifier.store_signal_message_id(sig.symbol, msg_id, passport_key)
  runner.state_store.update_position(pos.pos_id, tg_msg_id=msg_id)
  ```

  Then make `send_tp_sl_alert()` receive both `passport_name=passport.name` for lookup and `display_name=passport_label` for rendering.

- [ ] **Step 7: Run persistence and notifier tests**

  Run:

  ```bash
  .venv/bin/python -m pytest tests/test_state_store.py tests/test_passport_runner_resume.py tests/test_notifier.py -q
  ```

  Expected: all pass.

- [ ] **Step 8: Commit**

  ```bash
  git add bot/state_store.py bot/passport_runner.py bot/main_multi.py bot/notifier.py tests/test_state_store.py tests/test_passport_runner_resume.py
  git commit -m "feat: add durable multi-passport state resume"
  ```

---

### Task 3: Fix Backtest and Discovery Correctness Before Trusting New Passports

**Files:**
- Modify: `bot/backtester.py`
- Modify: `bot/discovery_engine.py`
- Modify: `bot/signals.py`
- Modify: `bot/scorer.py`
- Create: `tests/test_backtester_summary.py`
- Create: `tests/test_discovery_config_mapping.py`
- Create: `tests/test_signal_exit_modes.py`

- [ ] **Step 1: Add a regression test for `_summarize()` final equity**

  Create `tests/test_backtester_summary.py`:

  ```python
  from datetime import datetime

  from bot.backtester import _summarize
  from bot import config


  def test_summarize_uses_last_trade_equity_as_final_equity():
      trades = [
          {"pnl": 10.0, "equity_after": config.INITIAL_EQUITY + 10.0, "exit_time": datetime(2026, 4, 1, 0, 0, 0)},
          {"pnl": -5.0, "equity_after": config.INITIAL_EQUITY + 5.0, "exit_time": datetime(2026, 4, 2, 0, 0, 0)},
      ]

      summary = _summarize(trades)

      assert summary["final_equity"] == config.INITIAL_EQUITY + 5.0
      assert round(summary["return_pct"], 2) == 0.5
  ```

- [ ] **Step 2: Fix `_summarize()` and keep all metrics deterministic**

  In `bot/backtester.py`, initialize `final_eq` before using it:

  ```python
  final_eq = trades[-1]["equity_after"]
  ```

  Also guard Sharpe/Sortino/Calmar calculations with deterministic zero/inf handling and explicit tests.

- [ ] **Step 3: Add a regression test proving discovery profile weights actually affect scorer output**

  Create `tests/test_discovery_config_mapping.py` with a synthetic OHLCV window and two contrasting configs:

  ```python
  import pandas as pd

  from bot.discovery_engine import StrategyDiscoveryEngine


  def test_generated_weight_profiles_use_runtime_indicator_keys():
      engine = StrategyDiscoveryEngine(["BTCUSDT"], "1h", days=30)
      cfg = engine.generate_search_space()[0]

      assert "CONFIDENCE_THRESHOLD" in cfg
      assert "MIN_SCORE_THRESHOLD" not in cfg
      assert "ema_trend" in cfg["INDICATOR_WEIGHTS"]
      assert "volume_spike" in cfg["INDICATOR_WEIGHTS"]
      assert "w_ema" not in cfg["INDICATOR_WEIGHTS"]
  ```

- [ ] **Step 4: Replace dead discovery config keys with runtime keys**

  In `bot/discovery_engine.py`, generate configs like:

  ```python
  cfg = {
      "VOLUME_SPIKE_THRESHOLD": v,
      "CONFIDENCE_THRESHOLD": c,
      "INDICATOR_WEIGHTS": {
          "volume_spike": w["volume_spike"],
          "pressure": w["pressure"],
          "ema_trend": w["ema_trend"],
          "macd_signal": w["macd_signal"],
          "rsi_position": w["rsi_position"],
          "bb_position": w["bb_position"],
          "rsi_divergence": w["rsi_divergence"],
          "candle_direction": w["candle_direction"],
      },
      "_profile_name": profile_names[w_idx],
      "_exit_name": exit_names[ex_idx],
  }
  ```

  Remove unused `w_support` unless a real support/resistance signal is implemented.

- [ ] **Step 5: Add ATR exit tests and pass exit overrides consistently**

  Create `tests/test_signal_exit_modes.py`:

  ```python
  from bot import config
  from bot.signals import generate_signal


  def test_generate_signal_uses_atr_exit_when_enabled(monkeypatch):
      monkeypatch.setattr(config, "USE_ATR_EXITS", True, raising=False)
      score = {"go": True, "direction": "LONG", "confidence": 70.0, "leverage": 7, "risk_reward": 2.08, "signals": {}, "btc_trend": "Sideways", "atr": 5.0}

      signal = generate_signal("BTCUSDT", 100.0, score)

      assert signal is not None
      assert signal.sl == 90.0
      assert signal.tp1 == 120.0
  ```

  Then update `generate_signal()` and backtest callers so `USE_ATR_EXITS` and `USE_TRAILING_STOP` are read from one consistent source.

- [ ] **Step 6: Fix scorer edge cases and assert volume bonus does not double-count denominator**

  Add a focused scorer test and then adjust `total_weight` accounting so `volume_spike` is only added once when it actually contributes. Also normalize the no-vote reversal state to `NEUTRAL`, not `"NONE"`.

- [ ] **Step 7: Run backtest/discovery tests**

  Run:

  ```bash
  .venv/bin/python -m pytest tests/test_backtester_summary.py tests/test_discovery_config_mapping.py tests/test_signal_exit_modes.py -q
  ```

  Expected: all pass.

- [ ] **Step 8: Commit**

  ```bash
  git add bot/backtester.py bot/discovery_engine.py bot/signals.py bot/scorer.py tests/test_backtester_summary.py tests/test_discovery_config_mapping.py tests/test_signal_exit_modes.py
  git commit -m "fix: repair backtest and discovery config semantics"
  ```

---

### Task 4: Make Packaging, Imports, and Tests Reproducible From Repo Root

**Files:**
- Create: `pyproject.toml`
- Modify: `bot/requirements.txt`
- Modify: `scripts/run_twin_bots.py`
- Modify: `scripts/run_exit_opt.py`
- Modify: `tests/test_notifier.py`
- Modify: `tests/test_debug.py`
- Create: `tests/test_import_smoke.py`

- [ ] **Step 1: Define a root package spec**

  Create `pyproject.toml` so `python3 -m ...` works from a clean venv:

  ```toml
  [project]
  name = "crypto-signal"
  version = "0.1.0"
  requires-python = ">=3.11"
  dependencies = [
      "numpy",
      "pandas",
      "pyarrow",
      "requests",
      "matplotlib",
      "pytz",
      "telethon",
  ]

  [project.optional-dependencies]
  dev = ["pytest"]

  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["."]
  ```

- [ ] **Step 2: Add import smoke tests and convert script-style tests to assertions**

  Create `tests/test_import_smoke.py`:

  ```python
  def test_import_core_modules():
      import bot.main_multi
      import bot.passport_runner
      import bot.backtester
      import bot.discovery_engine
  ```

  Rewrite `tests/test_notifier.py` and `tests/test_debug.py` to use `assert`, fixtures, and repo-root-safe paths under `data/`.

- [ ] **Step 3: Fix script bootstrap paths**

  For scripts that currently append `scripts/` instead of repo root, use:

  ```python
  import os
  import sys

  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
  ```

  Apply this to `scripts/run_twin_bots.py`, `scripts/run_exit_opt.py`, and any other script that imports `bot`.

- [ ] **Step 4: Verify from a fresh interpreter mode**

  Run:

  ```bash
  .venv/bin/python -I -m pytest tests/test_import_smoke.py -q
  ```

  Expected: pass after packaging/import fixes.

- [ ] **Step 5: Commit**

  ```bash
  git add pyproject.toml bot/requirements.txt scripts/run_twin_bots.py scripts/run_exit_opt.py tests/test_notifier.py tests/test_debug.py tests/test_import_smoke.py
  git commit -m "build: make package imports and tests reproducible"
  ```

---

### Task 5: Add Production Guardrails Against Overtrading and Unbounded Open Positions

**Files:**
- Modify: `bot/config.py`
- Modify: `bot/passport_runner.py`
- Modify: `bot/position_manager.py`
- Modify: `pumpradar-passports/configs/*.json`
- Create: `tests/test_position_limits.py`

- [ ] **Step 1: Add tests for per-passport position caps**

  Create `tests/test_position_limits.py` asserting that a passport cannot open more than its configured max positions and cannot repeatedly stack many positions on one symbol if that is not intended.

- [ ] **Step 2: Introduce per-passport hard caps and optional symbol de-duplication**

  Add config keys such as:

  ```python
  MAX_OPEN_POSITIONS_PER_PASSPORT = 50
  MAX_OPEN_POSITIONS_PER_SYMBOL = 1
  ```

  Then enforce them in `PositionManager.can_open()` or in a new passport-aware gate before opening a position.

- [ ] **Step 3: Add regime-safe controls for Reversal**

  Until a full regime classifier exists, make Reversal require a stricter confidence threshold and a lower hard cap when `BTC Trend` is `Sideways`. This is a tactical production guardrail, not the final research solution.

- [ ] **Step 4: Verify by replaying a known high-signal scan**

  Use a deterministic cached candle sample and assert that Reversal no longer opens hundreds of positions in one session.

- [ ] **Step 5: Commit**

  ```bash
  git add bot/config.py bot/passport_runner.py bot/position_manager.py pumpradar-passports/configs tests/test_position_limits.py
  git commit -m "feat: add passport position guardrails"
  ```

---

### Task 6: Improve Observability and Remove Silent Failures

**Files:**
- Modify: `bot/scanner.py`
- Modify: `bot/passport_runner.py`
- Modify: `bot/notifier.py`
- Modify: `bot/data_fetcher.py`
- Create: `tests/test_fault_logging.py`

- [ ] **Step 1: Add tests proving Binance/Telegram exceptions are surfaced**

  Create a test that injects a failing fetch/send and asserts a warning/error log is emitted while the loop continues.

- [ ] **Step 2: Replace bare `except Exception: pass` with structured logs and counters**

  Use module-level loggers and include symbol/passport context:

  ```python
  import logging

  logger = logging.getLogger(__name__)

  try:
      df = fetch_klines(sym, "1m", limit=1, use_cache=False)
  except Exception:
      logger.exception("failed to fetch 1m mark price", extra={"symbol": sym, "passport": passport.name})
      continue
  ```

- [ ] **Step 3: Re-enable TLS verification by default**

  In `bot/data_fetcher.py`, remove `verify=False` and suppressed TLS warnings unless there is a documented, configurable escape hatch for a known proxy issue.

- [ ] **Step 4: Add an operator-facing summary command for state sanity**

  Extend Telegram `/status` or `/summary` so it reports state DB path, enabled passports, and open-position counts per passport. Keep this backed by tests.

- [ ] **Step 5: Commit**

  ```bash
  git add bot/scanner.py bot/passport_runner.py bot/notifier.py bot/data_fetcher.py tests/test_fault_logging.py
  git commit -m "chore: improve runtime observability and transport safety"
  ```

---

### Task 7: Reconcile Research Artifacts and Make Data Pipeline Paths Deterministic

**Files:**
- Modify: `scripts/parse_signals.py`
- Modify: `scripts/validate_market.py`
- Modify: `scripts/simulate_equity.py`
- Modify: `scripts/analyze_stats.py`
- Modify: `docs/analysis_report.md`
- Modify: `docs/strategy_spec.md`
- Modify: `docs/crypto_signal_handover.md`
- Create: `tests/test_research_pipeline_paths.py`

- [ ] **Step 1: Add a path test for the research pipeline**

  Create a test that runs script entrypoints against temp files under `data/` and asserts outputs land in `data/` or `docs/`, not repo root.

- [ ] **Step 2: Standardize script input/output defaults**

  Use repo-root-derived paths consistently:

  ```python
  ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
  DATA_DIR = os.path.join(ROOT, "data")
  DOCS_DIR = os.path.join(ROOT, "docs")
  ```

  Preserve CLI overrides for ad hoc experiments.

- [ ] **Step 3: Recompute and reconcile conflicting performance claims**

  Run the full historical pipeline and regenerate `docs/analysis_report.md` and `docs/strategy_spec.md` from the same source data/version. Then update `docs/crypto_signal_handover.md` so one baseline metric is presented with a clear methodology and date range.

- [ ] **Step 4: Fix local-only file links**

  Replace `file:///Users/faiqnau/...` links in docs with repo-relative markdown links so docs remain portable.

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/parse_signals.py scripts/validate_market.py scripts/simulate_equity.py scripts/analyze_stats.py docs/analysis_report.md docs/strategy_spec.md docs/crypto_signal_handover.md tests/test_research_pipeline_paths.py
  git commit -m "docs: reconcile research outputs and standardize pipeline paths"
  ```

---

### Task 8: Harden Secrets and Deployment Configuration

**Files:**
- Modify: `bot/main.py`
- Modify: `bot/main_multi.py`
- Modify: `scripts/fetch_samples.py`
- Modify: `scripts/fetch_deep.py`
- Modify: `.gitignore`
- Create: `ops/pumpradar.service`
- Create: `ops/env.example`

- [ ] **Step 1: Move Telegram and API secrets out of command-line args and code**

  Replace direct literals with environment variables:

  ```python
  tg_token = args.tg_token or os.environ.get("PUMPRADAR_TG_TOKEN")
  tg_chat = args.tg_chat or os.environ.get("PUMPRADAR_TG_CHAT")
  ```

  For Telethon scripts, read `PUMPRADAR_TG_API_ID`, `PUMPRADAR_TG_API_HASH`, and `PUMPRADAR_TG_SESSION`.

- [ ] **Step 2: Add a checked-in service template with `EnvironmentFile=`**

  Create `ops/pumpradar.service`:

  ```ini
  [Unit]
  Description=Pumpradar Multi-Passport Trading Bot
  After=network-online.target

  [Service]
  User=vforvaick
  WorkingDirectory=/home/vforvaick/pumpradar-bot
  EnvironmentFile=/home/vforvaick/pumpradar-bot/.env
  ExecStart=/home/vforvaick/pumpradar-bot/.venv/bin/python -m bot.main_multi --interval=1h
  Restart=always
  RestartSec=10

  [Install]
  WantedBy=multi-user.target
  ```

- [ ] **Step 3: Ignore local session/state artifacts**

  Update `.gitignore`:

  ```gitignore
  pumpradar_session.session
  state.db
  .cache/
  .venv/
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add bot/main.py bot/main_multi.py scripts/fetch_samples.py scripts/fetch_deep.py .gitignore ops/pumpradar.service ops/env.example
  git commit -m "sec: move secrets to environment and ignore local state"
  ```

---

### Task 9: Validate End-to-End and Deploy v2 to `fight-tres`

**Files:**
- Modify: `ops/fight-tres-runbook.md`
- Modify: `docs/crypto_signal_handover.md`

- [ ] **Step 1: Run the full local test suite**

  Run:

  ```bash
  .venv/bin/python -m pip install -e '.[dev]'
  .venv/bin/python -m pytest -q
  ```

  Expected: all tests pass.

- [ ] **Step 2: Run a restart-resume drill locally**

  Start `bot.main_multi` against a temp DB, generate one test signal, restart the process, and confirm open positions and Telegram message IDs are restored from SQLite.

- [ ] **Step 3: Deploy to `fight-tres` with a backup and controlled restart**

  Follow the runbook and keep a backup of the old server tree. After restart, verify:

  ```bash
  ssh fight-tres systemctl status pumpradar.service --no-pager
  ssh fight-tres journalctl -u pumpradar.service -n 200 --no-pager -o short-iso
  ```

  Expected: service starts from v2 code, logs startup restore messages from `PassportRunner` and `TelegramNotifier`, Reversal is disabled or capped, and no Telegram token is visible in `ExecStart`.

- [ ] **Step 4: Monitor the first 2 scan cycles after deploy**

  Verify one cycle does not reopen hundreds of Reversal positions, open positions/equity/message IDs restore after restart, and state DB grows as trades close. `signal_count` and `trade_count` are still in-memory counters, so they are expected to reset.

- [ ] **Step 5: Commit deployment notes**

  ```bash
  git add ops/fight-tres-runbook.md docs/crypto_signal_handover.md
  git commit -m "docs: record v2 deployment and post-restart validation"
  ```

## Generated Artifacts

- `discovery_results.json` and `data/equity_summary.json` are generated artifacts and are not currently ignored.
- Treat them intentionally in any workflow that produces them: either add them to ignore rules or commit them on purpose, but do not let them drift unnoticed.

---

## Self-Review

- Spec coverage: This plan covers live deployment drift, SQLite persistence, signal/backtest correctness, packaging/tests, risk guardrails, observability, research-doc reconciliation, secrets, and final deployment validation.
- Placeholder scan: No task contains `TODO`, `TBD`, or "implement later" placeholders.
- Type/signature consistency: Tests and implementation snippets use existing classes/functions from `Signal`, `StateStore`, `PassportRunner`, and config names aligned to runtime code, with explicit notes where key renames are required.

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-04-03-crypto-signal-remediation.md`.

1. Subagent-Driven (recommended): dispatch one worker per task, review between tasks, keep production-risky changes sequenced.
2. Inline Execution: execute the tasks in this session with checkpoints after each task.
