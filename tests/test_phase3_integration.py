"""Phase 3 integration verification tests.

Confirms that Phase 1 calculation fixes work correctly end-to-end through
the research pipeline's Stage 3 (Monte Carlo) and Stage 4 (portfolio construction).
"""
import numpy as np
import pytest

from bot.research.stage3 import perturb_config
from bot.research.stage4 import calc_composite_utility, calc_trade_overlap


class TestPerturbConfig:
    """Stage 3: perturb_config respects zero-weight semantics."""

    BASE_CONFIG = {
        "INDICATOR_WEIGHTS": {
            "ema_trend": 1.0,
            "macd_signal": 0.0,
            "rsi_position": 0.0,
            "rsi_divergence": 0.0,
            "bb_position": 1.5,
            "volume_spike": 2.0,
            "pressure": 0.0,
            "candle_direction": 0.0,
        },
        "MIN_CONFIDENCE": 60.0,
    }

    def test_zero_weights_never_perturbed(self):
        """Zero INDICATOR_WEIGHTS must stay exactly 0.0 after perturbation."""
        zero_keys = [k for k, v in self.BASE_CONFIG["INDICATOR_WEIGHTS"].items() if v == 0.0]
        assert zero_keys, "test requires some zero weights"

        rng = np.random.RandomState(42)
        for _ in range(20):
            result = perturb_config(self.BASE_CONFIG, rng=rng)
            for key in zero_keys:
                assert result["INDICATOR_WEIGHTS"][key] == 0.0, (
                    f"Zero weight '{key}' was perturbed to "
                    f"{result['INDICATOR_WEIGHTS'][key]}"
                )

    def test_nonzero_weights_actually_change(self):
        """Non-zero INDICATOR_WEIGHTS must vary across multiple perturbations."""
        nonzero_keys = [k for k, v in self.BASE_CONFIG["INDICATOR_WEIGHTS"].items() if v != 0.0]
        assert nonzero_keys, "test requires some non-zero weights"

        seen_values: dict[str, set] = {k: set() for k in nonzero_keys}

        for seed in range(50):
            rng = np.random.RandomState(seed)
            result = perturb_config(self.BASE_CONFIG, rng=rng)
            for key in nonzero_keys:
                seen_values[key].add(round(result["INDICATOR_WEIGHTS"][key], 6))

        for key in nonzero_keys:
            assert len(seen_values[key]) > 1, (
                f"Non-zero weight '{key}' never changed across 50 perturbations"
            )


class TestCalcTradeOverlap:
    """Stage 4: calc_trade_overlap correctly detects time-window overlap."""

    def test_overlapping_trades_return_nonzero(self):
        """Overlapping same-symbol, same-direction trades must score > 0."""
        trades_a = [
            {
                "symbol": "BTCUSDT",
                "direction": "long",
                "entry_time": "2024-01-01 10:00:00",
                "exit_time": "2024-01-01 14:00:00",
            }
        ]
        trades_b = [
            {
                "symbol": "BTCUSDT",
                "direction": "long",
                "entry_time": "2024-01-01 12:00:00",
                "exit_time": "2024-01-01 16:00:00",
            }
        ]

        overlap = calc_trade_overlap(trades_a, trades_b)
        assert overlap > 0, f"Expected overlap > 0, got {overlap}"

    def test_non_overlapping_trades_return_zero(self):
        """Non-overlapping trades must return 0."""
        trades_a = [
            {
                "symbol": "BTCUSDT",
                "direction": "long",
                "entry_time": "2024-01-01 08:00:00",
                "exit_time": "2024-01-01 10:00:00",
            }
        ]
        trades_b = [
            {
                "symbol": "BTCUSDT",
                "direction": "long",
                "entry_time": "2024-01-01 12:00:00",
                "exit_time": "2024-01-01 14:00:00",
            }
        ]

        overlap = calc_trade_overlap(trades_a, trades_b)
        assert overlap == 0.0, f"Expected 0.0, got {overlap}"

    def test_different_symbol_no_overlap(self):
        """Trades on different symbols must not count as overlap."""
        trades_a = [
            {
                "symbol": "BTCUSDT",
                "direction": "long",
                "entry_time": "2024-01-01 10:00:00",
                "exit_time": "2024-01-01 14:00:00",
            }
        ]
        trades_b = [
            {
                "symbol": "ETHUSDT",
                "direction": "long",
                "entry_time": "2024-01-01 11:00:00",
                "exit_time": "2024-01-01 13:00:00",
            }
        ]

        overlap = calc_trade_overlap(trades_a, trades_b)
        assert overlap == 0.0, f"Different symbols should not overlap, got {overlap}"


class TestCalcCompositeUtility:
    """Stage 4: calc_composite_utility handles max_dd=0 correctly (Phase 1 fix)."""

    def test_zero_max_dd_returns_high_value(self):
        """When max_dd=0 the function must return > 50 (not division-by-zero / 0)."""
        result = calc_composite_utility(sharpe=1.5, calmar=2.0, max_dd=0.0)
        assert result > 50, (
            f"calc_composite_utility with max_dd=0 returned {result}, expected > 50"
        )

    def test_zero_max_dd_formula(self):
        """max_dd=0 branch: result == (sharpe + calmar) * 10 + 100."""
        sharpe, calmar = 1.5, 2.0
        expected = (sharpe + calmar) * 10.0 + 100.0
        result = calc_composite_utility(sharpe=sharpe, calmar=calmar, max_dd=0.0)
        assert result == pytest.approx(expected), (
            f"Expected {expected}, got {result}"
        )

    def test_normal_max_dd_uses_ratio(self):
        """With normal max_dd the result is (sharpe + calmar) / (max_dd / 30)."""
        sharpe, calmar, max_dd = 1.0, 1.0, 30.0
        expected = (sharpe + calmar) / (max_dd / 30.0)  # = 2.0
        result = calc_composite_utility(sharpe=sharpe, calmar=calmar, max_dd=max_dd)
        assert result == pytest.approx(expected)
