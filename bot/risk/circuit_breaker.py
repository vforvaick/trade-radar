"""Circuit breaker — kills passport trading when drawdown exceeds threshold."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Disables passport trading when equity drawdown exceeds threshold.

    Default threshold: 30% drawdown from initial equity.
    Per-passport override via config_overrides.KILL_SWITCH_THRESHOLD.
    """

    def __init__(self, kill_threshold_pct: float = 0.30):
        self.kill_threshold_pct = kill_threshold_pct
        self.kill_log: list[dict] = []
        self._killed_passports: set[str] = set()

    def should_kill(
        self,
        passport_name: str,
        current_equity: float,
        initial_equity: float,
        override_threshold: Optional[float] = None,
    ) -> bool:
        """Check if passport should be killed due to drawdown.

        Returns True if drawdown >= threshold. Logs kill event on first trigger.
        """
        if initial_equity <= 0:
            return False

        threshold = override_threshold or self.kill_threshold_pct
        drawdown = (initial_equity - current_equity) / initial_equity

        if drawdown >= threshold:
            if passport_name not in self._killed_passports:
                self._killed_passports.add(passport_name)
                event = {
                    "passport": passport_name,
                    "equity": current_equity,
                    "initial_equity": initial_equity,
                    "drawdown_pct": round(drawdown * 100, 2),
                    "threshold_pct": round(threshold * 100, 2),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.kill_log.append(event)
                logger.warning(
                    "🔴 KILL SWITCH: %s — equity $%.2f (%.1f%% drawdown, threshold %.0f%%)",
                    passport_name, current_equity, drawdown * 100, threshold * 100,
                )
            return True

        return False

    def is_killed(self, passport_name: str) -> bool:
        return passport_name in self._killed_passports

    def reset(self, passport_name: str) -> None:
        self._killed_passports.discard(passport_name)
