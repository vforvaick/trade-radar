# Deployment & Live Trading — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the live execution pipeline: OrderIntent types, PositionManager, PortfolioRiskManager, namespace isolation (paper/prod), Scheduler/Workers, Telegram integration, HealthMonitor, PromotionEngine, VPS deployment scripts, and integration tests.

**Architecture:** Adds bot/execution/ for OrderIntent/PositionManager, bot/risk/ for PortfolioRiskManager, extends bot/telegram_notify.py, adds bot/health/ for monitoring, bot/deploy/ for VPS tooling. Uses SQLite for state, systemd for process management.

**Tech Stack:** Python 3.11+, sqlite3, asyncio, python-telegram-bot, systemd, pytest

**Depends on:** Plan 1 (Research Engine Core) + Plan 2 (Robustness & Portfolio)

---

## File Map

| File | Responsibility |
|------|---------------|
| bot/execution/types.py (CREATE) | OrderIntent, Fill, PositionRecord dataclasses |
| bot/execution/position_manager.py (CREATE) | Signal → OrderIntent conversion, cooldown, pyramiding |
| bot/execution/engine.py (CREATE) | Paper fills + exchange API execution |
| bot/risk/portfolio_risk.py (CREATE) | Hard limits, soft alerts, exposure tracking |
| bot/risk/namespace.py (CREATE) | Paper/prod namespace isolation |
| bot/scheduler/orchestrator.py (CREATE) | Load registry, dispatch workers, rate limiting |
| bot/scheduler/worker.py (CREATE) | Per-passport scan + signal + position pipeline |
| bot/telegram_commands.py (CREATE) | /strategies, /compare, /promote, /pause, /health |
| bot/health/monitor.py (CREATE) | Operational health checks + alerting |
| bot/health/promotion.py (CREATE) | Promotion gate policy engine |
| bot/deploy/vps_setup.py (CREATE) | Deployment scripts, systemd units, artifact sync |
| bot/deploy/state_db.py (CREATE) | SQLite schema init + migration |

---

## Task 1: Execution Types

**Files:**
- Create: `bot/execution/__init__.py`
- Create: `bot/execution/types.py`
- Create: `tests/execution/__init__.py`
- Create: `tests/execution/test_types.py`

- [ ] **Step 1: Write failing tests**

Create `tests/execution/test_types.py`:

```python
import pytest
from datetime import datetime

def test_order_intent_creation():
    from bot.execution.types import OrderIntent
    oi = OrderIntent(
        passport_id="psp_abc", symbol="BTCUSDT", direction="LONG",
        signal_confidence=72.5, size_hint=0.02, stop_loss=29500.0,
        take_profit=31000.0, entry_price=30000.0, cooldown_key="psp_abc:BTCUSDT",
        metadata={"family": "ema_crossover"},
    )
    assert oi.direction == "LONG"
    assert oi.signal_confidence == 72.5

def test_order_intent_validates_direction():
    from bot.execution.types import OrderIntent
    with pytest.raises(ValueError):
        OrderIntent(passport_id="x", symbol="X", direction="INVALID",
                    signal_confidence=50, size_hint=0.01,
                    stop_loss=0, take_profit=0, entry_price=0,
                    cooldown_key="x", metadata={})

def test_fill_creation():
    from bot.execution.types import Fill
    f = Fill(order_intent_id="oi_1", fill_price=30050.0, fill_size=0.02,
             slippage_bps=1.67, fee_bps=4.0, timestamp=datetime.now(),
             is_paper=True)
    assert f.is_paper is True

def test_position_record():
    from bot.execution.types import PositionRecord
    p = PositionRecord(
        position_id="pos_1", passport_id="psp_abc", symbol="BTCUSDT",
        direction="LONG", entry_price=30000.0, current_price=30500.0,
        size=0.02, unrealized_pnl=10.0, stop_loss=29500.0,
        take_profit=31000.0, namespace="paper",
        opened_at=datetime.now(), status="open",
    )
    assert p.namespace == "paper"
    assert p.status == "open"
```

