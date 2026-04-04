"""Core types for the Strategy Research Engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RegimeType(Enum):
    """Market regime classification. Exclusive — each bar belongs to exactly one."""
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    HIGH_VOL_CHOP = "HIGH_VOL_CHOP"
    LOW_VOL_COMPRESSION = "LOW_VOL_COMPRESSION"


@dataclass
class BacktestMetrics:
    """Standardized backtest result metrics."""
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    return_pct: float = 0.0
    final_equity: float = 0.0
    max_dd: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    profit_factor: float = 0.0

    @classmethod
    def from_summary(cls, summary: dict) -> BacktestMetrics:
        """Create from backtester._summarize() output dict."""
        return cls(
            trades=summary.get("trades", 0),
            wins=summary.get("wins", 0),
            losses=summary.get("losses", 0),
            win_rate=summary.get("win_rate", 0.0),
            total_pnl=summary.get("total_pnl", 0.0),
            return_pct=summary.get("return_pct", 0.0),
            final_equity=summary.get("final_equity", 0.0),
            max_dd=summary.get("max_dd", 0.0),
            sharpe=summary.get("sharpe", 0.0),
            sortino=summary.get("sortino", 0.0),
            calmar=summary.get("calmar", 0.0),
            profit_factor=summary.get("profit_factor", 0.0),
        )


@dataclass
class PassportCandidate:
    """A generated passport configuration awaiting evaluation."""
    passport_id: str
    slug: str
    family: str
    config_overrides: dict
    status: str = "generated"
    description: str = ""
    param_summary: str = ""


@dataclass
class EvalResult:
    """Result of evaluating a passport at a specific stage."""
    passport_id: str
    stage: int
    passed: bool
    metrics: dict = field(default_factory=dict)
    reject_reason: Optional[str] = None
    secondary_reasons: list[str] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """Summary of a full research pipeline run."""
    run_id: str
    total_generated: int = 0
    stage1_survivors: int = 0
    stage2_survivors: int = 0
    results: list[EvalResult] = field(default_factory=list)
    rejected_log: list[dict] = field(default_factory=list)
