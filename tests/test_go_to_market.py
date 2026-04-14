"""Tests for go-to-market 10-gate scorecard."""
import pytest

from bot.deploy.go_to_market import GoToMarketScorecard, GateResult, ScorecardResult


class TestGateResult:
    def test_pass(self):
        r = GateResult(gate="gate_1_return", passed=True, value=18.5, threshold=15.0)
        assert r.passed is True

    def test_fail(self):
        r = GateResult(gate="gate_1_return", passed=False, value=10.0, threshold=15.0)
        assert r.passed is False


class TestScorecardResult:
    def test_all_pass(self):
        gates = [
            GateResult("g1", True, 20, 15),
            GateResult("g2", True, 1.5, 1.3),
        ]
        result = ScorecardResult(passport_name="Test", gates=gates)
        assert result.all_passed is True
        assert result.passed_count == 2
        assert result.total_count == 2

    def test_partial_pass(self):
        gates = [
            GateResult("g1", True, 20, 15),
            GateResult("g2", False, 1.1, 1.3),
        ]
        result = ScorecardResult(passport_name="Test", gates=gates)
        assert result.all_passed is False
        assert result.passed_count == 1


class TestGoToMarketScorecard:
    def test_backtest_gates_pass(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 18.5,
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 35,
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        assert result.all_passed is True
        assert result.passed_count == 10

    def test_backtest_gates_fail_return(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 10.0,  # below 15%
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 35,
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        assert result.all_passed is False
        assert result.passed_count == 9
        failed = [g for g in result.gates if not g.passed]
        assert failed[0].gate == "gate_1_return"

    def test_paper_gates_fail_days(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 20.0,
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 20,  # below 30
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        assert result.all_passed is False
        failed = [g for g in result.gates if not g.passed]
        assert any(g.gate == "gate_8_paper_days" for g in failed)

    def test_missing_metric_raises(self):
        sc = GoToMarketScorecard()
        with pytest.raises(KeyError):
            sc.evaluate("TestPassport", {"return_pct_180d": 20.0})

    def test_format_table(self):
        sc = GoToMarketScorecard()
        metrics = {
            "return_pct_180d": 18.5,
            "profit_factor": 1.5,
            "max_drawdown": 30.0,
            "total_trades": 120,
            "win_rate": 42.0,
            "mc_profitable_pct": 75.0,
            "correlation_group_rank": 1,
            "paper_days": 35,
            "paper_pnl": 50.0,
            "max_single_loss_pct": 5.0,
        }
        result = sc.evaluate("TestPassport", metrics)
        table = result.format_table()
        assert "TestPassport" in table
        assert "✅" in table
