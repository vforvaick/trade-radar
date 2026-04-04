"""Tests for PromotionPolicy."""
import pytest


def make_good_metrics(**overrides):
    m = {
        "passport_id": "psp_og_v01",
        "paper_days": 21, "paper_trades": 45,
        "sharpe": 1.2, "max_dd": 0.12, "win_rate": 0.55,
        "profit_factor": 1.8, "portfolio_correlation": 0.15,
    }
    m.update(overrides)
    return m


def test_all_gates_pass():
    from bot.health.promotion import PromotionPolicy
    pp = PromotionPolicy()
    result = pp.evaluate(make_good_metrics())
    assert result["passed"] is True
    assert all(g["passed"] for g in result["gates"].values())


def test_sharpe_gate_fails():
    from bot.health.promotion import PromotionPolicy
    pp = PromotionPolicy(min_sharpe=0.5)
    result = pp.evaluate(make_good_metrics(sharpe=0.2))
    assert result["passed"] is False
    assert result["gates"]["sharpe"]["passed"] is False


def test_dd_gate_fails():
    from bot.health.promotion import PromotionPolicy
    pp = PromotionPolicy(max_dd=0.15)
    result = pp.evaluate(make_good_metrics(max_dd=0.30))
    assert result["passed"] is False
    assert result["gates"]["max_drawdown"]["passed"] is False


def test_insufficient_paper_days():
    from bot.health.promotion import PromotionPolicy
    pp = PromotionPolicy(min_paper_days=30)
    result = pp.evaluate(make_good_metrics(paper_days=10))
    assert result["passed"] is False


def test_all_seven_gates_present():
    from bot.health.promotion import PromotionPolicy
    pp = PromotionPolicy()
    result = pp.evaluate(make_good_metrics())
    assert len(result["gates"]) == 7
