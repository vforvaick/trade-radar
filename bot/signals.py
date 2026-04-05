"""
Signal generator.
Takes scorer output + entry price → calculates TP1/TP2/TP3/SL levels.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from bot import config


@dataclass
class Signal:
    """A complete trade signal with entry, targets, and stop loss."""
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    tp1: float
    tp2: float
    tp3: float
    sl: float
    leverage: int
    risk_reward: float
    confidence: float
    btc_trend: str
    timestamp: Optional[datetime] = None
    indicators: dict = field(default_factory=dict)
    atr_at_entry: Optional[float] = None  # ATR value at signal time, for trailing stop

    @property
    def sl_distance_pct(self):
        return abs(self.sl - self.entry_price) / self.entry_price * 100

    @property
    def tp1_distance_pct(self):
        return abs(self.tp1 - self.entry_price) / self.entry_price * 100

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry_price,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "sl": self.sl,
            "leverage": self.leverage,
            "rr": self.risk_reward,
            "confidence": self.confidence,
            "btc_trend": self.btc_trend,
            "sl_dist_pct": round(self.sl_distance_pct, 2),
            "tp1_dist_pct": round(self.tp1_distance_pct, 2),
        }


def generate_signal(symbol: str, entry_price: float, score_result: dict,
                    timestamp: datetime = None) -> Optional[Signal]:
    """
    Generate a full trade signal from scorer output.

    Args:
        symbol: e.g. 'BTCUSDT'
        entry_price: current market price
        score_result: output from scorer.score_confluence()
        timestamp: signal time

    Returns:
        Signal object or None if no-go
    """
    if not score_result["go"] or score_result["direction"] is None:
        return None

    direction = score_result["direction"]
    rr = score_result["risk_reward"]
    lev = score_result["leverage"]

    use_atr = getattr(config, "USE_ATR_EXITS", False)
    atr_val = score_result.get('atr')

    if use_atr and atr_val:
        sl_atr = atr_val * 2.0
        tp1_atr = atr_val * 4.0
        tp2_atr = tp1_atr * config.TP2_RATIO
        tp3_atr = tp2_atr * config.TP3_RATIO
        if direction == "LONG":
            sl = entry_price - sl_atr
            tp1 = entry_price + tp1_atr
            tp2 = entry_price + tp2_atr
            tp3 = entry_price + tp3_atr
        else:
            sl = entry_price + sl_atr
            tp1 = entry_price - tp1_atr
            tp2 = entry_price - tp2_atr
            tp3 = entry_price - tp3_atr
    else:
        # Calculate SL distance based on R:R tier
        sl_dist_pct = _estimate_sl_distance(rr)
        tp1_dist_pct = sl_dist_pct * rr
        tp2_dist_pct = tp1_dist_pct * config.TP2_RATIO
        tp3_dist_pct = tp2_dist_pct * config.TP3_RATIO

        if direction == "LONG":
            sl = entry_price * (1 - sl_dist_pct / 100)
            tp1 = entry_price * (1 + tp1_dist_pct / 100)
            tp2 = entry_price * (1 + tp2_dist_pct / 100)
            tp3 = entry_price * (1 + tp3_dist_pct / 100)
        else:  # SHORT
            sl = entry_price * (1 + sl_dist_pct / 100)
            tp1 = entry_price * (1 - tp1_dist_pct / 100)
            tp2 = entry_price * (1 - tp2_dist_pct / 100)
            tp3 = entry_price * (1 - tp3_dist_pct / 100)

    return Signal(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        tp1=round(tp1, 8),
        tp2=round(tp2, 8),
        tp3=round(tp3, 8),
        sl=round(sl, 8),
        leverage=lev,
        risk_reward=rr,
        confidence=score_result["confidence"],
        btc_trend=score_result.get("btc_trend", "Unknown"),
        timestamp=timestamp,
        indicators=score_result.get("signals", {}),
        atr_at_entry=score_result.get("atr"),
    )


def _estimate_sl_distance(rr: float) -> float:
    """
    Estimate SL distance percentage based on R:R tier.
    Values derived from reverse engineering:
      R:R 1.25 → SL ~3.49%
      R:R 1.43 → SL ~4.10%
      R:R 2.08 → SL ~3.81%
    """
    sl_map = {
        1.25: 3.49,
        1.43: 4.10,
        1.87: 2.73,
        1.88: 5.12,
        2.08: 3.81,
        2.87: 0.36,
    }
    # Find closest R:R
    closest = min(sl_map.keys(), key=lambda x: abs(x - rr))
    return sl_map[closest]