- [ ] **Step 2: Run tests — expected FAIL (module not found)**
- [ ] **Step 3: Implement types**

Create `bot/execution/types.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

VALID_DIRECTIONS = {"LONG", "SHORT"}
VALID_NAMESPACES = {"paper", "prod"}
VALID_STATUSES = {"open", "closed", "cancelled", "liquidated"}

@dataclass
class OrderIntent:
    passport_id: str
    symbol: str
    direction: str
    signal_confidence: float
    size_hint: float
    stop_loss: float
    take_profit: float
    entry_price: float
    cooldown_key: str
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"oi_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction: {self.direction}")

@dataclass
class Fill:
    order_intent_id: str
    fill_price: float
    fill_size: float
    slippage_bps: float
    fee_bps: float
    timestamp: datetime
    is_paper: bool
    fill_id: str = field(default_factory=lambda: f"fill_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")

@dataclass
class PositionRecord:
    position_id: str
    passport_id: str
    symbol: str
    direction: str
    entry_price: float
    current_price: float
    size: float
    unrealized_pnl: float
    stop_loss: float
    take_profit: float
    namespace: str
    opened_at: datetime
    status: str
    closed_at: Optional[datetime] = None
    realized_pnl: Optional[float] = None

    def __post_init__(self):
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction: {self.direction}")
        if self.namespace not in VALID_NAMESPACES:
            raise ValueError(f"Invalid namespace: {self.namespace}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {self.status}")
```

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/execution/ tests/execution/
git commit -m "feat(execution): add OrderIntent, Fill, PositionRecord types"
```

---

## Task 2: Position Manager

**Files:**
- Create: `bot/execution/position_manager.py`
- Create: `tests/execution/test_position_manager.py`

- [ ] **Step 1: Write failing tests**

Create `tests/execution/test_position_manager.py`:

```python
import pytest
from datetime import datetime, timedelta

def make_signal(direction="LONG", confidence=70.0, entry=30000.0, sl=29500.0, tp=31000.0):
    return {"direction": direction, "confidence": confidence,
            "entry_price": entry, "stop_loss": sl, "take_profit": tp}

def test_signal_to_intent():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=60)
    intent = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert intent is not None
    assert intent.direction == "LONG"
    assert intent.size_hint == 0.02

def test_cooldown_blocks():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=60)
    pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    blocked = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert blocked is None

def test_cooldown_expires():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=60)
    pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    pm._cooldowns["psp_abc:BTCUSDT"] = datetime.now() - timedelta(minutes=61)
    intent = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert intent is not None

def test_no_pyramiding_by_default():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, cooldown_minutes=0, max_pyramiding=1)
    pm._open_positions["psp_abc:BTCUSDT"] = 1
    intent = pm.signal_to_intent("psp_abc", "BTCUSDT", make_signal())
    assert intent is None

def test_low_confidence_rejected():
    from bot.execution.position_manager import PositionManager
    pm = PositionManager(default_size=0.02, min_confidence=60)
    sig = make_signal(confidence=50.0)
    assert pm.signal_to_intent("psp_abc", "BTCUSDT", sig) is None
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/execution/position_manager.py`:

- `PositionManager(default_size, cooldown_minutes=60, max_pyramiding=1, min_confidence=55)`
- `signal_to_intent(passport_id, symbol, signal_dict)` -> OrderIntent or None
- Internal: `_cooldowns` dict (key -> last_trade_time), `_open_positions` dict (key -> count)
- Checks: confidence >= min_confidence, cooldown expired, pyramiding not exceeded
- `record_fill(intent, fill)` — update open positions count
- `record_close(passport_id, symbol)` — decrement open positions

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/execution/position_manager.py tests/execution/test_position_manager.py
git commit -m "feat(execution): add PositionManager with cooldown and pyramiding"
```

---

## Task 3: Portfolio Risk Manager

