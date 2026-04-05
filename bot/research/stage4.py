"""Stage 4 evaluator — orthogonality check + portfolio construction.

Selects a diverse, uncorrelated portfolio from Stage 3 survivors using:
- Equity curve correlation
- Trade overlap
- Drawdown coincidence
- Composite utility (Sharpe + Calmar / DD-normalized)
- Marginal contribution test
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bot.research.types import Stage4Result


def calc_equity_correlation(curve_a: pd.Series, curve_b: pd.Series) -> float:
    """Pearson correlation on daily returns of two equity curves."""
    if len(curve_a) < 3 or len(curve_b) < 3:
        return 0.0
    min_len = min(len(curve_a), len(curve_b))
    ret_a = pd.Series(curve_a.values[:min_len]).diff().dropna()
    ret_b = pd.Series(curve_b.values[:min_len]).diff().dropna()
    if ret_a.std() == 0 or ret_b.std() == 0:
        return 0.0
    return float(ret_a.corr(ret_b))


def calc_trade_overlap(trades_a: list[dict], trades_b: list[dict]) -> float:
    """Fraction of trades overlapping in symbol + direction + time window."""
    if not trades_a or not trades_b:
        return 0.0

    overlap_count = 0
    for ta in trades_a:
        for tb in trades_b:
            if (ta["symbol"] == tb["symbol"]
                    and ta["direction"] == tb["direction"]
                    and ta["entry_bar"] <= tb["exit_bar"]
                    and ta["exit_bar"] >= tb["entry_bar"]):
                overlap_count += 1
                break

    return overlap_count / len(trades_a)


def calc_dd_coincidence(
    dd_a: pd.Series, dd_b: pd.Series,
    threshold: float = 10.0, window: int = 5,
) -> float:
    """Fraction of deep-drawdown bars that coincide between two strategies."""
    min_len = min(len(dd_a), len(dd_b))
    a = dd_a.values[:min_len]
    b = dd_b.values[:min_len]

    deep_a = a < -threshold
    deep_b = b < -threshold

    # Expand windows
    expanded_a = np.zeros(min_len, dtype=bool)
    expanded_b = np.zeros(min_len, dtype=bool)
    for i in range(min_len):
        if deep_a[i]:
            start = max(0, i - window // 2)
            end = min(min_len, i + window // 2 + 1)
            expanded_a[start:end] = True
        if deep_b[i]:
            start = max(0, i - window // 2)
            end = min(min_len, i + window // 2 + 1)
            expanded_b[start:end] = True

    coinciding = np.sum(expanded_a & expanded_b)
    total_deep = max(np.sum(expanded_a), np.sum(expanded_b))

    if total_deep == 0:
        return 0.0
    return float(coinciding / total_deep)


def calc_composite_utility(
    sharpe: float, calmar: float, max_dd: float,
) -> float:
    """Composite utility: (sharpe + calmar) / (max_dd / 30)."""
    dd_factor = max_dd / 30.0
    if dd_factor <= 0:
        return 0.0
    return (sharpe + calmar) / dd_factor


def calc_marginal_contribution(
    existing_utility: float, new_utility: float,
) -> float:
    """Delta utility from adding a new strategy."""
    return new_utility - existing_utility


class Stage4Evaluator:
    """Selects diverse portfolio from Stage 3 survivors."""

    def __init__(
        self,
        family_cap: int = 3,
        cluster_cap: int = 3,
        min_delta_utility: float = 0.05,
        max_equity_corr: float = 0.4,
        max_trade_overlap: float = 0.2,
        max_dd_coincidence: float = 0.3,
        target_min: int = 10,
        target_max: int = 20,
    ):
        self.family_cap = family_cap
        self.cluster_cap = cluster_cap
        self.min_delta_utility = min_delta_utility
        self.max_equity_corr = max_equity_corr
        self.max_trade_overlap = max_trade_overlap
        self.max_dd_coincidence = max_dd_coincidence
        self.target_min = target_min
        self.target_max = target_max

    def select_portfolio(self, candidates: list[dict]) -> Stage4Result:
        """Select diverse portfolio from ranked candidates.

        Each candidate dict should contain:
            passport_id, family, sharpe, calmar, max_dd,
            equity_curve (list), trades (list of dicts), dd_series (list)
        """
        if not candidates:
            return Stage4Result(
                selected_passport_ids=[], portfolio_utility=0.0,
                portfolio_sharpe=0.0, portfolio_max_dd=0.0,
            )

        # Rank by composite utility
        for c in candidates:
            c["utility"] = calc_composite_utility(
                c.get("sharpe", 0), c.get("calmar", 0), c.get("max_dd", 20),
            )
        ranked = sorted(candidates, key=lambda c: c["utility"], reverse=True)

        selected = []
        family_counts: dict[str, int] = {}
        rejection_log = []
        corr_matrix = {}

        for cand in ranked:
            pid = cand["passport_id"]
            family = cand.get("family", "unknown")

            # Family cap
            if family_counts.get(family, 0) >= self.family_cap:
                rejection_log.append({"passport_id": pid, "reason": f"Family cap ({family})"})
                continue

            # Check overlap with each selected
            rejected = False
            for sel in selected:
                sel_pid = sel["passport_id"]

                # Equity correlation
                eq_a = pd.Series(cand.get("equity_curve", []))
                eq_b = pd.Series(sel.get("equity_curve", []))
                if len(eq_a) > 2 and len(eq_b) > 2:
                    corr = calc_equity_correlation(eq_a, eq_b)
                    key = f"{pid}|{sel_pid}"
                    corr_matrix[key] = corr
                    if abs(corr) > self.max_equity_corr:
                        rejection_log.append({
                            "passport_id": pid,
                            "reason": f"High corr with {sel_pid}: {corr:.2f}",
                        })
                        rejected = True
                        break

                # Trade overlap
                overlap = calc_trade_overlap(
                    cand.get("trades", []), sel.get("trades", []),
                )
                if overlap > self.max_trade_overlap:
                    rejection_log.append({
                        "passport_id": pid,
                        "reason": f"Trade overlap with {sel_pid}: {overlap:.2f}",
                    })
                    rejected = True
                    break

                # DD coincidence
                dd_a = pd.Series(cand.get("dd_series", []))
                dd_b = pd.Series(sel.get("dd_series", []))
                if len(dd_a) > 2 and len(dd_b) > 2:
                    coincidence = calc_dd_coincidence(dd_a, dd_b)
                    if coincidence > self.max_dd_coincidence:
                        rejection_log.append({
                            "passport_id": pid,
                            "reason": f"DD coincidence with {sel_pid}: {coincidence:.2f}",
                        })
                        rejected = True
                        break

            if rejected:
                continue

            # Accept
            selected.append(cand)
            family_counts[family] = family_counts.get(family, 0) + 1

            if len(selected) >= self.target_max:
                break

        # Portfolio metrics
        selected_ids = [s["passport_id"] for s in selected]
        if selected:
            portfolio_sharpe = float(np.mean([s.get("sharpe", 0) for s in selected]))
            portfolio_dd = float(np.max([s.get("max_dd", 0) for s in selected]))
            portfolio_utility = float(np.sum([s.get("utility", 0) for s in selected]))
        else:
            portfolio_sharpe = 0.0
            portfolio_dd = 0.0
            portfolio_utility = 0.0

        return Stage4Result(
            selected_passport_ids=selected_ids,
            portfolio_utility=portfolio_utility,
            portfolio_sharpe=portfolio_sharpe,
            portfolio_max_dd=portfolio_dd,
            family_counts=family_counts,
            cluster_counts={},
            correlation_matrix=corr_matrix,
            rejection_log=rejection_log,
        )
