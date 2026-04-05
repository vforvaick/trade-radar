"""Tests for Stage 3 parameter perturbation evaluator."""
import pytest
import numpy as np


def test_perturb_int_param():
    from bot.research.stage3 import _perturb_value
    val = _perturb_value(100, "int", magnitude=0.15, rng=np.random.RandomState(42))
    assert isinstance(val, int) and 85 <= val <= 115


def test_perturb_float_param():
    from bot.research.stage3 import _perturb_value
    val = _perturb_value(1.0, "float", magnitude=0.15, rng=np.random.RandomState(42))
    assert isinstance(val, float) and 0.85 <= val <= 1.15


def test_perturb_bool_param():
    from bot.research.stage3 import _perturb_value
    val = _perturb_value(True, "bool", magnitude=0.15, rng=np.random.RandomState(42))
    assert isinstance(val, bool)


def test_stage3_pass():
    from bot.research.stage3 import Stage3Evaluator
    ev = Stage3Evaluator(mc_iterations=10)
    sums = [
        {"return_pct": 10.0, "max_dd": 15.0, "sharpe": 0.8, "profit_factor": 1.5, "trades": 30}
        for _ in range(10)
    ]
    r = ev.evaluate_from_summaries("psp_test", 12.0, sums)
    assert r.passed is True and r.survival_rate >= 0.6


def test_stage3_fail_low_survival():
    from bot.research.stage3 import Stage3Evaluator
    ev = Stage3Evaluator(mc_iterations=10)
    bad = [
        {"return_pct": -20.0, "max_dd": 40.0, "sharpe": -0.5, "profit_factor": 0.5, "trades": 30}
        for _ in range(8)
    ]
    good = [
        {"return_pct": 5.0, "max_dd": 10.0, "sharpe": 0.5, "profit_factor": 1.2, "trades": 30}
        for _ in range(2)
    ]
    r = ev.evaluate_from_summaries("psp_test", 12.0, bad + good)
    assert r.passed is False and r.survival_rate < 0.6


def test_stage3_fail_cliff():
    from bot.research.stage3 import Stage3Evaluator
    ev = Stage3Evaluator(mc_iterations=10)
    sums = [
        {"return_pct": 1.0, "max_dd": 10.0, "sharpe": 0.3, "profit_factor": 1.1, "trades": 30}
        for _ in range(10)
    ]
    r = ev.evaluate_from_summaries("psp_test", 20.0, sums)
    assert r.passed is False and "cliff" in (r.reject_reason or "").lower()