**Files:**
- Create: `bot/risk/__init__.py`
- Create: `bot/risk/portfolio_risk.py`
- Create: `tests/risk/__init__.py`
- Create: `tests/risk/test_portfolio_risk.py`

- [ ] **Step 1: Write failing tests**

Create `tests/risk/test_portfolio_risk.py`:

```python
import pytest

def make_intent(passport_id="psp_a", symbol="BTCUSDT", direction="LONG",
                size=0.02, entry=30000.0, family="ema"):
    from bot.execution.types import OrderIntent
    return OrderIntent(passport_id=passport_id, symbol=symbol,
        direction=direction, signal_confidence=70, size_hint=size,
        stop_loss=entry*0.98, take_profit=entry*1.04,
        entry_price=entry, cooldown_key=f"{passport_id}:{symbol}",
        metadata={"family": family})

def test_approve_within_limits():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000)
    result = prm.evaluate(make_intent())
    assert result["action"] == "approve"

def test_reject_exposure_cap():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.01, account_equity=10000)
    result = prm.evaluate(make_intent(size=0.5))
    assert result["action"] == "reject"
    assert "exposure" in result["reason"].lower()

def test_reject_family_cap():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=100000, family_cap=2)
    prm.record_position("psp_1", "ema", 0.02)
    prm.record_position("psp_2", "ema", 0.02)
    result = prm.evaluate(make_intent(passport_id="psp_3", family="ema"))
    assert result["action"] == "reject"
    assert "family" in result["reason"].lower()

def test_dd_circuit_breaker():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000,
                                dd_circuit_breaker=0.15)
    prm.update_drawdown("psp_a", 0.18)
    result = prm.evaluate(make_intent())
    assert result["action"] == "reject"
    assert "drawdown" in result["reason"].lower()

def test_resize_action():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.05, account_equity=10000)
    prm.record_position("psp_other", "rsi", 0.03)
    result = prm.evaluate(make_intent(size=0.03))
    assert result["action"] in ("resize", "reject")

def test_emergency_pause():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000)
    prm.emergency_pause()
    result = prm.evaluate(make_intent())
    assert result["action"] == "reject"
    assert "emergency" in result["reason"].lower()
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/risk/portfolio_risk.py`:

- `PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000, family_cap=3, cluster_cap=3, dd_circuit_breaker=0.15)`
- `evaluate(intent)` -> dict with action (approve/resize/reject), reason, adjusted_size
- `record_position(passport_id, family, size)` — track active positions
- `close_position(passport_id)` — remove from tracking
- `update_drawdown(passport_id, current_dd)` — update per-strategy DD
- `emergency_pause()` / `resume()` — global halt
- Hard limits: exposure cap, family cap, DD circuit breaker
- Soft alerts: returns alert_messages list in evaluate result

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/risk/ tests/risk/
git commit -m "feat(risk): add PortfolioRiskManager with hard limits and soft alerts"
```

---

## Task 4: Namespace Manager (Paper/Prod Isolation)

**Files:**
- Create: `bot/risk/namespace.py`
- Create: `tests/risk/test_namespace.py`

- [ ] **Step 1: Write failing tests**

Create `tests/risk/test_namespace.py`:

```python
import os, tempfile, pytest

@pytest.fixture
def ns_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d

def test_paper_namespace(ns_dir):
    from bot.risk.namespace import NamespaceManager
    ns = NamespaceManager(ns_dir, "paper")
    assert ns.table_prefix == "paper_"
    assert ns.telegram_prefix == "[PAPER]"

def test_prod_namespace(ns_dir):
    from bot.risk.namespace import NamespaceManager
    ns = NamespaceManager(ns_dir, "prod")
    assert ns.table_prefix == "prod_"
    assert ns.telegram_prefix == "[PROD]"

def test_separate_dbs(ns_dir):
    from bot.risk.namespace import NamespaceManager
    paper = NamespaceManager(ns_dir, "paper")
    prod = NamespaceManager(ns_dir, "prod")
    assert paper.db_path != prod.db_path

