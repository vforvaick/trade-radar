"""
Position manager — tracks open positions and implements the 70/20/10 TP cascade.
"""
from dataclasses import dataclass, field
from typing import Optional
from bot import config
from bot.signals import Signal


@dataclass
class Position:
    """An open position being managed."""
    signal: Signal
    equity_at_entry: float
    risk_amount: float  # dollars risked
    status: str = "OPEN"  # OPEN, TP1, TP2, TP3_CLOSED, SL_CLOSED
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    sl_is_breakeven: bool = False
    realized_pnl: float = 0.0
    trailing_sl: Optional[float] = None
    pos_id: Optional[int] = None

    @property
    def active_sl(self):
        """Current SL price (moves to breakeven after TP1, or trails)."""
        if self.trailing_sl is not None:
            return self.trailing_sl
        if self.sl_is_breakeven:
            return self.signal.entry_price
        return self.signal.sl


class PositionManager:
    """Manages open positions and processes price updates."""

    def __init__(self):
        self.positions: list[Position] = []
        self.closed_positions: list[Position] = []

    @property
    def open_count(self):
        return len(self.positions)

    def can_open(self, signal: Optional[Signal] = None) -> bool:
        passport_cap = getattr(
            config,
            "MAX_OPEN_POSITIONS_PER_PASSPORT",
            config.MAX_SIMULTANEOUS,
        )
        if self.open_count >= passport_cap:
            return False

        if signal is None:
            return True

        symbol_cap = getattr(config, "MAX_OPEN_POSITIONS_PER_SYMBOL", 0)
        if symbol_cap <= 0:
            return True

        symbol_open_count = sum(
            1
            for pos in self.positions
            if pos.signal.symbol == signal.symbol
        )
        return symbol_open_count < symbol_cap

    def open_position(self, signal: Signal, equity: float) -> Optional[Position]:
        """Open a new position from a signal."""
        if not self.can_open(signal):
            return None

        risk_amount = equity * (config.RISK_PER_TRADE_PCT / 100)
        pos = Position(
            signal=signal,
            equity_at_entry=equity,
            risk_amount=risk_amount,
        )
        self.positions.append(pos)
        return pos

    def update_positions(self, prices: dict[str, tuple[float, float, float]]):
        """
        Check all open positions against current prices.

        Args:
            prices: dict of symbol -> (high, low, close) for the current candle

        Returns:
            list of (position, event) tuples for events that occurred
        """
        events = []
        to_remove = []

        for pos in self.positions:
            sym = pos.signal.symbol
            if sym not in prices:
                continue

            high, low, close = prices[sym]
            evts = self._check_position(pos, high, low)
            events.extend([(pos, e) for e in evts])

            if pos.status in ("TP3_CLOSED", "SL_CLOSED"):
                to_remove.append(pos)

        for pos in to_remove:
            self.positions.remove(pos)
            self.closed_positions.append(pos)

        return events

    def _check_position(self, pos: Position, high: float, low: float) -> list[str]:
        """Check a single position against a candle's high/low."""
        events = []
        sig = pos.signal
        is_long = sig.direction == "LONG"

        # Check SL first (priority over TP)
        sl = pos.active_sl
        if is_long and low <= sl:
            if pos.tp1_hit:
                # SL at breakeven after TP1 — close remaining at zero loss
                pos.status = "SL_CLOSED"
                # Already captured 70% profit at TP1, rest at breakeven
                events.append("SL_BREAKEVEN")
            else:
                pos.realized_pnl -= pos.risk_amount
                pos.status = "SL_CLOSED"
                events.append("SL_HIT")
            return events

        if not is_long and high >= sl:
            if pos.tp1_hit:
                pos.status = "SL_CLOSED"
                events.append("SL_BREAKEVEN")
            else:
                pos.realized_pnl -= pos.risk_amount
                pos.status = "SL_CLOSED"
                events.append("SL_HIT")
            return events

        # Check TP levels (must check in order: TP1 → TP2 → TP3)
        if not pos.tp1_hit:
            tp1_hit = (is_long and high >= sig.tp1) or (not is_long and low <= sig.tp1)
            if tp1_hit:
                pos.tp1_hit = True
                pos.sl_is_breakeven = True
                # 70% of position closed at TP1
                sl_dist = abs(sig.sl - sig.entry_price) / sig.entry_price
                tp1_dist = abs(sig.tp1 - sig.entry_price) / sig.entry_price
                profit_70 = pos.risk_amount * (tp1_dist / sl_dist) * config.TP1_CLOSE_PCT
                pos.realized_pnl += profit_70
                pos.status = "TP1"
                events.append("TP1_HIT")

        if pos.tp1_hit and not pos.tp2_hit:
            tp2_hit = (is_long and high >= sig.tp2) or (not is_long and low <= sig.tp2)
            if tp2_hit:
                pos.tp2_hit = True
                sl_dist = abs(sig.sl - sig.entry_price) / sig.entry_price
                tp2_dist = abs(sig.tp2 - sig.entry_price) / sig.entry_price
                profit_20 = pos.risk_amount * (tp2_dist / sl_dist) * config.TP2_CLOSE_PCT
                pos.realized_pnl += profit_20
                pos.status = "TP2"
                events.append("TP2_HIT")

        if pos.tp2_hit and not pos.tp3_hit:
            tp3_hit = (is_long and high >= sig.tp3) or (not is_long and low <= sig.tp3)
            if tp3_hit:
                pos.tp3_hit = True
                sl_dist = abs(sig.sl - sig.entry_price) / sig.entry_price
                tp3_dist = abs(sig.tp3 - sig.entry_price) / sig.entry_price
                profit_10 = pos.risk_amount * (tp3_dist / sl_dist) * config.TP3_CLOSE_PCT
                pos.realized_pnl += profit_10
                pos.status = "TP3_CLOSED"
                events.append("TP3_HIT")

        # Trailing stop logic (only active after TP2, if configured)
        if pos.tp2_hit and getattr(config, 'USE_TRAILING_STOP', False) and pos.status != "TP3_CLOSED":
            trail_dist = (sig.atr_at_entry or abs(sig.entry_price - sig.sl)) * getattr(config, 'ATR_TRAIL_MULTIPLIER', 2.0)
            if is_long:
                new_sl = high - trail_dist
                if pos.trailing_sl is None or new_sl > pos.trailing_sl:
                    # ensure we never trail below breakeven
                    if new_sl > sig.entry_price:
                        pos.trailing_sl = new_sl
            else:
                new_sl = low + trail_dist
                if pos.trailing_sl is None or new_sl < pos.trailing_sl:
                    if new_sl < sig.entry_price:
                        pos.trailing_sl = new_sl

        return events

    def get_total_pnl(self) -> float:
        """Total realized P&L across all closed positions."""
        return sum(p.realized_pnl for p in self.closed_positions)

    def get_stats(self) -> dict:
        """Summary statistics."""
        closed = self.closed_positions
        if not closed:
            return {"trades": 0}

        wins = [p for p in closed if p.realized_pnl > 0]
        losses = [p for p in closed if p.realized_pnl <= 0]

        return {
            "trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed) * 100 if closed else 0,
            "total_pnl": self.get_total_pnl(),
            "avg_win": sum(p.realized_pnl for p in wins) / len(wins) if wins else 0,
            "avg_loss": sum(p.realized_pnl for p in losses) / len(losses) if losses else 0,
            "open_positions": self.open_count,
        }
