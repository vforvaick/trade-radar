"""Tests for Stage 4 orthogonality + portfolio construction."""
import numpy as np
import pandas as pd
import pytest


def test_equity_correlation():
    from bot.research.stage4 import calc_equity_correlation
    rng = np.random.RandomState(42)
    a = pd.Series(np.cumsum(rng.normal(0, 1, 100)))
    b = pd.Series(np.cumsum(rng.normal(0, 1, 100)))
    assert -1 <= calc_equity_correlation(a, b) <= 1


def test_trade_overlap_zero():
    from bot.research.stage4 import calc_trade_overlap
    a = [{"symbol": "BTC", "direction": "LONG", "entry_bar": 0, "exit_bar": 10}]
    b = [{"symbol": "ETH", "direction": "LONG", "entry_bar": 0, "exit_bar": 10}]
    assert calc_trade_overlap(a, b) == 0.0


def test_trade_overlap_full():
    from bot.research.stage4 import calc_trade_overlap
    t = [{"symbol": "BTC", "direction": "LONG", "entry_bar": 0, "exit_bar": 10}]
    assert calc_trade_overlap(t, t) == 1.0


def test_dd_coincidence():
    from bot.research.stage4 import calc_dd_coincidence
    dd_a = pd.Series([0, -5, -15, -12, -8, 0, 0, 0, 0, 0])
    dd_b = pd.Series([0, -3, -12, -14, -6, 0, 0, 0, 0, 0])
    assert calc_dd_coincidence(dd_a, dd_b, threshold=10, window=5) > 0


def test_composite_utility():
    from bot.research.stage4 import calc_composite_utility
    u = calc_composite_utility(sharpe=1.5, calmar=0.8, max_dd=20.0)
    expected = (1.5 + 0.8) / (20.0 / 30.0)
    assert abs(u - expected) < 0.01


def test_select_portfolio():
    from bot.research.stage4 import Stage4Evaluator
    rng = np.random.RandomState(42)
    cands = []
    for i in range(5):
        cands.append({
            "passport_id": f"psp_{i}",
            "family": f"fam_{i % 3}",
            "sharpe": 0.8 + i * 0.1,
            "calmar": 0.5 + i * 0.05,
            "max_dd": 15.0 + i,
            "equity_curve": list(np.cumsum(rng.normal(0.1, 1, 60))),
            "trades": [{"symbol": f"S{i}", "direction": "LONG",
                        "entry_bar": i * 10, "exit_bar": i * 10 + 5}],
            "dd_series": list(rng.uniform(-20, 0, 60)),
        })
    result = Stage4Evaluator(family_cap=3, cluster_cap=3).select_portfolio(cands)
    assert 0 < len(result.selected_passport_ids) <= 20
