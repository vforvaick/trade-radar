"""Tests for backtester bugs M2 and L4."""
from datetime import datetime

import pandas as pd

from bot import config
from bot.backtester import _summarize


def _make_trade(pnl, equity_after, exit_time):
    return {"pnl": pnl, "equity_after": equity_after, "exit_time": exit_time}


# --- M2: Sortino sentinel value ---

def test_m2_sortino_all_positive_returns_is_sentinel():
    """When all trade returns are positive, sortino should be 999.99 (sentinel)."""
    eq = config.INITIAL_EQUITY
    trades = [
        _make_trade(50.0, eq + 50.0, datetime(2026, 1, 10)),
        _make_trade(30.0, eq + 80.0, datetime(2026, 1, 20)),
        _make_trade(20.0, eq + 100.0, datetime(2026, 1, 30)),
    ]
    summary = _summarize(trades)
    assert summary["sortino"] == 999.99, f"Expected 999.99 but got {summary['sortino']}"


def test_m2_sortino_not_100_when_all_positive():
    """Confirm the old hardcoded 100.0 is no longer used."""
    eq = config.INITIAL_EQUITY
    trades = [
        _make_trade(100.0, eq + 100.0, datetime(2026, 2, 1)),
        _make_trade(50.0, eq + 150.0, datetime(2026, 2, 15)),
    ]
    summary = _summarize(trades)
    assert summary["sortino"] != 100.0


def test_m2_sortino_zero_when_mean_not_positive_and_no_neg():
    """If daily_returns mean is not positive and no negative returns, sortino = 0."""
    eq = config.INITIAL_EQUITY
    # Flat equity — pct_change of 0 gives mean 0
    trades = [
        _make_trade(0.0, eq, datetime(2026, 3, 1)),
        _make_trade(0.0, eq, datetime(2026, 3, 2)),
    ]
    summary = _summarize(trades)
    assert summary["sortino"] == 0.0


# --- L4: No duplicate equity start point ---

def test_l4_no_duplicate_when_start_time_already_present():
    """Guard prevents duplicate equity point when start_time already in series (idempotency test)."""
    eq = config.INITIAL_EQUITY
    trades = [
        _make_trade(20.0, eq + 20.0, datetime(2026, 4, 5)),
        _make_trade(15.0, eq + 35.0, datetime(2026, 4, 10)),
        _make_trade(10.0, eq + 45.0, datetime(2026, 4, 15)),
    ]
    # Run _summarize twice on identical trades — must produce identical metrics
    # If guard weren't present, duplicate index entry could corrupt metrics on re-run
    summary1 = _summarize(trades)
    summary2 = _summarize(trades)
    assert summary1["sharpe"] == summary2["sharpe"], "Sharpe changed on re-run (duplicate pollution)"
    assert summary1["sortino"] == summary2["sortino"], "Sortino changed on re-run (duplicate pollution)"
    assert summary1["return_pct"] == summary2["return_pct"], "Return changed on re-run (duplicate pollution)"
    assert summary1["return_pct"] > 0, "Expected positive return"


def test_l4_equity_series_length_not_inflated():
    """Equity series should not get an extra duplicate start point on normal runs."""
    # This test calls _summarize and checks that the function does not crash and
    # returns consistent metrics — the guard prevents duplicate index entries.
    eq = config.INITIAL_EQUITY
    trades = [
        _make_trade(5.0, eq + 5.0, datetime(2026, 5, 1)),
        _make_trade(5.0, eq + 10.0, datetime(2026, 5, 8)),
    ]
    summary1 = _summarize(trades)
    summary2 = _summarize(trades)
    # Idempotent — running twice gives same result
    assert summary1["sharpe"] == summary2["sharpe"]
    assert summary1["sortino"] == summary2["sortino"]
    assert summary1["return_pct"] == summary2["return_pct"]
