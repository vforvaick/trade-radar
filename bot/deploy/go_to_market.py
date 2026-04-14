"""Go-to-market 10-gate scorecard for real-money deployment readiness."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class GateResult:
    gate: str
    passed: bool
    value: float
    threshold: float
    description: str = ""


@dataclass
class ScorecardResult:
    passport_name: str
    gates: list[GateResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(g.passed for g in self.gates)

    @property
    def passed_count(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    @property
    def total_count(self) -> int:
        return len(self.gates)

    def format_table(self) -> str:
        lines = [
            f"📋 Go-to-Market Scorecard: {self.passport_name}",
            f"   Result: {'✅ PASS' if self.all_passed else '❌ FAIL'} "
            f"({self.passed_count}/{self.total_count} gates)",
            "",
        ]
        for g in self.gates:
            icon = "✅" if g.passed else "❌"
            lines.append(
                f"   {icon} {g.gate:30s} | value={g.value:.2f} | "
                f"threshold={g.threshold:.2f} | {g.description}"
            )
        return "\n".join(lines)


GATE_DEFINITIONS = [
    {
        "name": "gate_1_return",
        "description": "180d return > 15%",
        "metric": "return_pct_180d",
        "threshold": 15.0,
        "comparator": "gt",
    },
    {
        "name": "gate_2_profit_factor",
        "description": "Profit factor > 1.3",
        "metric": "profit_factor",
        "threshold": 1.3,
        "comparator": "gt",
    },
    {
        "name": "gate_3_max_drawdown",
        "description": "Max drawdown < 40%",
        "metric": "max_drawdown",
        "threshold": 40.0,
        "comparator": "lt",
    },
    {
        "name": "gate_4_min_trades",
        "description": "Min 50 trades",
        "metric": "total_trades",
        "threshold": 50.0,
        "comparator": "gte",
    },
    {
        "name": "gate_5_win_rate",
        "description": "Win rate > 35%",
        "metric": "win_rate",
        "threshold": 35.0,
        "comparator": "gt",
    },
    {
        "name": "gate_6_mc_robust",
        "description": "Monte Carlo 70%+ profitable",
        "metric": "mc_profitable_pct",
        "threshold": 70.0,
        "comparator": "gte",
    },
    {
        "name": "gate_7_orthogonal",
        "description": "Orthogonality rank = 1",
        "metric": "correlation_group_rank",
        "threshold": 1.0,
        "comparator": "eq",
    },
    {
        "name": "gate_8_paper_days",
        "description": "30+ days paper trading",
        "metric": "paper_days",
        "threshold": 30.0,
        "comparator": "gte",
    },
    {
        "name": "gate_9_paper_pnl",
        "description": "Paper PnL positive",
        "metric": "paper_pnl",
        "threshold": 0.0,
        "comparator": "gt",
    },
    {
        "name": "gate_10_no_catastrophe",
        "description": "No single trade loss > 10% equity",
        "metric": "max_single_loss_pct",
        "threshold": 10.0,
        "comparator": "lt",
    },
]


class GoToMarketScorecard:
    """Evaluates passport readiness for real-money deployment."""

    def __init__(self, gate_overrides: Optional[dict] = None):
        self.gates = copy.deepcopy(GATE_DEFINITIONS)
        if gate_overrides:
            for gate in self.gates:
                if gate["name"] in gate_overrides:
                    gate["threshold"] = gate_overrides[gate["name"]]

    def evaluate(self, passport_name: str, metrics: dict) -> ScorecardResult:
        results = []
        for gate in self.gates:
            value = metrics[gate["metric"]]
            threshold = gate["threshold"]
            comparator = gate["comparator"]

            if comparator == "gt":
                passed = value > threshold
            elif comparator == "gte":
                passed = value >= threshold
            elif comparator == "lt":
                passed = value < threshold
            elif comparator == "lte":
                passed = value <= threshold
            elif comparator == "eq":
                passed = value == threshold
            else:
                passed = False

            results.append(GateResult(
                gate=gate["name"],
                passed=passed,
                value=float(value),
                threshold=float(threshold),
                description=gate["description"],
            ))

        return ScorecardResult(passport_name=passport_name, gates=results)

    def evaluate_from_db(
        self,
        passport_name: str,
        research_db_path: str = "research_experiments.db",
        state_db_path: str = "state.db",
    ) -> ScorecardResult:
        """Build metrics from research DB + paper state DB, then evaluate."""
        import sqlite3
        from datetime import datetime, timezone

        metrics = {}

        # Backtest metrics from research DB
        conn = sqlite3.connect(research_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("""
            SELECT e.metrics FROM eval_results e
            JOIN passports p ON e.passport_id = p.passport_id AND e.run_id = p.run_id
            WHERE p.slug LIKE ? AND e.stage = 2 AND e.passed = 1
            ORDER BY e.evaluated_at DESC LIMIT 1
        """, (f"%{passport_name}%",))
        row = cur.fetchone()
        if row:
            bt_metrics = json.loads(row["metrics"])
            metrics["return_pct_180d"] = bt_metrics.get("median_return", 0) * 100
            metrics["profit_factor"] = bt_metrics.get("avg_profit_factor", 0)
            metrics["max_drawdown"] = bt_metrics.get("max_fold_dd", 100)
            metrics["total_trades"] = bt_metrics.get("total_trades", 0)
            metrics["win_rate"] = bt_metrics.get("win_rate", 0)
        else:
            metrics.update({
                "return_pct_180d": 0, "profit_factor": 0,
                "max_drawdown": 100, "total_trades": 0, "win_rate": 0,
            })
        conn.close()

        # MC and orthogonality (default to not-yet-tested)
        metrics.setdefault("mc_profitable_pct", 0)
        metrics.setdefault("correlation_group_rank", 99)

        # Paper trading metrics from state DB
        state_conn = sqlite3.connect(state_db_path)
        state_conn.row_factory = sqlite3.Row

        cur = state_conn.execute("""
            SELECT MIN(timestamp) as first, MAX(timestamp) as last
            FROM equity_snapshots WHERE passport_name = ?
        """, (passport_name,))
        row = cur.fetchone()
        if row and row["first"]:
            first = datetime.fromisoformat(row["first"])
            last = datetime.fromisoformat(row["last"])
            metrics["paper_days"] = (last - first).days
        else:
            metrics["paper_days"] = 0

        cur = state_conn.execute("""
            SELECT equity FROM equity_snapshots
            WHERE passport_name = ? ORDER BY timestamp DESC LIMIT 1
        """, (passport_name,))
        row = cur.fetchone()
        from bot import config
        initial = getattr(config, "INITIAL_EQUITY", 500)
        metrics["paper_pnl"] = (row["equity"] - initial) if row else 0

        cur = state_conn.execute("""
            SELECT realized_pnl, equity_at_entry
            FROM positions WHERE passport_name = ? AND status != 'OPEN'
              AND equity_at_entry > 0
            ORDER BY ABS(realized_pnl) / equity_at_entry DESC LIMIT 1
        """, (passport_name,))
        row = cur.fetchone()
        if row and row["realized_pnl"] is not None and row["equity_at_entry"]:
            metrics["max_single_loss_pct"] = abs(row["realized_pnl"]) / row["equity_at_entry"] * 100
        else:
            metrics["max_single_loss_pct"] = 0

        state_conn.close()

        return self.evaluate(passport_name, metrics)
