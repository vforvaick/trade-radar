# Multi-Passport Strategy Runner

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the bot to run multiple strategy "passports" simultaneously in paper-trading mode, each with its own indicator weights and exit rules, with all signals tagged by passport name in Telegram.

**Architecture:** A new `PassportRunner` orchestrator reads passport config files from `pumpradar-passports/configs/`, runs each one through the existing `scanner → scorer → signal` pipeline with config overrides, and sends tagged Telegram alerts. Existing single-passport behavior is preserved as the default fallback.

**Tech Stack:** Python 3, existing bot modules, JSON passport config files.

---

### Task 1: Create Passport Config Format

**Files:**
- Create: `pumpradar-passports/configs/momentum.json`
- Create: `pumpradar-passports/configs/reversal.json`
- Create: `pumpradar-passports/configs/dynamic_exit.json`

Each passport is a JSON file:
```json
{
  "name": "Pumpradar Momentum",
  "emoji": "🚀",
  "description": "Standard trend-following with 2x volume filter",
  "config_overrides": {
    "EMA_FAST": 9,
    "EMA_MID": 21,
    "EMA_SLOW": 50,
    "VOLUME_SPIKE_THRESHOLD": 2.0,
    "INDICATOR_WEIGHTS": {
      "ema_trend": 1.0,
      "macd_signal": 1.0,
      "rsi_position": 1.0,
      "rsi_divergence": 1.0,
      "bb_position": 1.0,
      "volume_spike": 2.0,
      "pressure": 1.0,
      "candle_direction": 1.0
    },
    "USE_ATR_EXITS": false,
    "USE_TRAILING_STOP": false
  }
}
```

- [ ] **Step 1: Create `momentum.json`** — The baseline Rank #2 passport
- [ ] **Step 2: Create `reversal.json`** — Mean reversion with REVERSAL_MODE
- [ ] **Step 3: Create `dynamic_exit.json`** — ATR exits + trailing stops
- [ ] **Step 4: Commit**

---

### Task 2: Create PassportRunner Orchestrator

**Files:**
- Create: `bot/passport_runner.py`

The orchestrator:
1. Loads all `*.json` passports from `pumpradar-passports/configs/`
2. For each passport, temporarily sets config overrides
3. Runs the existing `Scanner.scan_all()` pipeline
4. Tags resulting signals with the passport name
5. Restores config after each passport evaluation
6. Sends tagged signals to Telegram

- [ ] **Step 1: Write `bot/passport_runner.py`**

```python
class PassportRunner:
    def __init__(self, passport_dir, notifier, interval="1h"):
        self.passports = self._load_passports(passport_dir)
        self.notifier = notifier
        self.scanner = Scanner(interval=interval, limit=100)
        self.position_managers = {}  # One PM per passport
        
    def run_all_passports(self):
        results = {}
        for passport in self.passports:
            signals = self._run_single(passport)
            results[passport['name']] = signals
        return results
        
    def _run_single(self, passport):
        # Apply overrides, scan, restore
        original = self._apply_overrides(passport['config_overrides'])
        signals = self.scanner.scan_all()
        self._restore_config(original)
        return [(sig, passport) for sig in signals]
```

- [ ] **Step 2: Commit**

---

### Task 3: Update Telegram Notifier for Passport Tags

**Files:**
- Modify: `bot/notifier.py`

Add a `send_passport_signal(signal, passport_name, passport_emoji)` method that prefixes
the message with the passport identity:
```
🚀 [Pumpradar Momentum]
📊 LONG SIGNAL — BTCUSDT
Entry: $67,500 | Conf: 62.5%
TP1: $68,200 | TP2: $69,100 | TP3: $70,500
SL: $66,800 | Lev: 5x
```

- [ ] **Step 1: Add `send_passport_signal` method**
- [ ] **Step 2: Commit**

---

### Task 4: Create Multi-Passport Main Entry Point

**Files:**
- Create: `bot/main_multi.py`

New entry point that replaces the single-passport loop with multi-passport rotation:
```python
# Scans with ALL passports every hour
# Each passport has independent PositionManager
# Signals tagged and sent to Telegram individually
```

- [ ] **Step 1: Write `bot/main_multi.py`**
- [ ] **Step 2: Test locally**
- [ ] **Step 3: Commit**
