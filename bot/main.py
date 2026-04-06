"""
Main entry point for Pumpradar Replication Bot.
Runs the continuous scanning and position management loop.
"""
import argparse
import os
import time
from datetime import datetime

import pandas as pd

from bot import config
from bot.scanner import Scanner
from bot.executor import PaperExecutor, LiveExecutor
from bot.notifier import TelegramNotifier
from bot.position_manager import PositionManager
from bot.data_fetcher import fetch_klines


def resolve_telegram_credentials(tg_token: str = None, tg_chat: str = None) -> tuple[str, str]:
    """Resolve Telegram credentials from CLI overrides or the environment."""
    token = (tg_token or os.environ.get("CRYPTOPASS_TG_TOKEN") or "").strip() or None
    chat = (tg_chat or os.environ.get("CRYPTOPASS_TG_CHAT") or "").strip() or None
    if token is None and chat is None:
        return None, None
    if token is None or chat is None:
        raise SystemExit(
            "Missing Telegram credentials. Set CRYPTOPASS_TG_TOKEN and CRYPTOPASS_TG_CHAT "
            "or pass --tg-token and --tg-chat, or omit both to disable Telegram."
        )
    return token, chat


def run_bot(mode: str, interval: str = "1h", tg_token: str = None, tg_chat: str = None):
    print(f"\n🚀 Starting Pumpradar Replication Bot")
    print(f"Mode: {mode.upper()}")
    print(f"Interval: {interval}\n")

    scanner = Scanner(interval=interval, limit=100)
    notifier = TelegramNotifier(bot_token=tg_token, chat_id=tg_chat)
    position_manager = PositionManager()
    
    if mode == "live":
        print("⚠️ WARNING: Live trading enabled.")
        executor = LiveExecutor(api_key="...", api_secret="...")
    else:
        print("ℹ️ Paper trading enabled. No real trades will be executed.")
        executor = PaperExecutor()

    # Initial setup
    scanner.refresh_symbols()
    scanner.update_btc_trend()
    
    # State tracking
    last_scan_time = 0
    scan_interval_sec = 60 * 60  # default 1 hour, depends on timeframe
    if interval == "15m":
        scan_interval_sec = 15 * 60
    elif interval == "4h":
        scan_interval_sec = 4 * 60 * 60
        
    equity = config.INITIAL_EQUITY
    print(f"Initial Simulated Equity: ${equity:,.2f}\n")

    try:
        while True:
            now = time.time()
            
            # 1. Update Open Positions (Monitor SL/TP)
            # In a real bot, we'd use WebSockets for this. Here we poll.
            if position_manager.open_count > 0:
                _update_positions(position_manager, equity, executor, notifier)

            # 2. Daily Maintenance
            # Refresh symbol list and BTC trend occasionally
            if int(now) % 86400 < 60:
                scanner.refresh_symbols()
                
            # 3. Main Indicator Scan (run at candle close)
            # Simplification: run on schedule based on interval
            if now - last_scan_time >= scan_interval_sec:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running full market scan...")
                scanner.update_btc_trend()
                signals = scanner.scan_all()
                
                for sig in signals:
                    if position_manager.can_open(sig):
                        # Execute trade
                        success = executor.execute_signal(sig, equity)
                        if success:
                            # Register with position manager
                            position_manager.open_position(sig, equity)
                            # Notify and store message_id for reply threading
                            msg_id = notifier.send_signal(sig)
                            notifier.store_signal_message_id(sig.symbol, msg_id)
                    else:
                        print(
                            f"[Main] Ignored {sig.symbol} - blocked by position guardrail "
                            f"(passport cap or same-symbol cap)."
                        )
                
                last_scan_time = now

            # Sleep briefly
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n[Main] Gracefully shutting down...")
        print("Final Stats:")
        print(position_manager.get_stats())


def _update_positions(pm: PositionManager, initial_equity: float, executor, notifier: TelegramNotifier):
    """Fetch current prices for open positions and check TP/SL."""
    current_prices = {}
    for pos in pm.positions:
        sym = pos.signal.symbol
        try:
            # Fetch latest 1m candle to get current price bounds
            df = fetch_klines(sym, "1m", limit=1, use_cache=False)
            if not df.empty:
                current_prices[sym] = (df.iloc[0]['high'], df.iloc[0]['low'], df.iloc[0]['close'])
        except Exception:
            pass
            
    events = pm.update_positions(current_prices)
    for pos, event in events:
        msg = f"Position Event: {pos.signal.symbol} -> {event}"
        print(f"[Main] {msg}")
        
        # Calculate current equity (closed P&L + in-flight partial P&L)
        open_pnl = sum(p.realized_pnl for p in pm.positions)
        current_equity = initial_equity + pm.get_total_pnl() + open_pnl
        notifier.send_tp_sl_alert(pos.signal, event, pos.realized_pnl, current_equity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pumpradar Replica Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--tg-token", default=None, help="Telegram Bot Token")
    parser.add_argument("--tg-chat", default=None, help="Telegram Chat ID")
    
    args = parser.parse_args()
    tg_token, tg_chat = resolve_telegram_credentials(args.tg_token, args.tg_chat)
    run_bot(args.mode, args.interval, tg_token, tg_chat)
