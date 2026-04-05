"""Evaluation pipeline — Stage 1 (viability) and Stage 2 (regime walk-forward).

Stage 1 is a sanity gate: kill obviously broken candidates cheaply.
Stage 2 is OOS validation: regime-aware walk-forward.
"""
from __future__ import annotations

import statistics
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


class Stage2Evaluator:
    """Stage 2: Regime-Split Walk-Forward Validation.

    Checks:
    - At least 2/3 folds OOS positive (or 1/1 for single fold)
    - Median OOS return > 0
    - No single fold DD > 40%
    - Aggregate Sharpe > 0.3 OR Calmar > 0.5 OR PF > 1.1
    """

    def __init__(
        self,
        min_positive_folds_ratio: float = 0.67,
        max_fold_dd: float = 40.0,
        min_sharpe: float = 0.3,
        min_calmar: float = 0.5,
        min_profit_factor: float = 1.1,
    ):
        self.min_positive_folds_ratio = min_positive_folds_ratio
        self.max_fold_dd = max_fold_dd
        self.min_sharpe = min_sharpe
        self.min_calmar = min_calmar
        self.min_profit_factor = min_profit_factor

    def evaluate(
        self,
        passport_id: str,
        fold_results: list[dict],
    ) -> EvalResult:
        """Evaluate OOS walk-forward fold results."""
        failures: list[str] = []
        n_folds = len(fold_results)
        if n_folds == 0:
            return EvalResult(
                passport_id=passport_id, stage=2, passed=False,
                reject_reason="No fold results provided",
            )

        returns = [f["return_pct"] for f in fold_results]
        positive_count = sum(1 for r in returns if r > 0)
        positive_ratio = positive_count / n_folds

        # Check: enough positive folds (2 out of 3 = pass)
        required_positive = max(1, int(n_folds * self.min_positive_folds_ratio))
        if n_folds >= 3 and positive_count < required_positive:
            failures.append(
                f"Insufficient positive folds: {positive_count}/{n_folds} "
                f"({positive_ratio:.0%} < {self.min_positive_folds_ratio:.0%})"
            )
        elif n_folds < 3 and positive_count == 0:
            failures.append("Single fold is not positive")

        median_return = statistics.median(returns)
        if median_return <= 0 and n_folds >= 3:
            failures.append(f"Median OOS return <= 0: {median_return:.2f}%")

        for i, fold in enumerate(fold_results):
            dd = fold.get("max_dd", 0)
            if dd > self.max_fold_dd:
                failures.append(
                    f"Fold {i+1} drawdown catastrophic: {dd:.1f}% > {self.max_fold_dd}%"
                )
                break

        avg_sharpe = statistics.mean(f.get("sharpe", 0) for f in fold_results)
        avg_calmar = statistics.mean(f.get("calmar", 0) for f in fold_results)
        avg_pf = statistics.mean(f.get("profit_factor", 0) for f in fold_results)

        metrics_pass = (
            avg_sharpe >= self.min_sharpe
            or avg_calmar >= self.min_calmar
            or avg_pf >= self.min_profit_factor
        )
        if not metrics_pass:
            failures.append(
                f"No quality metric passes: Sharpe={avg_sharpe:.2f}, "
                f"Calmar={avg_calmar:.2f}, PF={avg_pf:.2f}"
            )

        agg_metrics = {
            "n_folds": n_folds,
            "positive_folds": positive_count,
            "median_return": median_return,
            "avg_sharpe": avg_sharpe,
            "avg_calmar": avg_calmar,
            "avg_profit_factor": avg_pf,
            "fold_returns": returns,
        }

        if not failures:
            return EvalResult(
                passport_id=passport_id, stage=2, passed=True,
                metrics=agg_metrics,
            )

        return EvalResult(
            passport_id=passport_id, stage=2, passed=False,
            metrics=agg_metrics,
            reject_reason=failures[0],
            secondary_reasons=failures[1:],
        )
