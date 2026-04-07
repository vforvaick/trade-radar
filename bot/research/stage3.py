"""Stage 3 evaluator — Monte Carlo parameter perturbation.

Tests robustness by perturbing strategy parameters ±15% and checking
survival rate across multiple backtests.
"""
from __future__ import annotations

import numpy as np

from bot.research.types import Stage3Result


def _perturb_value(
    value, param_type: str, magnitude: float = 0.15,
    rng: np.random.RandomState | None = None, bounds: tuple | None = None,
) -> int | float | bool:
    """Perturb a single parameter value."""
    if rng is None:
        rng = np.random.RandomState()

    if param_type == "bool":
        return not value if rng.random() < magnitude else value

    factor = 1.0 + rng.uniform(-magnitude, magnitude)

    if param_type == "int":
        result = int(round(value * factor))
        if bounds:
            result = max(bounds[0], min(bounds[1], result))
        return result

    if param_type == "float":
        result = value * factor
        if bounds:
            result = max(bounds[0], min(bounds[1], result))
        return result

    return value


def perturb_config(
    config_overrides: dict, param_types: dict | None = None,
    magnitude: float = 0.15, rng: np.random.RandomState | None = None,
) -> dict:
    """Perturb all numeric parameters in a config dict.

    Args:
        config_overrides: original config dict
        param_types: name → "int"|"float"|"bool" (auto-detected if None)
        magnitude: perturbation range (0.15 = ±15%)
        rng: random state for reproducibility
    """
    if rng is None:
        rng = np.random.RandomState()

    weights_magnitude = 0.20

    result = {}
    for key, value in config_overrides.items():
        if key == "INDICATOR_WEIGHTS":
            perturbed_weights = {}
            for w_name, w_val in value.items():
                if w_val == 0.0:
                    perturbed_weights[w_name] = 0.0  # zero = disabled, never perturb
                else:
                    factor = 1.0 + rng.uniform(-weights_magnitude, weights_magnitude)
                    perturbed_weights[w_name] = max(0.01, w_val * factor)
            result[key] = perturbed_weights
            continue

        if param_types and key in param_types:
            ptype = param_types[key]
        elif isinstance(value, bool):
            ptype = "bool"
        elif isinstance(value, int):
            ptype = "int"
        elif isinstance(value, float):
            ptype = "float"
        else:
            result[key] = value
            continue

        result[key] = _perturb_value(value, ptype, magnitude, rng)

    return result


class Stage3Evaluator:
    """Evaluates parameter robustness via Monte Carlo perturbation."""

    def __init__(
        self,
        mc_iterations: int = 50,
        perturbation_pct: float = 0.15,
        survival_threshold: float = 0.60,
        cliff_threshold: float = 0.50,
        p5_floor: float = -30.0,
    ):
        self.mc_iterations = mc_iterations
        self.perturbation_pct = perturbation_pct
        self.survival_threshold = survival_threshold
        self.cliff_threshold = cliff_threshold
        self.p5_floor = p5_floor

    def _is_surviving(self, summary: dict) -> bool:
        """Check if a perturbed run meets minimum viability."""
        ret = summary.get("return_pct", -100)
        dd = summary.get("max_dd", 100)
        sharpe = summary.get("sharpe", -1)
        pf = summary.get("profit_factor", 0)
        return ret > 0 and dd < 50 and (sharpe > 0.1 or pf > 1.05)

    def evaluate_from_summaries(
        self,
        passport_id: str,
        original_return: float,
        perturbed_summaries: list[dict],
    ) -> Stage3Result:
        """Evaluate from pre-computed perturbed backtest summaries.

        Args:
            passport_id: passport being evaluated
            original_return: return_pct from original (unperturbed) backtest
            perturbed_summaries: list of backtest summary dicts from perturbed configs
        """
        n = len(perturbed_summaries)
        if n == 0:
            return Stage3Result(
                passport_id=passport_id, survival_rate=0.0,
                mean_perturbed_return=0.0, original_return=original_return,
                p5_return=0.0, p95_return=0.0, iqr_return=0.0,
                passed=False, reject_reason="No perturbation data",
                mc_iterations=0,
            )

        surviving = sum(1 for s in perturbed_summaries if self._is_surviving(s))
        survival_rate = surviving / n

        returns = [s.get("return_pct", -100) for s in perturbed_summaries]
        returns_arr = np.array(returns)
        mean_return = float(np.mean(returns_arr))
        p5 = float(np.percentile(returns_arr, 5))
        p95 = float(np.percentile(returns_arr, 95))
        q25, q75 = np.percentile(returns_arr, [25, 75])
        iqr = float(q75 - q25)

        reject_reasons = []

        if survival_rate < self.survival_threshold:
            reject_reasons.append(
                f"Low survival: {survival_rate:.0%} < {self.survival_threshold:.0%}"
            )

        # Cliff detection: mean perturbed return drops > cliff_threshold of original
        if original_return > 0 and mean_return < original_return * (1 - self.cliff_threshold):
            reject_reasons.append(
                f"Cliff: mean perturbed {mean_return:.1f}% vs original {original_return:.1f}%"
            )

        if p5 < self.p5_floor:
            reject_reasons.append(f"p5 too low: {p5:.1f}% < {self.p5_floor:.1f}%")

        passed = len(reject_reasons) == 0
        reject_reason = "; ".join(reject_reasons) if reject_reasons else None

        return Stage3Result(
            passport_id=passport_id,
            survival_rate=survival_rate,
            mean_perturbed_return=mean_return,
            original_return=original_return,
            p5_return=p5,
            p95_return=p95,
            iqr_return=iqr,
            passed=passed,
            reject_reason=reject_reason,
            mc_iterations=n,
            perturbation_details=[],
        )
