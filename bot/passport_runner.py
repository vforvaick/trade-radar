"""
Multi-Passport Strategy Runner.
Loads passport configs from JSON files, runs each through the scoring pipeline
with its own config overrides and independent PositionManager.
"""
import os
import json
import time
from datetime import datetime
from typing import List, Dict

from bot import config
from bot.scanner import Scanner
from bot.signals import generate_signal, Signal
from bot.position_manager import PositionManager, Position
from bot.data_fetcher import fetch_klines
from bot.state_store import StateStore


class Passport:
    """A single strategy passport with its own config and state."""

    def __init__(self, filepath: str):
        with open(filepath) as f:
            data = json.load(f)

        self.name = data["name"]
        self.emoji = data.get("emoji", "📊")
        self.description = data.get("description", "")
        self.config_overrides = data.get("config_overrides", {})
        self.position_manager = PositionManager()
        self.equity = config.INITIAL_EQUITY
        self.trade_count = 0
        self.signal_count = 0

    def __repr__(self):
        return f"Passport({self.name})"


class PassportRunner:
    """Orchestrates multiple passport strategies."""

    def __init__(self, passport_dir: str, interval: str = "1h"):
        self.state_store = StateStore()
        self.passports = self._load_passports(passport_dir)
        self.scanner = Scanner(interval=interval, limit=100)
        self.interval = interval

        print(f"[PassportRunner] Loaded {len(self.passports)} passports:", flush=True)
        for p in self.passports:
            # Restore state
            last_equity = self.state_store.get_last_equity(p.name)
            if last_equity:
                p.equity = last_equity
                
            open_positions = self.state_store.load_open_positions(p.name)
            for row in open_positions:
                sig_dict = json.loads(row["signal_json"])
                if 'timestamp' in sig_dict and isinstance(sig_dict['timestamp'], str):
                    try:
                        sig_dict['timestamp'] = datetime.fromisoformat(sig_dict['timestamp'])
                    except:
                        pass
                sig = Signal(**sig_dict)
                pos = Position(
                    signal=sig,
                    equity_at_entry=row["equity_at_entry"],
                    risk_amount=row["risk_amount"],
                    status=row["status"],
                    tp1_hit=bool(row["tp1_hit"]),
                    tp2_hit=bool(row["tp2_hit"]),
                    tp3_hit=bool(row["tp3_hit"]),
                    sl_is_breakeven=bool(row["sl_is_breakeven"]),
                    realized_pnl=row["realized_pnl"],
                    trailing_sl=row["trailing_sl"],
                    pos_id=row["id"]
                )
                p.position_manager.positions.append(pos)
                
            print(f"  {p.emoji} {p.name}: {p.description} (Equity: ${p.equity:,.0f}, Open Pos: {len(open_positions)})", flush=True)

    def _load_passports(self, passport_dir: str) -> List[Passport]:
        """Load all *.json passport configs from a directory."""
        passports = []
        if not os.path.isdir(passport_dir):
            print(f"[PassportRunner] Warning: {passport_dir} not found", flush=True)
            return passports

        for fname in sorted(os.listdir(passport_dir)):
            if fname.endswith(".json"):
                try:
                    p = Passport(os.path.join(passport_dir, fname))
                    passports.append(p)
                except Exception as e:
                    print(f"[PassportRunner] Error loading {fname}: {e}", flush=True)

        return passports

    def run_scan_cycle(self) -> List[Dict]:
        """
        Run a full scan cycle across all passports.
        Each passport gets its own config overrides applied temporarily.

        Returns list of (signal, passport) tuples for signals found.
        """
        all_results = []

        # Refresh BTC trend once (shared across passports)
        self.scanner.update_btc_trend()

        for passport in self.passports:
            print(f"\n[{passport.emoji} {passport.name}] Scanning...", flush=True)

            # Save original config
            original_config = self._save_config()

            # Apply passport overrides
            self._apply_overrides(passport.config_overrides)

            try:
                signals = self.scanner.scan_all()

                for sig in signals:
                    if passport.position_manager.can_open():
                        pos = passport.position_manager.open_position(sig, passport.equity)
                        if pos:
                            pos_id = self.state_store.save_position(
                                passport.name, sig, passport.equity, pos.risk_amount
                            )
                            pos.pos_id = pos_id
                            passport.signal_count += 1
                            all_results.append({
                                "signal": sig,
                                "passport": passport,
                                "position": pos
                            })

                print(f"[{passport.emoji} {passport.name}] "
                      f"Found {len(signals)} signals, "
                      f"Open: {passport.position_manager.open_count}", flush=True)

            except Exception as e:
                print(f"[{passport.emoji} {passport.name}] Error: {e}", flush=True)

            finally:
                # ALWAYS restore config to not pollute next passport
                self._restore_config(original_config)

        return all_results

    def update_all_positions(self):
        """Check TP/SL for all passports' open positions."""
        events = []
        for passport in self.passports:
            if passport.position_manager.open_count == 0:
                continue

            current_prices = {}
            for pos in passport.position_manager.positions:
                sym = pos.signal.symbol
                try:
                    df = fetch_klines(sym, "1m", limit=1, use_cache=False)
                    if not df.empty:
                        current_prices[sym] = (
                            df.iloc[0]['high'],
                            df.iloc[0]['low'],
                            df.iloc[0]['close']
                        )
                except Exception:
                    pass

            pos_events = passport.position_manager.update_positions(current_prices)
            for pos, event in pos_events:
                self.state_store.update_position(
                    pos.pos_id, 
                    status=pos.status,
                    tp1_hit=pos.tp1_hit,
                    tp2_hit=pos.tp2_hit,
                    tp3_hit=pos.tp3_hit,
                    sl_is_breakeven=pos.sl_is_breakeven,
                    realized_pnl=pos.realized_pnl,
                    trailing_sl=pos.trailing_sl
                )
                
                if event in ("SL_HIT", "SL_BREAKEVEN", "TP3_HIT"):
                    passport.equity += pos.realized_pnl
                    passport.trade_count += 1
                    self.state_store.save_equity(passport.name, passport.equity)
                    self.state_store.log_trade(passport.name, {
                        "symbol": pos.signal.symbol,
                        "event": event,
                        "realized_pnl": pos.realized_pnl,
                        "equity": passport.equity,
                        "timestamp": datetime.now().isoformat()
                    })

                events.append({
                    "passport": passport,
                    "position": pos,
                    "event": event,
                })

        return events

    def get_summary(self) -> str:
        """Get summary of all passports' performance."""
        lines = ["\n📊 Multi-Passport Summary:"]
        for p in self.passports:
            stats = p.position_manager.get_stats()
            pnl_pct = (p.equity / config.INITIAL_EQUITY - 1) * 100
            lines.append(
                f"  {p.emoji} {p.name}: "
                f"Equity=${p.equity:,.0f} ({pnl_pct:+.1f}%) | "
                f"Signals={p.signal_count} | "
                f"Trades={p.trade_count} | "
                f"Open={p.position_manager.open_count}"
            )
        return "\n".join(lines)

    def _save_config(self) -> Dict:
        """Snapshot current config values."""
        keys = [
            'EMA_FAST', 'EMA_MID', 'EMA_SLOW',
            'VOLUME_SPIKE_THRESHOLD', 'INDICATOR_WEIGHTS',
            'USE_ATR_EXITS', 'USE_TRAILING_STOP',
        ]
        return {k: getattr(config, k, None) for k in keys}

    def _apply_overrides(self, overrides: Dict):
        """Apply passport config overrides to global config."""
        for k, v in overrides.items():
            setattr(config, k, v)

    def _restore_config(self, original: Dict):
        """Restore original config values."""
        for k, v in original.items():
            if v is not None:
                setattr(config, k, v)
            elif hasattr(config, k):
                delattr(config, k)
