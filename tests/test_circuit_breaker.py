"""Tests for circuit breaker (kill switch)."""
from unittest.mock import MagicMock, patch

import pytest

from bot.risk.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_no_trigger_above_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=400, initial_equity=500) is False

    def test_trigger_at_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=350, initial_equity=500) is True

    def test_trigger_below_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=300, initial_equity=500) is True

    def test_custom_threshold(self):
        cb = CircuitBreaker(kill_threshold_pct=0.50)
        assert cb.should_kill("TestPassport", current_equity=260, initial_equity=500) is False
        assert cb.should_kill("TestPassport", current_equity=250, initial_equity=500) is True

    def test_zero_initial_equity_no_crash(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        assert cb.should_kill("TestPassport", current_equity=0, initial_equity=0) is False

    def test_per_passport_override(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        # 20% drawdown with 50% threshold = should NOT kill
        assert cb.should_kill(
            "TestPassport", current_equity=80, initial_equity=100,
            override_threshold=0.50,
        ) is False
        # 20% drawdown with 10% threshold = should kill
        assert cb.should_kill(
            "TestPassport", current_equity=80, initial_equity=100,
            override_threshold=0.10,
        ) is True


class TestCircuitBreakerLog:
    def test_kill_event_logged(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        cb.should_kill("TestPassport", current_equity=300, initial_equity=500)
        assert len(cb.kill_log) == 1
        assert cb.kill_log[0]["passport"] == "TestPassport"
        assert cb.kill_log[0]["equity"] == 300

    def test_no_duplicate_kill_log(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        cb.should_kill("TestPassport", current_equity=300, initial_equity=500)
        cb.should_kill("TestPassport", current_equity=280, initial_equity=500)
        assert len(cb.kill_log) == 1  # only first trigger logged

    def test_different_passports_logged_separately(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        cb.should_kill("Passport1", current_equity=300, initial_equity=500)
        cb.should_kill("Passport2", current_equity=300, initial_equity=500)
        assert len(cb.kill_log) == 2
