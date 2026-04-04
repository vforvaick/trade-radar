"""Promotion Engine — 7-point policy gate for passport promotion."""
from __future__ import annotations

from typing import Optional


class PromotionPolicy:
    """7-point policy gate for promoting passports between lifecycle stages."""

    def __init__(
        self,
        min_paper_days: int = 14,
        min_paper_trades: int = 20,
        min_sharpe: float = 0.3,
        max_dd: float = 0.25,
        min_win_rate: float = 0.40,
        min_profit_factor: float = 1.0,
        max_correlation: float = 0.5,
    ):
        self.min_paper_days = min_paper_days
        self.min_paper_trades = min_paper_trades
        self.min_sharpe = min_sharpe
        self.max_dd = max_dd
        self.min_win_rate = min_win_rate
        self.min_profit_factor = min_profit_factor
        self.max_correlation = max_correlation

    def evaluate(self, metrics: dict) -> dict:
        """Evaluate passport metrics against 7 promotion gates.

        Returns dict with passed (bool), gates (dict of gate results).
        """
        gates = {}

        # 1. Minimum paper trading days
        days = metrics.get("paper_days", 0)
        gates["paper_duration"] = {
            "passed": days >= self.min_paper_days,
            "reason": f"{days}/{self.min_paper_days} days",
        }

        # 2. Minimum paper trades
        trades = metrics.get("paper_trades", 0)
        gates["paper_trades"] = {
            "passed": trades >= self.min_paper_trades,
            "reason": f"{trades}/{self.min_paper_trades} trades",
        }

        # 3. Sharpe ratio
        sharpe = metrics.get("sharpe", 0)
        gates["sharpe"] = {
            "passed": sharpe >= self.min_sharpe,
            "reason": f"{sharpe:.2f} >= {self.min_sharpe}",
        }

        # 4. Maximum drawdown
        dd = metrics.get("max_dd", 1.0)
        gates["max_drawdown"] = {
            "passed": dd <= self.max_dd,
            "reason": f"{dd:.1%} <= {self.max_dd:.1%}",
        }

        # 5. Win rate
        wr = metrics.get("win_rate", 0)
        gates["win_rate"] = {
            "passed": wr >= self.min_win_rate,
            "reason": f"{wr:.1%} >= {self.min_win_rate:.1%}",
        }

        # 6. Profit factor
        pf = metrics.get("profit_factor", 0)
        gates["profit_factor"] = {
            "passed": pf >= self.min_profit_factor,
            "reason": f"{pf:.2f} >= {self.min_profit_factor}",
        }

        # 7. Portfolio correlation
        corr = metrics.get("portfolio_correlation", 0)
        gates["portfolio_correlation"] = {
            "passed": corr <= self.max_correlation,
            "reason": f"{corr:.2f} <= {self.max_correlation}",
        }

        passed = all(g["passed"] for g in gates.values())
        return {
            "passed": passed,
            "passport_id": metrics.get("passport_id", "unknown"),
            "gates": gates,
        }