def test_no_cross_access(ns_dir):
    from bot.risk.namespace import NamespaceManager
    paper = NamespaceManager(ns_dir, "paper")
    paper.write_position({"id": "pos1", "symbol": "BTC"})
    prod = NamespaceManager(ns_dir, "prod")
    assert prod.read_positions() == []

def test_invalid_namespace():
    from bot.risk.namespace import NamespaceManager
    with pytest.raises(ValueError):
        NamespaceManager("/tmp", "staging")
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/risk/namespace.py`:

- `NamespaceManager(base_dir, namespace)` — validates paper/prod only
- Properties: `table_prefix`, `telegram_prefix`, `db_path`
- Methods: `write_position(data)`, `read_positions()`, `write_fill(data)`, `read_fills()`, `clear_all()` (for testing)
- Uses separate SQLite files: `paper.db` / `prod.db`

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/risk/namespace.py tests/risk/test_namespace.py
git commit -m "feat(risk): add NamespaceManager for paper/prod isolation"
```

---

## Task 5: Scheduler and Workers

**Files:**
- Create: `bot/scheduler/__init__.py`
- Create: `bot/scheduler/orchestrator.py`
- Create: `bot/scheduler/worker.py`
- Create: `tests/scheduler/__init__.py`
- Create: `tests/scheduler/test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scheduler/test_orchestrator.py`:

```python
import pytest, tempfile

def test_load_active_passports():
    from bot.scheduler.orchestrator import Orchestrator
    with tempfile.TemporaryDirectory() as d:
        orch = Orchestrator(registry_dir=d, namespace="paper", scan_interval=60)
        passports = orch.load_active_passports()
        assert isinstance(passports, list)

def test_group_passports():
    from bot.scheduler.orchestrator import Orchestrator
    orch = Orchestrator.__new__(Orchestrator)
    groups = orch.group_passports(
        [{"passport_id": f"p{i}", "interval": "4h"} for i in range(6)],
        max_per_group=3)
    assert len(groups) == 2

def test_worker_pipeline():
    from bot.scheduler.worker import Worker
    w = Worker.__new__(Worker)
    assert hasattr(w, "run_single")

def test_rate_limiter():
    from bot.scheduler.orchestrator import RateLimiter
    rl = RateLimiter(max_calls=5, window_seconds=60)
    for _ in range(5):
        assert rl.allow()
    assert not rl.allow()
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/scheduler/orchestrator.py`:

- `RateLimiter(max_calls, window_seconds)` — sliding window
- `Orchestrator(registry_dir, namespace, scan_interval, max_workers=3, rate_limit=30)`
  - `load_active_passports()` — reads registry for paper_live/production status
  - `group_passports(passports, max_per_group)` — round-robin by family
  - `run_cycle()` — load → group → dispatch workers → collect intents → risk check
  - `start()` / `stop()` — main loop with graceful shutdown

Create `bot/scheduler/worker.py`:

- `Worker(passport_config, position_manager, namespace_manager)`
  - `run_single(symbol)` — fetch data → score → signal_to_intent → return intent or None
  - `run_batch(symbols)` — run_single for each symbol, return list of intents

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/scheduler/ tests/scheduler/
git commit -m "feat(scheduler): add Orchestrator, Worker, RateLimiter"
```

---

## Task 6: Telegram Commands

**Files:**
- Create: `bot/telegram_commands.py`
- Create: `tests/test_telegram_commands.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_telegram_commands.py`:

```python
import pytest

def test_format_strategies_list():
    from bot.telegram_commands import format_strategies_list
    strategies = [{"slug": "ema-fast", "status": "paper_live", "pnl": 5.2},
                  {"slug": "rsi-rev", "status": "paper_live", "pnl": -1.3}]
    text = format_strategies_list(strategies)
    assert "ema-fast" in text
    assert "5.2" in text

