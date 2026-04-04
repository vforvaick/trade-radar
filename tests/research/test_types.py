"""Tests for research engine core types."""
import pytest
from bot.research.types import (
    RegimeType,
    PassportCandidate,
    EvalResult,
    ExperimentResult,
    BacktestMetrics,
)


class TestRegimeType:
    def test_regime_enum_has_four_values(self):
        assert len(RegimeType) == 4

    def test_regime_values(self):
        assert RegimeType.TREND_UP.value == "TREND_UP"
        assert RegimeType.TREND_DOWN.value == "TREND_DOWN"
        assert RegimeType.HIGH_VOL_CHOP.value == "HIGH_VOL_CHOP"
        assert RegimeType.LOW_VOL_COMPRESSION.value == "LOW_VOL_COMPRESSION"


class TestBacktestMetrics:
    def test_create_from_summary_dict(self):
        summary = {
            "trades": 50,
            "wins": 25,
            "losses": 25,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "return_pct": 10.0,
            "final_equity": 1100.0,
            "max_dd": 15.0,
            "sharpe": 1.2,
            "sortino": 1.5,
            "calmar": 0.8,
            "profit_factor": 1.3,
        }
        m = BacktestMetrics.from_summary(summary)
        assert m.trades == 50
        assert m.win_rate == 50.0
        assert m.sharpe == 1.2
        assert m.max_dd == 15.0

    def test_from_summary_handles_missing_keys(self):
        summary = {"trades": 0, "return_pct": 0.0, "max_dd": 0.0}
        m = BacktestMetrics.from_summary(summary)
        assert m.trades == 0
        assert m.sharpe == 0.0


class TestPassportCandidate:
    def test_create_passport_candidate(self):
        pc = PassportCandidate(
            passport_id="psp_test_001",
            slug="ema_crossover-fast_9_26",
            family="ema_crossover",
            config_overrides={
                "INDICATOR_WEIGHTS": {"ema_trend": 2.0},
                "CONFIDENCE_THRESHOLD": 60,
            },
        )
        assert pc.passport_id.startswith("psp_")
        assert pc.family == "ema_crossover"
        assert pc.config_overrides["CONFIDENCE_THRESHOLD"] == 60

    def test_passport_candidate_has_default_status(self):
        pc = PassportCandidate(
            passport_id="psp_test_002",
            slug="test",
            family="test",
            config_overrides={},
        )
        assert pc.status == "generated"


class TestEvalResult:
    def test_eval_result_stage1_pass(self):
        er = EvalResult(
            passport_id="psp_test_001",
            stage=1,
            passed=True,
            metrics={"trades": 50, "max_dd": 30.0},
        )
        assert er.passed is True
        assert er.reject_reason is None

    def test_eval_result_stage1_fail(self):
        er = EvalResult(
            passport_id="psp_test_001",
            stage=1,
            passed=False,
            metrics={"trades": 5},
            reject_reason="Insufficient trades: 5 < 30",
        )
        assert er.passed is False
        assert "Insufficient" in er.reject_reason


class TestExperimentResult:
    def test_create_experiment_result(self):
        er = ExperimentResult(
            run_id="exp-2026-04-04-001",
            total_generated=400,
            stage1_survivors=180,
            stage2_survivors=45,
        )
        assert er.total_generated == 400
        assert er.stage2_survivors == 45
