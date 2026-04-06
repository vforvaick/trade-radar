from datetime import datetime

from bot import config
from bot.backtester import _summarize


def test_summarize_uses_last_trade_equity_as_final_equity():
    trades = [
        {
            "pnl": 10.0,
            "equity_after": config.INITIAL_EQUITY + 10.0,
            "exit_time": datetime(2026, 4, 1, 0, 0, 0),
        },
        {
            "pnl": -5.0,
            "equity_after": config.INITIAL_EQUITY + 5.0,
            "exit_time": datetime(2026, 4, 2, 0, 0, 0),
        },
    ]

    summary = _summarize(trades)

    assert summary["final_equity"] == config.INITIAL_EQUITY + 5.0
    assert round(summary["return_pct"], 2) == 1.0


def test_summarize_handles_flat_returns_without_nan_metrics():
    trades = [
        {
            "pnl": 0.0,
            "equity_after": config.INITIAL_EQUITY,
            "exit_time": datetime(2026, 4, 1, 0, 0, 0),
        }
    ]

    summary = _summarize(trades)

    assert summary["final_equity"] == config.INITIAL_EQUITY
    assert summary["sharpe"] == 0.0
    assert summary["sortino"] == 0.0
    assert summary["calmar"] == 100.0