def test_format_compare():
    from bot.telegram_commands import format_compare
    a = {"slug": "A", "sharpe": 1.2, "return_pct": 8.5, "max_dd": 12.0, "trades": 45}
    b = {"slug": "B", "sharpe": 0.8, "return_pct": 5.2, "max_dd": 18.0, "trades": 32}
    text = format_compare(a, b)
    assert "A" in text and "B" in text

def test_format_health():
    from bot.telegram_commands import format_health
    health = {"last_scan": "2025-01-01 12:00", "api_latency_ms": 120,
              "error_rate": 0.01, "active_passports": 12}
    text = format_health(health)
    assert "12" in text

def test_promotion_check_format():
    from bot.telegram_commands import format_promotion_check
    result = {"passport_id": "psp_abc", "passed": True, "checks": [
        {"name": "min_days", "passed": True, "detail": "21 days"},
        {"name": "min_trades", "passed": True, "detail": "45 trades"},
    ]}
    text = format_promotion_check(result)
    assert "psp_abc" in text

def test_daily_digest():
    from bot.telegram_commands import format_daily_digest
    data = {"total_pnl": 125.50, "strategies": [
        {"slug": "ema-fast", "pnl": 80.0, "trades_today": 3},
        {"slug": "rsi-rev", "pnl": 45.5, "trades_today": 1},
    ]}
    text = format_daily_digest(data)
    assert "125" in text
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/telegram_commands.py`:

Formatting functions (pure, testable):
- `format_strategies_list(strategies)` -> str
- `format_compare(a, b)` -> str
- `format_health(health_data)` -> str
- `format_promotion_check(result)` -> str
- `format_daily_digest(data)` -> str

Command handlers (integration):
- `handle_strategies(update, context)` — fetch from registry + state_db
- `handle_compare(update, context)` — parse args, fetch metrics
- `handle_promote(update, context)` — trigger promotion gate check
- `handle_pause(update, context)` — call PortfolioRiskManager.emergency_pause
- `handle_health(update, context)` — fetch from HealthMonitor
- `register_commands(application)` — register all handlers

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/telegram_commands.py tests/test_telegram_commands.py
git commit -m "feat(telegram): add /strategies, /compare, /promote, /pause, /health commands"
```

---

## Task 7: Health Monitor

**Files:**
- Create: `bot/health/__init__.py`
- Create: `bot/health/monitor.py`
- Create: `tests/health/__init__.py`
- Create: `tests/health/test_monitor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/health/test_monitor.py`:

```python
import pytest
from datetime import datetime, timedelta

def test_scan_freshness_ok():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(scan_interval=300)
    hm.record_scan(datetime.now())
    assert hm.check_scan_freshness()["healthy"] is True

def test_scan_freshness_stale():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(scan_interval=300)
    hm.record_scan(datetime.now() - timedelta(seconds=700))
    result = hm.check_scan_freshness()
    assert result["healthy"] is False

def test_api_latency_ok():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor()
    hm.record_api_latency(120)
    assert hm.check_api_health()["healthy"] is True

def test_api_latency_degraded():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(api_latency_warn=200)
    hm.record_api_latency(250)
    assert hm.check_api_health()["healthy"] is False

def test_full_health_report():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor()
    hm.record_scan(datetime.now())
    hm.record_api_latency(100)
    report = hm.full_report()
    assert "scan_freshness" in report
    assert "api_health" in report
    assert all(v["healthy"] for v in report.values())

def test_error_rate_alert():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(error_rate_warn=0.05)
    for _ in range(10):
        hm.record_api_call(success=False)
    assert hm.check_api_health()["healthy"] is False
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/health/monitor.py`:

