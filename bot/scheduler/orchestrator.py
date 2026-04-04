"""Scheduler — rate limiter, orchestrator, and worker for strategy execution."""
from __future__ import annotations

import time
from collections import deque
from typing import Callable, Optional


class RateLimiter:
    """Sliding-window rate limiter for API calls."""

    def __init__(self, max_calls: int = 10, window_seconds: float = 60.0):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()

    def acquire(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_calls:
            return False
        self._timestamps.append(now)
        return True

    def wait_and_acquire(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.acquire():
                return True
            time.sleep(0.1)
        return False


class Worker:
    """Executes a single strategy tick."""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.rate_limiter = rate_limiter

    def run_single(self, passport_id: str, symbol: str,
                   strategy_fn: Callable, **kwargs) -> Optional[dict]:
        if self.rate_limiter and not self.rate_limiter.acquire():
            return {"status": "rate_limited", "passport_id": passport_id}
        try:
            result = strategy_fn(passport_id=passport_id, symbol=symbol, **kwargs)
            return {"status": "ok", "passport_id": passport_id, "result": result}
        except Exception as e:
            return {"status": "error", "passport_id": passport_id, "error": str(e)}

    def run_batch(self, tasks: list[dict], strategy_fn: Callable) -> list[dict]:
        results = []
        for task in tasks:
            r = self.run_single(
                passport_id=task["passport_id"],
                symbol=task["symbol"],
                strategy_fn=strategy_fn,
                **task.get("kwargs", {}),
            )
            results.append(r)
        return results


class Orchestrator:
    """Coordinates strategy execution across multiple passports."""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.rate_limiter = rate_limiter or RateLimiter()
        self.worker = Worker(self.rate_limiter)
        self._schedule: list[dict] = []

    def add_task(self, passport_id: str, symbol: str, **kwargs):
        self._schedule.append({"passport_id": passport_id, "symbol": symbol, "kwargs": kwargs})

    def run_all(self, strategy_fn: Callable) -> list[dict]:
        results = self.worker.run_batch(self._schedule, strategy_fn)
        self._schedule.clear()
        return results
