"""Research pipeline orchestrator — generate, evaluate, track."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from bot.backtester import run_backtest
from bot.research.types import (
    PassportCandidate, BacktestMetrics, EvalResult, Stage3Result, Stage4Result,
)
from bot.research.generator import generate_passports
from bot.research.evaluator import Stage1Evaluator, Stage2Evaluator
from bot.research.stage3 import Stage3Evaluator, perturb_config
from bot.research.stage4 import Stage4Evaluator
from bot.research.tracker import ExperimentTracker
from bot.research.families import SCORING_FAMILIES

logger = logging.getLogger(__name__)


class ResearchPipeline:
    """Orchestrates the full research pipeline: generate → Stage 1 → Stage 2 → Stage 3 → Stage 4."""

    def __init__(
        self,
        symbols: list[str],
        interval: str = "1h",
        days: int = 180,
        db_path: str = "research_experiments.db",
    ):
        self.symbols = symbols
        self.interval = interval
        self.days = days
        self.tracker = ExperimentTracker(db_path=db_path)
        self.stage1 = Stage1Evaluator()
        self.stage2 = Stage2Evaluator()
        self.stage3 = Stage3Evaluator()
        self.stage4 = Stage4Evaluator()
        self.run_id: Optional[str] = None

    def generate_candidates(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
    ) -> list[PassportCandidate]:
        """Generate passport candidates and start tracking."""
        candidates = generate_passports(families=families, max_per_family=max_per_family)
        self.run_id = self.tracker.start_experiment(total_generated=len(candidates))
        for c in candidates:
            self.tracker.log_passport(self.run_id, c)
        logger.info("Generated %d candidates (run_id=%s)", len(candidates), self.run_id)
        return candidates

    def run_stage1(
        self,
        candidates: list[PassportCandidate],
    ) -> list[PassportCandidate]:
        """Run Stage 1 viability on all candidates via backtesting."""
        survivors = []
        for i, candidate in enumerate(candidates):
            logger.info(
                "[Stage 1] %d/%d — %s", i + 1, len(candidates), candidate.slug,
            )
            try:
                summary = run_backtest(
                    symbols=self.symbols,
                    interval=self.interval,
                    days=self.days,
                    cfg_override=candidate.config_overrides,
                )
                metrics = BacktestMetrics.from_summary(summary)
            except Exception as e:
                logger.warning("Backtest failed for %s: %s", candidate.slug, e)
                result = EvalResult(
                    passport_id=candidate.passport_id, stage=1, passed=False,
                    reject_reason=f"Backtest error: {e}",
                )
                self.tracker.log_eval(self.run_id, result)
                continue

            min_trades = SCORING_FAMILIES.get(
                candidate.family, {}
            ).get("min_trades", 30)
            result = self.stage1.evaluate(
                candidate.passport_id, metrics, min_trades=min_trades,
            )
            self.tracker.log_eval(self.run_id, result)

            if result.passed:
                candidate.status = "stage1_passed"
                survivors.append(candidate)
                logger.info("  PASS — return=%.1f%% dd=%.1f%% sharpe=%.2f",
                            metrics.return_pct, metrics.max_dd, metrics.sharpe)
            else:
                logger.info("  FAIL — %s", result.reject_reason)

        logger.info("Stage 1: %d/%d survived", len(survivors), len(candidates))
        return survivors

    def run_stage2(
        self,
        candidates: list[PassportCandidate],
        train_days: int = 120,
        test_days: int = 60,
    ) -> list[PassportCandidate]:
        """Run Stage 2 walk-forward validation on Stage 1 survivors."""
        survivors = []
        total_days = self.days
        folds = _calc_folds(total_days, train_days, test_days, slide=30)

        for i, candidate in enumerate(candidates):
            logger.info(
                "[Stage 2] %d/%d — %s (%d folds)",
                i + 1, len(candidates), candidate.slug, len(folds),
            )
            fold_results = []
            for fold_idx, (train_end_offset, test_end_offset) in enumerate(folds):
                try:
                    train_summary = run_backtest(
                        symbols=self.symbols,
                        interval=self.interval,
                        days=train_days,
                        cfg_override=candidate.config_overrides,
                        end_offset_days=train_end_offset,
                    )
                    test_summary = run_backtest(
                        symbols=self.symbols,
                        interval=self.interval,
                        days=test_days,
                        cfg_override=candidate.config_overrides,
                        end_offset_days=test_end_offset,
                    )
                    train_ret = train_summary.get("return_pct", 0)
                    test_ret = test_summary.get("return_pct", 0)
                    test_summary["overfit_ratio"] = (
                        test_ret / train_ret if train_ret != 0 else 0.0
                    )
                    fold_results.append(test_summary)
                except Exception as e:
                    logger.warning("Fold %d failed for %s: %s", fold_idx, candidate.slug, e)
                    fold_results.append({
                        "return_pct": -100.0, "max_dd": 100.0,
                        "sharpe": -1.0, "calmar": -1.0, "profit_factor": 0.0,
                        "trades": 0,
                    })

            result = self.stage2.evaluate(candidate.passport_id, fold_results)
            self.tracker.log_eval(self.run_id, result)

            if result.passed:
                candidate.status = "stage2_passed"
                survivors.append(candidate)
                logger.info("  PASS — avg_sharpe=%.2f median_ret=%.1f%%",
                            result.metrics.get("avg_sharpe", 0),
                            result.metrics.get("median_return", 0))
            else:
                logger.info("  FAIL — %s", result.reject_reason)

        logger.info("Stage 2: %d/%d survived", len(survivors), len(candidates))
        return survivors

    def run_stage3(
        self,
        candidates: list[PassportCandidate],
        mc_iterations: int = 50,
    ) -> list[PassportCandidate]:
        """Run Stage 3 Monte Carlo perturbation on Stage 2 survivors."""
        survivors = []
        rng = np.random.RandomState(42)

        for i, candidate in enumerate(candidates):
            logger.info(
                "[Stage 3] %d/%d — %s (%d MC iterations)",
                i + 1, len(candidates), candidate.slug, mc_iterations,
            )

            # Run original backtest for baseline return
            try:
                orig_summary = run_backtest(
                    symbols=self.symbols,
                    interval=self.interval,
                    days=self.days,
                    cfg_override=candidate.config_overrides,
                )
                original_return = orig_summary.get("return_pct", 0.0)
            except Exception as e:
                logger.warning("Original backtest failed for %s: %s", candidate.slug, e)
                continue

            # Run perturbed backtests
            perturbed_summaries = []
            for mc_i in range(mc_iterations):
                perturbed_config = perturb_config(
                    candidate.config_overrides, magnitude=0.15, rng=rng,
                )
                try:
                    summary = run_backtest(
                        symbols=self.symbols,
                        interval=self.interval,
                        days=self.days,
                        cfg_override=perturbed_config,
                    )
                    perturbed_summaries.append(summary)
                except Exception:
                    perturbed_summaries.append({
                        "return_pct": -100.0, "max_dd": 100.0,
                        "sharpe": -1.0, "profit_factor": 0.0, "trades": 0,
                    })

            result = self.stage3.evaluate_from_summaries(
                candidate.passport_id, original_return, perturbed_summaries,
            )

            if result.passed:
                candidate.status = "stage3_passed"
                survivors.append(candidate)
                logger.info("  PASS — survival=%.0f%% mean_ret=%.1f%%",
                            result.survival_rate * 100, result.mean_perturbed_return)
            else:
                logger.info("  FAIL — %s", result.reject_reason)

        logger.info("Stage 3: %d/%d survived", len(survivors), len(candidates))
        return survivors

    def run_stage4(
        self,
        candidates: list[PassportCandidate],
    ) -> Stage4Result:
        """Run Stage 4 portfolio selection on Stage 3 survivors."""
        logger.info("[Stage 4] Building portfolio from %d candidates", len(candidates))

        # Build candidate dicts with backtest metrics
        cand_dicts = []
        for candidate in candidates:
            try:
                summary = run_backtest(
                    symbols=self.symbols,
                    interval=self.interval,
                    days=self.days,
                    cfg_override=candidate.config_overrides,
                )
                cand_dicts.append({
                    "passport_id": candidate.passport_id,
                    "family": candidate.family,
                    "sharpe": summary.get("sharpe", 0),
                    "calmar": summary.get("calmar", 0),
                    "max_dd": summary.get("max_dd", 50),
                    "equity_curve": summary.get("equity_curve", []),
                    "trades": summary.get("trade_details", []),
                    "dd_series": summary.get("dd_series", []),
                })
            except Exception as e:
                logger.warning("Backtest for Stage 4 failed for %s: %s",
                               candidate.slug, e)

        result = self.stage4.select_portfolio(cand_dicts)
        logger.info("Stage 4: selected %d for portfolio (utility=%.2f)",
                     len(result.selected_passport_ids), result.portfolio_utility)
        return result

    def run_full(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
    ) -> list[PassportCandidate]:
        """Run the 2-stage pipeline: generate → Stage 1 → Stage 2."""
        candidates = self.generate_candidates(families, max_per_family)
        stage1_survivors = self.run_stage1(candidates)
        stage2_survivors = self.run_stage2(stage1_survivors)

        self.tracker.finish_experiment(
            self.run_id,
            stage1_survivors=len(stage1_survivors),
            stage2_survivors=len(stage2_survivors),
        )

        logger.info(
            "Pipeline complete: %d generated → %d stage1 → %d stage2",
            len(candidates), len(stage1_survivors), len(stage2_survivors),
        )
        return stage2_survivors

    def run_full_4stage(
        self,
        families: Optional[list[str]] = None,
        max_per_family: Optional[int] = None,
        mc_iterations: int = 50,
    ) -> Stage4Result:
        """Run the complete 4-stage pipeline: generate → S1 → S2 → S3 → S4."""
        candidates = self.generate_candidates(families, max_per_family)
        stage1_survivors = self.run_stage1(candidates)
        stage2_survivors = self.run_stage2(stage1_survivors)
        stage3_survivors = self.run_stage3(stage2_survivors, mc_iterations)
        result = self.run_stage4(stage3_survivors)

        self.tracker.finish_experiment(
            self.run_id,
            stage1_survivors=len(stage1_survivors),
            stage2_survivors=len(stage2_survivors),
        )

        logger.info(
            "4-stage pipeline: %d → %d S1 → %d S2 → %d S3 → %d selected",
            len(candidates), len(stage1_survivors), len(stage2_survivors),
            len(stage3_survivors), len(result.selected_passport_ids),
        )
        return result


def _calc_folds(
    total_days: int, train_days: int, test_days: int, slide: int = 30,
) -> list[tuple[int, int]]:
    """Calculate walk-forward fold offsets.

    Returns list of (train_end_offset, test_end_offset) in days from end.
    """
    fold_size = train_days + test_days
    folds = []
    offset = 0
    while offset + fold_size <= total_days:
        test_end_offset = offset
        train_end_offset = offset + test_days
        folds.append((train_end_offset, test_end_offset))
        offset += slide

    if not folds:
        folds.append((0, 0))

    return folds
