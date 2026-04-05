"""Execution types: OrderIntent, Fill, PositionRecord."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

VALID_DIRECTIONS = {"LONG", "SHORT"}
VALID_NAMESPACES = {"paper", "prod"}
VALID_STATUSES = {"open", "closed", "cancelled", "liquidated"}


@dataclass
class OrderIntent:
    passport_id: str
    symbol: str
    direction: str
    signal_confidence: float
    size_hint: float
    stop_loss: float
    take_profit: float
    entry_price: float
    cooldown_key: str
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"oi_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction: {self.direction}")


@dataclass
class Fill:
    order_intent_id: str
    fill_price: float
    fill_size: float
    slippage_bps: float
    fee_bps: float
    timestamp: datetime
    is_paper: bool
    fill_id: str = field(default_factory=lambda: f"fill_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")


@dataclass
class PositionRecord:
    position_id: str
    passport_id: str
    symbol: str
    direction: str
    entry_price: float
    current_price: float
    size: float
    unrealized_pnl: float
    stop_loss: float
    take_profit: float
    namespace: str
    opened_at: datetime
    status: str
    closed_at: Optional[datetime] = None
    realized_pnl: Optional[float] = None

    def __post_init__(self):
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction: {self.direction}")
        if self.namespace not in VALID_NAMESPACES:
            raise ValueError(f"Invalid namespace: {self.namespace}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {self.status}")
