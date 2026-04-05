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


class TestStage3Result:
    def test_stage3_result_creation(self):
        from bot.research.types import Stage3Result
        r = Stage3Result(
            passport_id="psp_test", survival_rate=0.72,
            mean_perturbed_return=8.5, original_return=12.0,
            p5_return=-5.2, p95_return=22.0, iqr_return=10.5,
            passed=True, reject_reason=None, mc_iterations=50,
            perturbation_details=[],
        )
        assert r.passed is True
        assert r.survival_rate == 0.72


class TestStage4Result:
    def test_stage4_result_creation(self):
        from bot.research.types import Stage4Result
        r = Stage4Result(
            selected_passport_ids=["psp_a", "psp_b"],
            portfolio_utility=2.35, portfolio_sharpe=1.2, portfolio_max_dd=15.0,
            family_counts={"ema_crossover": 2}, cluster_counts={0: 2},
            correlation_matrix={"psp_a|psp_b": 0.15}, rejection_log=[],
        )
        assert len(r.selected_passport_ids) == 2


class TestPortfolioSelection:
    def test_portfolio_selection(self):
        from bot.research.types import PortfolioSelection
        ps = PortfolioSelection(
            experiment_run_id="exp-001", selected=[], total_candidates=100,
            stage3_survivors=25, stage4_selected=12, composite_utility=3.1,
            selection_rationale="Top 12 by marginal utility",
        )
        assert ps.stage4_selected == 12
