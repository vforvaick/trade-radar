"""Tests for scoring family definitions."""
import pytest
from bot.research.families import SCORING_FAMILIES, get_family, get_param_grid


class TestScoringFamilies:
    def test_has_at_least_10_families(self):
        assert len(SCORING_FAMILIES) >= 10

    def test_each_family_has_required_fields(self):
        required = {"name", "weights", "param_ranges", "compatible_regimes", "min_trades"}
        for name, family in SCORING_FAMILIES.items():
            missing = required - set(family.keys())
            assert not missing, f"Family '{name}' missing fields: {missing}"

    def test_weights_use_valid_indicator_names(self):
        valid_indicators = {
            "ema_trend", "macd_signal", "rsi_position", "rsi_divergence",
            "bb_position", "volume_spike", "pressure", "candle_direction",
            "stochrsi", "obv_trend", "ichimoku", "vwap_deviation",
            "keltner", "donchian", "heikin_ashi", "williams_r",
            "cci", "mfi", "hull_ma", "supertrend", "pivot_points",
        }
        for name, family in SCORING_FAMILIES.items():
            for ind in family["weights"]:
                assert ind in valid_indicators, f"Family '{name}' has invalid indicator '{ind}'"

    def test_ema_crossover_family(self):
        f = get_family("ema_crossover")
        assert f is not None
        assert f["weights"]["ema_trend"] >= 2.0
        assert f["weights"].get("rsi_position", 0) <= 1.0

    def test_get_family_returns_none_for_unknown(self):
        assert get_family("nonexistent") is None


class TestParamGrid:
    def test_get_param_grid_returns_list_of_overrides(self):
        grid = get_param_grid("ema_crossover")
        assert len(grid) > 0
        for item in grid:
            assert "INDICATOR_WEIGHTS" in item
            assert "CONFIDENCE_THRESHOLD" in item

    def test_grid_respects_bounds(self):
        grid = get_param_grid("ema_crossover")
        for item in grid:
            assert 50 <= item["CONFIDENCE_THRESHOLD"] <= 75

    def test_grid_returns_empty_for_unknown_family(self):
        grid = get_param_grid("nonexistent")
        assert grid == []


class TestExtendedFamilies:
    def test_families_6_through_18_exist(self):
        expected = [
            "stochastic_reversal", "obv_trend", "ichimoku_cloud",
            "vwap_deviation", "keltner_breakout", "donchian_breakout",
            "heikin_ashi_momentum", "williams_reversal", "cci_divergence",
            "mfi_flow", "hull_ma_crossover", "supertrend_follow", "pivot_bounce",
        ]
        for name in expected:
            assert name in SCORING_FAMILIES, f"Missing: {name}"

    def test_total_family_count_at_least_25(self):
        assert len(SCORING_FAMILIES) >= 25
