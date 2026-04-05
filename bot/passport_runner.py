"""
Multi-Passport Strategy Runner.
Loads passport configs from JSON files, runs each through the scoring pipeline
with its own config overrides and independent PositionManager.
"""
import os
import json
import logging
import time
from datetime import datetime
from typing import List, Dict

from bot import config
from bot.scanner import Scanner
from bot.signals import generate_signal, Signal
from bot.position_manager import PositionManager, Position
from bot.data_fetcher import fetch_klines
from bot.state_store import StateStore


logger = logging.getLogger(__name__)


class Passport:
    """A single strategy passport with its own config and state."""

    def __init__(self, filepath: str):
        with open(filepath) as f:
            data = json.load(f)

        self.name = data["name"]
        self.emoji = data.get("emoji", "📊")
        self.enabled = _is_enabled(data)
        self.description = data.get("description", "")
        self.config_overrides = data.get("config_overrides", {})
        self.position_manager = PositionManager()
        self.equity = config.INITIAL_EQUITY
        self.trade_count = 0
        self.signal_count = 0

    def __repr__(self):
        return f"Passport({self.name})"


def _is_enabled(passport_data: dict) -> bool:
    return passport_data.get("enabled", True) is not False


class PassportRunner:
    """Orchestrates multiple passport strategies."""

    def __init__(self, passport_dir: str, interval: str = "1h"):
        self.passport_load_error_count = 0
        self.state_restore_error_count = 0
        self.scan_cycle_error_count = 0
        self.price_fetch_error_count = 0
        self.state_store = StateStore()
        self.passports = self._load_passports(passport_dir)
        self.scanner = Scanner(interval=interval, limit=100)
        self.interval = interval

        print(f"[PassportRunner] Loaded {len(self.passports)} passports:", flush=True)
        for p in self.passports:
            # Restore state
            last_equity = self.state_store.get_last_equity(p.name)
            if last_equity is not None:
                p.equity = last_equity
                
            open_positions = self.state_store.load_open_positions(p.name)
            for row in open_positions:
                self._restore_position_row(p, row)
                
            print(
                f"  {p.emoji} {p.name}: {p.description} "
                f"(Equity: ${p.equity:,.0f}, Open Pos: {p.position_manager.open_count})",
                flush=True,
            )

    def _load_passports(self, passport_dir: str) -> List[Passport]:
        """Load all *.json passport configs from a directory."""
        passports = []
        if not os.path.isdir(passport_dir):
            print(f"[PassportRunner] Warning: {passport_dir} not found", flush=True)
            return passports

        for fname in sorted(os.listdir(passport_dir)):
            if fname.endswith(".json"):
                try:
                    fpath = os.path.join(passport_dir, fname)
                    with open(fpath) as f:
                        passport_data = json.load(f)
                    if not _is_enabled(passport_data):
                        open_positions = self.state_store.load_open_positions(passport_data["name"])
                        if open_positions:
                            print(
                                f"[PassportRunner] Restoring disabled passport with {len(open_positions)} open positions: {fname}",
                                flush=True,
                            )
                        else:
                            print(f"[PassportRunner] Skipping disabled passport config: {fname}", flush=True)
                            continue
                    p = Passport(fpath)
                    passports.append(p)
                except Exception as e:
                    self.passport_load_error_count += 1
                    logger.exception(
                        "Failed to load passport config file=%s path=%s",
                        fname,
                        os.path.join(passport_dir, fname),
                    )
                    print(f"[PassportRunner] Error loading {fname}: {e}", flush=True)

        return passports

    def _restore_position_row(self, passport: Passport, row: dict):
        """Restore one open-position row and skip malformed rows with context-rich logs."""
        try:
            sig_dict = json.loads(row["signal_json"])
            if "timestamp" in sig_dict and sig_dict["timestamp"] is not None:
                if isinstance(sig_dict["timestamp"], str):
                    try:
                        sig_dict["timestamp"] = datetime.fromisoformat(sig_dict["timestamp"])
                    except Exception as e:
                        self.state_restore_error_count += 1
                        logger.exception(
                            "Failed to parse restored timestamp passport=%s symbol=%s pos_id=%s",
                            passport.name,
                            row["symbol"],
                            row["id"],
                        )
                        print(
                            f"[PassportRunner] Failed to parse restored timestamp for {passport.name}/{row['symbol']}: {e}",
                            flush=True,
                        )
                        return
                if not isinstance(sig_dict["timestamp"], datetime):
                    self.state_restore_error_count += 1
                    logger.error(
                        "Failed to restore open position passport=%s symbol=%s pos_id=%s invalid_timestamp_type=%s",
                        passport.name,
                        row["symbol"],
                        row["id"],
                        type(sig_dict["timestamp"]).__name__,
                    )
                    print(
                        f"[PassportRunner] Failed to restore open position for {passport.name}/{row['symbol']}: "
                        f"invalid timestamp type {type(sig_dict['timestamp']).__name__}",
                        flush=True,
                    )
                    return
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
            passport.position_manager.positions.append(pos)
        except Exception as e:
            self.state_restore_error_count += 1
            logger.exception(
                "Failed to restore open position passport=%s symbol=%s pos_id=%s",
                passport.name,
                row.get("symbol"),
                row.get("id"),
            )
            print(
                f"[PassportRunner] Failed to restore open position for {passport.name}/{row.get('symbol')}: {e}",
                flush=True,
            )

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
            if not passport.enabled:
                print(
                    f"\n[{passport.emoji} {passport.name}] Scan disabled; monitoring restored positions only.",
                    flush=True,
                )
                continue

            print(f"\n[{passport.emoji} {passport.name}] Scanning...", flush=True)

            # Save original config
            original_config = self._save_config(passport.config_overrides.keys())

            # Apply passport overrides
            self._apply_overrides(passport.config_overrides)
            self._apply_regime_guardrails(passport)

            skip_days = getattr(config, 'SKIP_WEEKDAYS', [])
            if skip_days and datetime.now().weekday() in skip_days:
                print(
                    f"[{passport.emoji} {passport.name}] Skipping scan — "
                    f"weekday {datetime.now().weekday()} in SKIP_WEEKDAYS {skip_days}",
                    flush=True,
                )
                self._restore_config(original_config)
                continue

            try:
                signals = self.scanner.scan_all()

                for sig in signals:
                    if sig.confidence < config.CONFIDENCE_THRESHOLD:
                        continue

                    if passport.position_manager.can_open(sig):
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
                self.scan_cycle_error_count += 1
                logger.exception(
                    "Scan cycle failed passport=%s enabled=%s btc_trend=%s",
                    passport.name,
                    passport.enabled,
                    self.scanner.btc_trend,
                )
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
                except Exception as e:
                    self.price_fetch_error_count += 1
                    logger.exception(
                        "Failed to fetch current price passport=%s symbol=%s interval=1m",
                        passport.name,
                        sym,
                    )
                    print(
                        f"[PassportRunner] Failed to fetch 1m price for {passport.name}/{sym}: {e}",
                        flush=True,
                    )

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

    def get_status_report(self) -> str:
        """Build an operator-facing state report for Telegram /status."""
        lines = [
            "🟢 **Bot Status**",
            "Actively scanning and monitoring positions.",
            f"State DB: `{self.state_store.db_path}`",
            "Passports:",
        ]
        for p in self.passports:
            status = "enabled" if p.enabled else "disabled"
            lines.append(
                f"  {p.emoji} {p.name}: {status} | Open={p.position_manager.open_count}"
            )

        lines.append(
            "Fault Counters: "
            f"load={self.passport_load_error_count}, "
            f"restore={self.state_restore_error_count}, "
            f"scan={self.scan_cycle_error_count}, "
            f"price={self.price_fetch_error_count}"
        )
        return "\n".join(lines)

    def _save_config(self, override_keys=None) -> Dict:
        """Snapshot current config values."""
        keys = [
            'EMA_FAST', 'EMA_MID', 'EMA_SLOW',
            'CONFIDENCE_THRESHOLD',
            'RSI_LONG_THRESHOLD', 'RSI_SHORT_THRESHOLD',
            'VOLUME_SPIKE_THRESHOLD', 'INDICATOR_WEIGHTS',
            'MAX_OPEN_POSITIONS_PER_PASSPORT', 'MAX_OPEN_POSITIONS_PER_SYMBOL',
            'REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD',
            'REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT',
            'USE_ATR_EXITS', 'USE_TRAILING_STOP', 'ATR_TRAIL_MULTIPLIER',
            'SKIP_WEEKDAYS',
        ]
        if override_keys:
            keys = list(dict.fromkeys([*keys, *override_keys]))
        return {k: getattr(config, k, None) for k in keys}

    def _apply_overrides(self, overrides: Dict):
        """Apply passport config overrides to global config."""
        for k, v in overrides.items():
            setattr(config, k, v)

    def _apply_regime_guardrails(self, passport: Passport):
        """Apply tactical regime clamps for passports that need extra protection."""
        if self.scanner.btc_trend != "Sideways":
            return

        weights = passport.config_overrides.get("INDICATOR_WEIGHTS", {})
        is_reversal = (
            weights.get("REVERSAL_MODE") is True
            or "reversal" in passport.name.lower()
        )
        if not is_reversal:
            return

        config.CONFIDENCE_THRESHOLD = max(
            config.CONFIDENCE_THRESHOLD,
            config.REVERSAL_SIDEWAYS_CONFIDENCE_THRESHOLD,
        )
        config.MAX_OPEN_POSITIONS_PER_PASSPORT = min(
            config.MAX_OPEN_POSITIONS_PER_PASSPORT,
            config.REVERSAL_SIDEWAYS_MAX_OPEN_POSITIONS_PER_PASSPORT,
        )

    def _restore_config(self, original: Dict):
        """Restore original config values."""
        for k, v in original.items():
            if v is not None:
                setattr(config, k, v)
            elif hasattr(config, k):
                delattr(config, k)
