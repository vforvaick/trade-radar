"""Position Manager — converts signals to OrderIntents with cooldown + pyramiding."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from bot.execution.types import OrderIntent


class PositionManager:
    """Manages signal-to-intent conversion with cooldown and position limits."""

    def __init__(
        self,
        default_size: float = 0.02,
        cooldown_minutes: int = 60,
        max_pyramiding: int = 1,
        min_confidence: float = 55.0,
    ):
        self.default_size = default_size
        self.cooldown_minutes = cooldown_minutes
        self.max_pyramiding = max_pyramiding
        self.min_confidence = min_confidence
        self._cooldowns: dict[str, datetime] = {}
        self._open_positions: dict[str, int] = {}

    def signal_to_intent(
        self,
        passport_id: str,
        symbol: str,
        signal: dict,
    ) -> Optional[OrderIntent]:
        """Convert a signal dict to an OrderIntent, or None if blocked."""
        direction = signal.get("direction")
        if not direction:
            return None

        confidence = signal.get("confidence", 0)
        if confidence < self.min_confidence:
            return None

        cooldown_key = f"{passport_id}:{symbol}"

        # Check cooldown
        if cooldown_key in self._cooldowns:
            last = self._cooldowns[cooldown_key]
            if datetime.now() - last < timedelta(minutes=self.cooldown_minutes):
                return None

        # Check pyramiding
        if self._open_positions.get(cooldown_key, 0) >= self.max_pyramiding:
            return None

        # Create intent
        intent = OrderIntent(
            passport_id=passport_id,
            symbol=symbol,
            direction=direction,
            signal_confidence=confidence,
            size_hint=self.default_size,
            stop_loss=signal.get("stop_loss", 0),
            take_profit=signal.get("take_profit", 0),
            entry_price=signal.get("entry_price", 0),
            cooldown_key=cooldown_key,
            metadata=signal.get("metadata", {}),
        )

        self._cooldowns[cooldown_key] = datetime.now()
        return intent

    def record_fill(self, intent: OrderIntent):
        """Record that an intent was filled — increment open positions."""
        key = intent.cooldown_key
        self._open_positions[key] = self._open_positions.get(key, 0) + 1

    def record_close(self, passport_id: str, symbol: str):
        """Record that a position was closed — decrement open positions."""
        key = f"{passport_id}:{symbol}"
        if key in self._open_positions:
            self._open_positions[key] = max(0, self._open_positions[key] - 1)
