"""Tests for PortfolioRiskManager."""
import pytest


def make_intent(passport_id="psp_a", symbol="BTCUSDT", direction="LONG",
                size=0.02, entry=30000.0, family="ema"):
    from bot.execution.types import OrderIntent
    return OrderIntent(passport_id=passport_id, symbol=symbol,
        direction=direction, signal_confidence=70, size_hint=size,
        stop_loss=entry*0.98, take_profit=entry*1.04,
        entry_price=entry, cooldown_key=f"{passport_id}:{symbol}",
        metadata={"family": family})


def test_approve_within_limits():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000)
    result = prm.evaluate(make_intent())
    assert result["action"] == "approve"


def test_reject_exposure_cap():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.01, account_equity=10000)
    prm.record_position("psp_existing", "rsi", 0.01)  # Already at cap
    result = prm.evaluate(make_intent(size=0.5))
    assert result["action"] == "reject"
    assert "exposure" in result["reason"].lower()


def test_reject_family_cap():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=100000, family_cap=2)
    prm.record_position("psp_1", "ema", 0.02)
    prm.record_position("psp_2", "ema", 0.02)
    result = prm.evaluate(make_intent(passport_id="psp_3", family="ema"))
    assert result["action"] == "reject"
    assert "family" in result["reason"].lower()


def test_dd_circuit_breaker():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000,
                                dd_circuit_breaker=0.15)
    prm.update_drawdown("psp_a", 0.18)
    result = prm.evaluate(make_intent())
    assert result["action"] == "reject"
    assert "drawdown" in result["reason"].lower()


def test_resize_action():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.05, account_equity=10000)
    prm.record_position("psp_other", "rsi", 0.03)
    result = prm.evaluate(make_intent(size=0.03))
    assert result["action"] in ("resize", "reject")


def test_emergency_pause():
    from bot.risk.portfolio_risk import PortfolioRiskManager
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000)
    prm.emergency_pause()
    result = prm.evaluate(make_intent())
    assert result["action"] == "reject"
    assert "emergency" in result["reason"].lower()
