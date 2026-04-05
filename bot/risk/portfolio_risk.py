"""Portfolio Risk Manager — hard limits, soft alerts, exposure tracking."""
from __future__ import annotations

from typing import Optional


class PortfolioRiskManager:
    """Evaluates order intents against portfolio-level risk constraints."""

    def __init__(
        self,
        max_gross_exposure: float = 0.6,
        account_equity: float = 10000,
        family_cap: int = 3,
        cluster_cap: int = 3,
        dd_circuit_breaker: float = 0.15,
    ):
        self.max_gross_exposure = max_gross_exposure
        self.account_equity = account_equity
        self.family_cap = family_cap
        self.cluster_cap = cluster_cap
        self.dd_circuit_breaker = dd_circuit_breaker
        self._positions: dict[str, dict] = {}  # passport_id → {family, size}
        self._drawdowns: dict[str, float] = {}  # passport_id → current DD
        self._paused = False

    def evaluate(self, intent) -> dict:
        """Evaluate an OrderIntent against risk constraints.

        Returns dict with action (approve/resize/reject), reason, alerts.
        """
        alerts = []

        if self._paused:
            return {"action": "reject", "reason": "Emergency pause active",
                    "adjusted_size": 0, "alerts": alerts}

        # DD circuit breaker
        if intent.passport_id in self._drawdowns:
            if self._drawdowns[intent.passport_id] >= self.dd_circuit_breaker:
                return {"action": "reject",
                        "reason": f"Drawdown circuit breaker: {self._drawdowns[intent.passport_id]:.1%}",
                        "adjusted_size": 0, "alerts": alerts}

        # Family cap
        family = intent.metadata.get("family", "unknown")
        family_count = sum(1 for p in self._positions.values() if p.get("family") == family)
        if family_count >= self.family_cap:
            return {"action": "reject",
                    "reason": f"Family cap exceeded: {family} ({family_count}/{self.family_cap})",
                    "adjusted_size": 0, "alerts": alerts}

        # Exposure check (all sizes as fraction of equity)
        current_exposure = sum(p.get("size", 0) for p in self._positions.values())
        new_exposure = current_exposure + intent.size_hint

        if new_exposure > self.max_gross_exposure:
            remaining = self.max_gross_exposure - current_exposure
            if remaining <= 0:
                return {"action": "reject",
                        "reason": f"Exposure cap: {current_exposure:.4f}/{self.max_gross_exposure:.4f}",
                        "adjusted_size": 0, "alerts": alerts}
            return {"action": "resize",
                    "reason": f"Resized to fit exposure cap",
                    "adjusted_size": remaining, "alerts": alerts}

        return {"action": "approve", "reason": "Within limits",
                "adjusted_size": intent.size_hint, "alerts": alerts}

    def record_position(self, passport_id: str, family: str, size: float):
        self._positions[passport_id] = {"family": family, "size": size}

    def close_position(self, passport_id: str):
        self._positions.pop(passport_id, None)

    def update_drawdown(self, passport_id: str, current_dd: float):
        self._drawdowns[passport_id] = current_dd

    def emergency_pause(self):
        self._paused = True

    def resume(self):
        self._paused = False
