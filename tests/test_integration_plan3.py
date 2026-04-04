"""Integration test — verifies all Plan 3 modules work together."""
import os
import tempfile
from datetime import datetime


def test_full_signal_to_trade_pipeline():
    """End-to-end: signal → PositionManager → PortfolioRisk → Fill → StateDB."""
    from bot.execution.types import OrderIntent, Fill, PositionRecord
    from bot.execution.position_manager import PositionManager
    from bot.risk.portfolio_risk import PortfolioRiskManager
    from bot.deploy.state_db import StateDB

    pm = PositionManager(default_size=0.05, cooldown_minutes=0, min_confidence=50)
    prm = PortfolioRiskManager(max_gross_exposure=0.6, account_equity=10000)

    signal = {"direction": "LONG", "confidence": 75, "entry_price": 30000,
              "stop_loss": 29500, "take_profit": 31000, "metadata": {"family": "ema"}}

    intent = pm.signal_to_intent("psp_og_v01", "BTCUSDT", signal)
    assert intent is not None

    risk_eval = prm.evaluate(intent)
    assert risk_eval["action"] == "approve"

    fill = Fill(order_intent_id=intent.id, fill_price=30010.0,
                fill_size=risk_eval["adjusted_size"], slippage_bps=0.33,
                fee_bps=4.0, timestamp=datetime.now(), is_paper=True)

    pm.record_fill(intent)
    prm.record_position("psp_og_v01", "ema", fill.fill_size)

    with tempfile.TemporaryDirectory() as d:
        db = StateDB(os.path.join(d, "state.db"))
        db.upsert_passport("psp_og_v01", "paper_live", version="v0.1", family="ema")
        db.log_trade("psp_og_v01", "BTCUSDT", "LONG", entry_price=30010.0)
        trades = db.get_trades(passport_id="psp_og_v01")
        assert len(trades) == 1
        db.close()


def test_health_promotion_telegram_integration():
    """Health check → Promotion evaluation → Telegram formatting."""
    from bot.health.monitor import HealthMonitor
    from bot.health.promotion import PromotionPolicy
    from bot.telegram_commands import format_health, format_promotion_check

    hm = HealthMonitor()
    hm.record_data_update()
    hm.record_api_call(150)
    health = hm.full_check()
    assert health["healthy"] is True

    msg = format_health(health)
    assert "✅" in msg

    pp = PromotionPolicy()
    metrics = {"passport_id": "psp_og_v01", "paper_days": 21,
               "paper_trades": 45, "sharpe": 1.2, "max_dd": 0.12,
               "win_rate": 0.55, "profit_factor": 1.8,
               "portfolio_correlation": 0.15}
    result = pp.evaluate(metrics)
    assert result["passed"] is True

    promo_msg = format_promotion_check(result)
    assert "🎉" in promo_msg


def test_scheduler_with_risk():
    """Scheduler runs strategies and results pass through risk manager."""
    from bot.scheduler.orchestrator import Orchestrator, RateLimiter
    from bot.risk.portfolio_risk import PortfolioRiskManager

    rl = RateLimiter(max_calls=100, window_seconds=60)
    orch = Orchestrator(rl)
    orch.add_task("psp_a", "BTCUSDT")
    orch.add_task("psp_b", "ETHUSDT")

    def mock_strategy(**kwargs):
        return {"direction": "LONG", "confidence": 70}

    results = orch.run_all(mock_strategy)
    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)


def test_namespace_isolation_with_statedb():
    """Paper and prod namespaces stay separate in StateDB."""
    from bot.risk.namespace import NamespaceManager
    from bot.deploy.state_db import StateDB
    import tempfile, os

    with tempfile.TemporaryDirectory() as d:
        paper_ns = NamespaceManager(d, "paper")
        prod_ns = NamespaceManager(d, "prod")

        paper_ns.write_position({"id": "pos1", "symbol": "BTC"})
        assert len(paper_ns.read_positions()) == 1
        assert len(prod_ns.read_positions()) == 0

        db = StateDB(os.path.join(d, "state.db"))
        db.log_trade("psp_a", "BTC", "LONG", 30000, namespace="paper")
        db.log_trade("psp_b", "ETH", "LONG", 2000, namespace="prod")
        assert len(db.get_trades(namespace="paper")) == 1
        assert len(db.get_trades(namespace="prod")) == 1
        db.close()
