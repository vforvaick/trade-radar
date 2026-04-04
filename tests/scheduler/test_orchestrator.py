"""Tests for Scheduler (RateLimiter, Worker, Orchestrator)."""
import pytest


def test_rate_limiter_allows():
    from bot.scheduler.orchestrator import RateLimiter
    rl = RateLimiter(max_calls=5, window_seconds=60)
    for _ in range(5):
        assert rl.acquire() is True
    assert rl.acquire() is False


def test_worker_runs_strategy():
    from bot.scheduler.orchestrator import Worker
    w = Worker()
    def dummy_strategy(**kwargs):
        return {"signal": "LONG"}
    result = w.run_single("psp_a", "BTCUSDT", dummy_strategy)
    assert result["status"] == "ok"
    assert result["result"]["signal"] == "LONG"


def test_worker_catches_errors():
    from bot.scheduler.orchestrator import Worker
    w = Worker()
    def failing_strategy(**kwargs):
        raise RuntimeError("API timeout")
    result = w.run_single("psp_a", "BTCUSDT", failing_strategy)
    assert result["status"] == "error"
    assert "timeout" in result["error"].lower()


def test_worker_rate_limited():
    from bot.scheduler.orchestrator import Worker, RateLimiter
    rl = RateLimiter(max_calls=1, window_seconds=60)
    w = Worker(rl)
    def dummy(**kwargs):
        return {}
    w.run_single("a", "BTC", dummy)
    r2 = w.run_single("b", "ETH", dummy)
    assert r2["status"] == "rate_limited"


def test_orchestrator_batch():
    from bot.scheduler.orchestrator import Orchestrator, RateLimiter
    rl = RateLimiter(max_calls=100, window_seconds=60)
    orch = Orchestrator(rl)
    orch.add_task("psp_a", "BTCUSDT")
    orch.add_task("psp_b", "ETHUSDT")
    results = orch.run_all(lambda **kw: {"sig": kw["symbol"]})
    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)
