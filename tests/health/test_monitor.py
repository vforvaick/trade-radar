"""Tests for HealthMonitor."""
import pytest
from datetime import datetime, timedelta


def test_fresh_data_ok():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(max_data_age_minutes=15)
    hm.record_data_update()
    assert hm.scan_freshness()["ok"] is True


def test_stale_data_fail():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(max_data_age_minutes=5)
    hm.record_data_update(datetime.now() - timedelta(minutes=10))
    assert hm.scan_freshness()["ok"] is False


def test_api_latency_ok():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(max_api_latency_ms=5000)
    for _ in range(5):
        hm.record_api_call(200)
    assert hm.api_latency()["ok"] is True


def test_api_latency_fail():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(max_api_latency_ms=100)
    for _ in range(5):
        hm.record_api_call(500)
    assert hm.api_latency()["ok"] is False


def test_error_rate():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor(max_error_rate=0.1)
    for _ in range(9):
        hm.record_api_call(100, is_error=False)
    hm.record_api_call(100, is_error=True)
    assert hm.error_rate()["ok"] is True  # 10% = threshold


def test_full_check():
    from bot.health.monitor import HealthMonitor
    hm = HealthMonitor()
    hm.record_data_update()
    hm.record_api_call(100)
    result = hm.full_check()
    assert result["healthy"] is True
    assert "data_freshness" in result["checks"]
