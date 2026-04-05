"""Tests for experiment tracker (SQLite persistence)."""
import os
import tempfile
import pytest
from bot.research.tracker import ExperimentTracker
from bot.research.types import PassportCandidate, EvalResult, ExperimentResult


@pytest.fixture
def tracker():
    """Create tracker with temp database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    t = ExperimentTracker(db_path=path)
    yield t
    t.close()
    os.unlink(path)


class TestExperimentTracker:
    def test_start_experiment(self, tracker):
        run_id = tracker.start_experiment(total_generated=400)
        assert run_id.startswith("exp-")

    def test_log_passport(self, tracker):
        run_id = tracker.start_experiment(total_generated=1)
        pc = PassportCandidate(
            passport_id="psp_test_001", slug="test-slug",
            family="ema_crossover", config_overrides={"CONFIDENCE_THRESHOLD": 60},
        )
        tracker.log_passport(run_id, pc)
        passports = tracker.get_passports(run_id)
        assert len(passports) == 1
        assert passports[0]["passport_id"] == "psp_test_001"

    def test_log_eval_result(self, tracker):
        run_id = tracker.start_experiment(total_generated=1)
        er = EvalResult(
            passport_id="psp_test_001", stage=1, passed=True,
            metrics={"trades": 50, "return_pct": 10.0},
        )
        tracker.log_eval(run_id, er)
        evals = tracker.get_evals(run_id, stage=1)
        assert len(evals) == 1
        assert evals[0]["passed"] is True

    def test_get_survivors(self, tracker):
        run_id = tracker.start_experiment(total_generated=3)
        for i, passed in enumerate([True, False, True]):
            er = EvalResult(
                passport_id=f"psp_{i}", stage=1, passed=passed,
                metrics={},
                reject_reason=None if passed else "failed",
            )
            tracker.log_eval(run_id, er)
        survivors = tracker.get_survivors(run_id, stage=1)
        assert len(survivors) == 2

    def test_finish_experiment(self, tracker):
        run_id = tracker.start_experiment(total_generated=10)
        result = tracker.finish_experiment(
            run_id, stage1_survivors=5, stage2_survivors=2,
        )
        assert isinstance(result, ExperimentResult)
        assert result.stage1_survivors == 5
        assert result.stage2_survivors == 2
