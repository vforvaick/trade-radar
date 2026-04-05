"""Tests for Telegram command formatters."""
import pytest


def test_format_strategies_empty():
    from bot.telegram_commands import format_strategies_list
    assert "No active" in format_strategies_list([])


def test_format_strategies_list():
    from bot.telegram_commands import format_strategies_list
    strategies = [
        {"id": "OG_v0.1", "status": "production", "pnl": 5.3},
        {"id": "Momentum_v0.2", "status": "paper_live", "pnl": -2.1},
    ]
    result = format_strategies_list(strategies)
    assert "🟢" in result
    assert "🟡" in result
    assert "+5.30%" in result
    assert "-2.10%" in result


def test_format_compare():
    from bot.telegram_commands import format_compare
    a = {"id": "OG_v0.1", "sharpe": 1.2, "calmar": 0.8, "max_dd": 0.12,
         "total_return": 15.3, "win_rate": 0.55}
    b = {"id": "OG_v0.2", "sharpe": 0.9, "calmar": 0.6, "max_dd": 0.18,
         "total_return": 8.1, "win_rate": 0.48}
    result = format_compare(a, b)
    assert "OG_v0.1" in result and "OG_v0.2" in result
    assert "sharpe" in result


def test_format_health():
    from bot.telegram_commands import format_health
    h = {"healthy": True, "checks": {
        "data_freshness": {"ok": True, "detail": "< 5min"},
        "api_latency": {"ok": True, "detail": "120ms"},
    }}
    result = format_health(h)
    assert "✅" in result


def test_format_daily_digest():
    from bot.telegram_commands import format_daily_digest
    d = {"total_pnl": 3.5, "active": 5, "trades_today": 12, "alerts": ["DD spike"]}
    result = format_daily_digest(d)
    assert "+3.50%" in result
    assert "DD spike" in result
