"""Evaluation pipeline — Stage 1 (viability) and Stage 2 (regime walk-forward).

Stage 1 is a sanity gate: kill obviously broken candidates cheaply.
Stage 2 is OOS validation: regime-aware walk-forward.
"""
from __future__ import annotations

from typing import Optional

from bot.research.types import BacktestMetrics, EvalResult


class Stage1Evaluator:
    """Stage 1: Minimum Viability (Sanity Gate).

    Three sub-groups:
    A. Data sanity (not checked here — handled before backtesting)
    B. Trading sanity (min trades, fee ratio)
    C. Catastrophe screen (max DD, return floor)
    """

    def __init__(
        self,
        max_dd_threshold: float = 50.0,
        return_floor: float = -20.0,
        min_profit_factor: float = 0.85,
    ):
        self.max_dd_threshold = max_dd_threshold
        self.return_floor = return_floor
        self.min_profit_factor = min_profit_factor

    def evaluate(
        self,
        passport_id: str,
        metrics: BacktestMetrics,
        min_trades: int = 30,
    ) -> EvalResult:
        """Run Stage 1 viability checks.

        Returns EvalResult with passed=True/False and rejection reasons.
        """
        failures: list[str] = []

        # B. Trading sanity
        if metrics.trades < min_trades:
            failures.append(
                f"Insufficient trades: {metrics.trades} < {min_trades}"
            )
        if metrics.profit_factor > 0 and metrics.profit_factor < self.min_profit_factor:
            failures.append(
                f"Profit factor too low: {metrics.profit_factor:.2f} < {self.min_profit_factor}"
            )

        # C. Catastrophe screen
        if metrics.max_dd > self.max_dd_threshold:
            failures.append(
                f"Drawdown catastrophic: {metrics.max_dd:.1f}% > {self.max_dd_threshold}%"
            )
        if metrics.return_pct < self.return_floor:
            failures.append(
                f"Return below floor: {metrics.return_pct:.1f}% < {self.return_floor}%"
            )

        if not failures:
            return EvalResult(
                passport_id=passport_id,
                stage=1,
                passed=True,
                metrics=_metrics_to_dict(metrics),
            )

        return EvalResult(
            passport_id=passport_id,
            stage=1,
            passed=False,
            metrics=_metrics_to_dict(metrics),
            reject_reason=failures[0],
            secondary_reasons=failures[1:],
        )


def _metrics_to_dict(m: BacktestMetrics) -> dict:
    """Convert BacktestMetrics to a plain dict for storage."""
    return {
        "trades": m.trades, "win_rate": m.win_rate,
        "return_pct": m.return_pct, "max_dd": m.max_dd,
        "sharpe": m.sharpe, "sortino": m.sortino,
        "calmar": m.calmar, "profit_factor": m.profit_factor,
    }
