"""Health Monitor — data freshness, API latency, error rate checks."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


class HealthMonitor:
    """Monitors operational health of the trading system."""

    def __init__(
        self,
        max_data_age_minutes: int = 15,
        max_api_latency_ms: float = 5000,
        max_error_rate: float = 0.1,
    ):
        self.max_data_age_minutes = max_data_age_minutes
        self.max_api_latency_ms = max_api_latency_ms
        self.max_error_rate = max_error_rate
        self._last_data_time: Optional[datetime] = None
        self._api_latencies: list[float] = []
        self._total_requests: int = 0
        self._error_count: int = 0

    def record_data_update(self, ts: Optional[datetime] = None):
        self._last_data_time = ts or datetime.now()

    def record_api_call(self, latency_ms: float, is_error: bool = False):
        self._total_requests += 1
        self._api_latencies.append(latency_ms)
        if len(self._api_latencies) > 100:
            self._api_latencies = self._api_latencies[-100:]
        if is_error:
            self._error_count += 1

    def scan_freshness(self) -> dict:
        if self._last_data_time is None:
            return {"ok": False, "detail": "No data received yet"}
        age = datetime.now() - self._last_data_time
        age_min = age.total_seconds() / 60
        ok = age_min <= self.max_data_age_minutes
        return {"ok": ok, "detail": f"{age_min:.1f}min ago"}

    def api_latency(self) -> dict:
        if not self._api_latencies:
            return {"ok": True, "detail": "No API calls yet"}
        avg = sum(self._api_latencies[-20:]) / len(self._api_latencies[-20:])
        ok = avg <= self.max_api_latency_ms
        return {"ok": ok, "detail": f"{avg:.0f}ms avg"}

    def error_rate(self) -> dict:
        if self._total_requests == 0:
            return {"ok": True, "detail": "No requests yet"}
        rate = self._error_count / self._total_requests
        ok = rate <= self.max_error_rate
        return {"ok": ok, "detail": f"{rate:.1%}"}

    def full_check(self) -> dict:
        checks = {
            "data_freshness": self.scan_freshness(),
            "api_latency": self.api_latency(),
            "error_rate": self.error_rate(),
        }
        healthy = all(c["ok"] for c in checks.values())
        return {"healthy": healthy, "checks": checks}