- `HealthMonitor(scan_interval=300, api_latency_warn=500, error_rate_warn=0.1)`
- `record_scan(timestamp)`, `record_api_latency(ms)`, `record_api_call(success)`
- `check_scan_freshness()` -> dict with healthy, detail
- `check_api_health()` -> dict (latency + error rate)
- `check_db_health()` -> dict (write test)
- `check_telegram_health()` -> dict (last heartbeat)
- `full_report()` -> dict of all checks
- `get_alerts()` -> list of unhealthy items

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/health/ tests/health/
git commit -m "feat(health): add operational HealthMonitor"
```

---

## Task 8: Promotion Engine

**Files:**
- Create: `bot/health/promotion.py`
- Create: `tests/health/test_promotion.py`

- [ ] **Step 1: Write failing tests**

Create `tests/health/test_promotion.py`:

```python
import pytest
from datetime import datetime, timedelta

def make_paper_record(days=21, trades=45, dd=0.10, divergence=0.15):
    return {"passport_id": "psp_abc", "paper_start": datetime.now() - timedelta(days=days),
            "trade_count": trades, "max_drawdown": dd, "backtest_dd": 0.12,
            "divergence_score": divergence, "paused": False,
            "family": "ema_crossover", "cluster": 0}

def test_promotion_pass():
    from bot.health.promotion import PromotionEngine
    pe = PromotionEngine(min_paper_days=14, min_trades=10, max_divergence=0.3)
    result = pe.check(make_paper_record())
    assert result["passed"] is True
    assert all(c["passed"] for c in result["checks"])

def test_promotion_fail_min_days():
    from bot.health.promotion import PromotionEngine
    pe = PromotionEngine(min_paper_days=14)
    result = pe.check(make_paper_record(days=7))
    assert result["passed"] is False

def test_promotion_fail_min_trades():
    from bot.health.promotion import PromotionEngine
    pe = PromotionEngine(min_trades=10)
    result = pe.check(make_paper_record(trades=5))
    assert result["passed"] is False

def test_promotion_fail_paused():
    from bot.health.promotion import PromotionEngine
    pe = PromotionEngine()
    rec = make_paper_record()
    rec["paused"] = True
    result = pe.check(rec)
    assert result["passed"] is False

def test_promotion_fail_divergence():
    from bot.health.promotion import PromotionEngine
    pe = PromotionEngine(max_divergence=0.2)
    result = pe.check(make_paper_record(divergence=0.5))
    assert result["passed"] is False
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/health/promotion.py`:

- `PromotionEngine(min_paper_days=14, min_trades=10, max_divergence=0.3, family_cap=3, cluster_cap=3)`
- `check(paper_record)` -> dict with passed, checks list, passport_id
- Checks: min_paper_days, min_trades, not_paused, divergence_within_bounds, dd_not_catastrophic, family_cap_ok, cluster_cap_ok
- Each check returns {name, passed, detail} for transparent reporting

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/health/promotion.py tests/health/test_promotion.py
git commit -m "feat(health): add PromotionEngine with 7-point policy gate"
```

---

## Task 9: State DB and Deployment Scripts

**Files:**
- Create: `bot/deploy/__init__.py`
- Create: `bot/deploy/state_db.py`
- Create: `bot/deploy/vps_setup.py`
- Create: `tests/deploy/__init__.py`
- Create: `tests/deploy/test_state_db.py`

- [ ] **Step 1: Write failing tests**

Create `tests/deploy/test_state_db.py`:

```python
import os, tempfile, pytest

@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        yield os.path.join(d, "test.db")

def test_init_schema(db_path):
    from bot.deploy.state_db import StateDB
    db = StateDB(db_path)
    db.init_schema()
    tables = db.list_tables()
    assert "passports" in tables
    assert "positions_paper" in tables
    assert "alerts" in tables

def test_insert_and_read_position(db_path):
    from bot.deploy.state_db import StateDB
    db = StateDB(db_path)
    db.init_schema()
    db.insert_position("paper", {"position_id": "pos_1", "symbol": "BTC", "pnl": 5.0})
    rows = db.read_positions("paper")
    assert len(rows) == 1 and rows[0]["symbol"] == "BTC"

def test_paper_prod_isolation(db_path):
    from bot.deploy.state_db import StateDB
    db = StateDB(db_path)
    db.init_schema()
    db.insert_position("paper", {"position_id": "p1", "symbol": "BTC", "pnl": 5.0})
    db.insert_position("prod", {"position_id": "p2", "symbol": "ETH", "pnl": 10.0})
    assert len(db.read_positions("paper")) == 1
    assert len(db.read_positions("prod")) == 1

def test_migration_idempotent(db_path):
    from bot.deploy.state_db import StateDB
    db = StateDB(db_path)
    db.init_schema()
    db.init_schema()  # should not error
```

