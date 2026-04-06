"""
Multi-Passport Main Entry Point.
Runs all passport strategies simultaneously in paper-trading mode.
Each passport scans independently and sends tagged Telegram signals.
"""
import os
import sys
import time
import argparse
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot import config
from bot.notifier import TelegramNotifier, TelegramCommandPoller
from bot.passport_runner import PassportRunner


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


def format_signal_message(signal, passport) -> str:
    """Format a signal with passport branding for Telegram."""
    direction_emoji = "🟢" if signal.direction == "LONG" else "🔴"

    msg = (
        f"{passport.emoji} **[{passport.name}]**\n"
        f"{direction_emoji} {signal.direction} SIGNAL — {signal.symbol}\n"
        f"\n"
        f"📊 Entry: `{signal.entry_price:.6g}`\n"
        f"🎯 TP1: `{signal.tp1:.6g}` | TP2: `{signal.tp2:.6g}` | TP3: `{signal.tp3:.6g}`\n"
        f"🛑 SL: `{signal.sl:.6g}`\n"
        f"⚡ Lev: {signal.leverage}x | Conf: {signal.confidence}%\n"
        f"📈 BTC: {signal.btc_trend}\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )
    return msg


def format_event_message(event_data) -> str:
    """Format a position event (TP/SL hit) with passport branding."""
    passport = event_data["passport"]
    pos = event_data["position"]
    event = event_data["event"]

    emoji_map = {
        "TP1_HIT": "🎯",
        "TP2_HIT": "🎯🎯",
        "TP3_HIT": "🏆",
        "SL_HIT": "🛑",
        "SL_BREAKEVEN": "⚖️",
    }

    msg = (
        f"{passport.emoji} **[{passport.name}]**\n"
        f"{emoji_map.get(event, '📢')} {event} — {pos.signal.symbol}\n"
        f"P&L: ${pos.realized_pnl:+.2f} | Equity: ${passport.equity:,.0f}"
    )
    return msg


def run_multi_passport(tg_token: str = None, tg_chat: str = None,
                       interval: str = "1h"):
    """Main loop for multi-passport paper trading."""
    print("=" * 60, flush=True)
    print("🏛️  CRYPTOPASS MULTI-PASSPORT RUNNER", flush=True)
    print("=" * 60, flush=True)

    # Setup
    passports_root = os.path.join(
        os.path.dirname(__file__), "..", "passports"
    )
    passports_root = os.path.abspath(passports_root)

    runner = PassportRunner(passports_root, interval=interval)
    tg_group = (os.environ.get("CRYPTOPASS_TG_GROUP_ID") or "").strip() or None
    tg_topic = (os.environ.get("CRYPTOPASS_TG_TRADE_TOPIC_ID") or "").strip() or None
    tg_log_topic = (os.environ.get("CRYPTOPASS_TG_LOG_TOPIC_ID") or "").strip() or None
    notifier = TelegramNotifier(bot_token=tg_token, chat_id=tg_chat,
                                group_id=tg_group, trade_topic_id=tg_topic,
                                log_topic_id=tg_log_topic)
    notifier.restore_message_ids(runner.state_store)

    # Start telegram polling thread
    poller = TelegramCommandPoller(notifier, runner)
    poller.start()

    # Scan interval based on timeframe
    scan_interval_sec = 60 * 60  # 1h default
    if interval == "15m":
        scan_interval_sec = 15 * 60
    elif interval == "4h":
        scan_interval_sec = 4 * 60 * 60

    print(f"\nInterval: {interval} | Scan every: {scan_interval_sec}s", flush=True)
    print(f"Passport dir: {passports_root}", flush=True)
    print(f"Telegram: {'enabled' if tg_token else 'disabled'}\n", flush=True)

    # Initial scan
    runner.scanner.refresh_symbols()
    last_scan_time = 0

    try:
        while True:
            now = time.time()

            # 1. Update positions for ALL passports
            events = runner.update_all_positions()
            for event_data in events:
                event_msg = format_event_message(event_data)
                print(event_msg, flush=True)
                if tg_token:
                    passport = event_data["passport"]
                    pos = event_data["position"]
                    event = event_data["event"]
                    # For partial closes (TP1/TP2), passport.equity hasn't been updated
                    # yet — add cumulative realized_pnl to show correct current equity.
                    if event in ("TP1_HIT", "TP2_HIT"):
                        equity_display = passport.equity + pos.realized_pnl
                    else:
                        equity_display = passport.equity
                    notifier.send_tp_sl_alert(
                        signal=pos.signal,
                        event=event,
                        realized_pnl=pos.realized_pnl,
                        equity=equity_display,
                        passport_name=passport.name,
                        display_name=f"{passport.emoji} [{passport.name}]",
                    )

            # 2. Run full scan cycle on schedule
            if now - last_scan_time >= scan_interval_sec:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                      f"Running multi-passport scan...", flush=True)

                results = runner.run_scan_cycle()

                for result in results:
                    sig = result["signal"]
                    passport = result["passport"]
                    pos = result["position"]
                    sig_msg = format_signal_message(sig, passport)
                    print(sig_msg, flush=True)
                    if tg_token:
                        msg_id = notifier.send_signal(sig, passport_name=passport.name, passport_emoji=passport.emoji)
                        notifier.store_signal_message_id(sig.symbol, msg_id, passport.name)
                        if msg_id and pos.pos_id:
                            runner.state_store.update_position(pos.pos_id, tg_msg_id=msg_id)

                # Print summary
                summary = runner.get_summary()
                print(summary, flush=True)

                # Snapshot equity with last-seen prices for accurate unrealized PnL
                runner.snapshot_equity_all(runner._last_prices)

                last_scan_time = now

            # Sleep briefly
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n[Multi] Gracefully shutting down...", flush=True)
        print(runner.get_summary(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cryptopass Multi-Passport Runner")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--tg-token", default=None, help="Telegram Bot Token")
    parser.add_argument("--tg-chat", default=None, help="Telegram Chat ID")

    args = parser.parse_args()
    tg_token, tg_chat = resolve_telegram_credentials(args.tg_token, args.tg_chat)
    run_multi_passport(tg_token, tg_chat, args.interval)
