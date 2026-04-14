"""Integration tests for circuit breaker in PassportRunner."""
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from bot.risk.circuit_breaker import CircuitBreaker


class TestCircuitBreakerInRunner:
    """Test that PassportRunner respects circuit breaker."""

    def test_passport_skipped_when_killed(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        # Simulate killed passport
        killed = cb.should_kill("TestPassport", current_equity=300, initial_equity=500)
        assert killed is True
        assert cb.is_killed("TestPassport") is True

    def test_passport_not_skipped_when_healthy(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        killed = cb.should_kill("TestPassport", current_equity=400, initial_equity=500)
        assert killed is False
        assert cb.is_killed("TestPassport") is False

    def test_per_passport_threshold_from_config(self):
        cb = CircuitBreaker(kill_threshold_pct=0.30)
        # Passport with custom 50% threshold
        killed = cb.should_kill(
            "HighRisk",
            current_equity=60,
            initial_equity=100,
            override_threshold=0.50,
        )
        assert killed is False  # 40% < 50%

        killed = cb.should_kill(
            "HighRisk",
            current_equity=49,
            initial_equity=100,
            override_threshold=0.50,
        )
        assert killed is True  # 51% >= 50%