- [ ] **Step 2: Run tests — expected FAIL**
- [ ] **Step 3: Implement**

Create `bot/deploy/state_db.py`:

- `StateDB(db_path)` — SQLite wrapper
- `init_schema()` — CREATE TABLE IF NOT EXISTS for all tables (passports, passport_state, positions_paper, positions_prod, fills, trades, portfolio_snapshots, equity_curves, alerts, health_heartbeats, error_log, promotion_events, retirement_events, experiment_runs, experiment_metrics)
- `insert_position(namespace, data)`, `read_positions(namespace)`, `list_tables()`
- `insert_alert(data)`, `read_alerts(since)`, `insert_heartbeat()`, `read_last_heartbeat()`

Create `bot/deploy/vps_setup.py`:

- `generate_systemd_unit(service_name, command, user, working_dir)` -> str (unit file content)
- `generate_deploy_script(vps_host, deploy_dir, services)` -> str (bash deploy script)
- `sync_passports(local_dir, remote_host, remote_dir)` — rsync wrapper
- `create_artifact_bundle(passport_ids, registry_path, output_path)` — zip for transfer

- [ ] **Step 4: Run tests — expected PASS**
- [ ] **Step 5: Commit**

```bash
git add bot/deploy/ tests/deploy/
git commit -m "feat(deploy): add StateDB schema and VPS deployment scripts"
```

---

## Task 10: Integration Test + Full Verification

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Verify import chain**

```bash
python -c "
from bot.execution.types import OrderIntent, Fill, PositionRecord
from bot.execution.position_manager import PositionManager
from bot.risk.portfolio_risk import PortfolioRiskManager
from bot.risk.namespace import NamespaceManager
from bot.scheduler.orchestrator import Orchestrator
from bot.health.monitor import HealthMonitor
from bot.health.promotion import PromotionEngine
from bot.deploy.state_db import StateDB
print('All Plan 3 modules OK')
"
```

- [ ] **Step 3: Write integration test**

Create `tests/test_integration_plan3.py`:

```python
import tempfile, pytest

def test_signal_to_execution_pipeline():
    """End-to-end: signal → PositionManager → Risk check → Fill"""
    from bot.execution.position_manager import PositionManager
    from bot.risk.portfolio_risk import PortfolioRiskManager

    pm = PositionManager(default_size=0.02, cooldown_minutes=0)
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000)

    signal = {"direction": "LONG", "confidence": 72, "entry_price": 30000,
              "stop_loss": 29500, "take_profit": 31000}
    intent = pm.signal_to_intent("psp_a", "BTCUSDT", signal)
    assert intent is not None

    risk_result = prm.evaluate(intent)
    assert risk_result["action"] == "approve"

def test_paper_prod_full_isolation():
    """Verify paper and prod never share state"""
    import os, tempfile
    from bot.risk.namespace import NamespaceManager

    with tempfile.TemporaryDirectory() as d:
        paper = NamespaceManager(d, "paper")
        prod = NamespaceManager(d, "prod")
        paper.write_position({"id": "p1", "symbol": "BTC"})
        assert len(paper.read_positions()) == 1
        assert len(prod.read_positions()) == 0
```

- [ ] **Step 4: Run integration tests — expected PASS**

```bash
python -m pytest tests/test_integration_plan3.py -v
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "test(plan3): full Plan 3 integration verified"
```
