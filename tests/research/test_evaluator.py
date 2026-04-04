"""Tests for evaluation pipeline stages."""
import pytest
from bot.research.types import BacktestMetrics, EvalResult
from bot.research.evaluator import Stage1Evaluator


class TestStage1Evaluator:
    def setup_method(self):
        self.evaluator = Stage1Evaluator()

    def test_pass_healthy_metrics(self):
        metrics = BacktestMetrics(
            trades=50, wins=28, losses=22, win_rate=56.0,
            return_pct=15.0, max_dd=25.0, sharpe=1.2,
            profit_factor=1.4, final_equity=1150.0,
        )
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is True
        assert result.stage == 1

    def test_fail_insufficient_trades(self):
        metrics = BacktestMetrics(trades=5, return_pct=50.0, max_dd=10.0)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        assert "trades" in result.reject_reason.lower()

    def test_fail_catastrophic_drawdown(self):
        metrics = BacktestMetrics(trades=50, return_pct=5.0, max_dd=55.0)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        assert "drawdown" in result.reject_reason.lower()

    def test_fail_severe_loss(self):
        metrics = BacktestMetrics(trades=50, return_pct=-25.0, max_dd=30.0)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        assert "return" in result.reject_reason.lower()

    def test_custom_min_trades(self):
        metrics = BacktestMetrics(trades=18, return_pct=10.0, max_dd=20.0, profit_factor=1.2)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=15)
        assert result.passed is True

    def test_fail_fees_dominate(self):
        metrics = BacktestMetrics(
            trades=50, return_pct=-5.0, max_dd=20.0, profit_factor=0.7,
        )
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False

    def test_collects_secondary_reasons(self):
        metrics = BacktestMetrics(trades=5, return_pct=-30.0, max_dd=60.0, profit_factor=0.5)
        result = self.evaluator.evaluate("psp_001", metrics, min_trades=30)
        assert result.passed is False
        total_reasons = 1 + len(result.secondary_reasons)
        assert total_reasons >= 2
