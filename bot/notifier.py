"""
Telegram notifier module for trade alerts and command polling.
"""
import inspect
import logging
import requests
import threading
import time
from bot.signals import Signal


logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None,
                 group_id: str = None, topic_id: str = None):
        self.bot_token = bot_token
        self.chat_id = chat_id            # DM chat — system logs/errors
        self.group_id = group_id          # Trade group chat ID
        self.topic_id = topic_id          # message_thread_id for trade topic
        self.enabled = bool(bot_token and chat_id)
        self.group_enabled = bool(bot_token and group_id)
        self.send_error_count = 0
        # Maps (symbol, passport_name) -> message_id for reply threading
        self.signal_message_ids: dict[tuple[str, str], int] = {}
        
    def restore_message_ids(self, state_store):
        """Restore active message IDs from the database."""
        if self.enabled and state_store:
            self.signal_message_ids = state_store.load_active_message_ids()
            print(f"[Notifier] Restored {len(self.signal_message_ids)} active signal message threads", flush=True)
        
    def _send(
        self,
        text: str,
        reply_to_message_id: int = None,
        symbol: str = None,
        passport_name: str = None,
        event: str = None,
    ) -> int | None:
        """Send a message and return the message_id, or None on failure."""
        if not self.enabled:
            return None
            
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
            payload["allow_sending_without_reply"] = True
        try:
            resp = requests.post(url, json=payload, timeout=5)
            data = resp.json()
            if data.get("ok"):
                return data["result"]["message_id"]
            self.send_error_count += 1
            logger.warning(
                "Telegram API rejected message chat_id=%s reply_to_message_id=%s symbol=%s passport=%s event=%s response=%s",
                self.chat_id,
                reply_to_message_id,
                symbol,
                passport_name,
                event,
                data,
            )
        except Exception as e:
            self.send_error_count += 1
            logger.exception(
                "Failed to send Telegram message chat_id=%s reply_to_message_id=%s symbol=%s passport=%s event=%s",
                self.chat_id,
                reply_to_message_id,
                symbol,
                passport_name,
                event,
            )
            print(f"[Notifier] Failed to send TG message: {e}")
        return None

    def send_signal(self, signal: Signal):
        """Format and send a new trade signal alert."""
        emoji = "🟢 LONG" if signal.direction == "LONG" else "🔴 SHORT"
        
        msg = f"🚀 **Pumpradar Replica Signal** 🚀\n\n"
        msg += f"**Symbol:** #{signal.symbol}\n"
        msg += f"**Direction:** {emoji}\n"
        msg += f"**Entry:** `{signal.entry_price}`\n\n"
        
        msg += f"📊 **Context:**\n"
        msg += f"BTC Trend: {signal.btc_trend}\n"
        msg += f"Risk/Reward: 1:{signal.risk_reward}\n"
        msg += f"Leverage: **{signal.leverage}x**\n\n"
        
        msg += f"🎯 **Targets:**\n"
        msg += f"TP1: `{signal.tp1}`\n"
        msg += f"TP2: `{signal.tp2}`\n"
        msg += f"TP3: `{signal.tp3}`\n\n"
        
        msg += f"🛑 **Stop Loss:** `{signal.sl}`\n\n"
        
        msg += f"🤖 **AI Confluence:** {signal.confidence}%\n"
        
        print(f"[Notifier] Sending signal alert for {signal.symbol}")
        msg_id = self._send_to_group(msg, symbol=signal.symbol)
        return msg_id

    def send_update(self, msg: str):
        """Send a general update or TP/SL hit alert."""
        print(f"[Notifier] {msg}")
        self._send(f"🔔 **Bot Update:**\n{msg}")

    def store_signal_message_id(self, symbol: str, message_id: int, passport_name: str = None):
        """Store the message_id of a setup signal for reply threading."""
        if message_id:
            key = (symbol, passport_name or "")
            self.signal_message_ids[key] = message_id

    def send_tp_sl_alert(
        self,
        signal: Signal,
        event: str,
        realized_pnl: float,
        equity: float,
        passport_name: str = None,
        display_name: str = None,
    ):
        """Format and send a rich TP/SL hit alert."""
        emoji_map = {
            "TP1_HIT": "🎯",
            "TP2_HIT": "🎯🎯",
            "TP3_HIT": "🏆",
            "SL_HIT": "🛑",
            "SL_BREAKEVEN": "⚖️",
        }
        
        event_emoji = emoji_map.get(event, "📢")
        direction_emoji = "🟢" if signal.direction == "LONG" else "🔴"
        
        prefix = display_name or passport_name or "🚀 **Pumpradar Replica**"
        
        msg = f"{prefix}\n\n"
        msg += f"{event_emoji} **{event.replace('_', ' ')}** — #{signal.symbol}\n"
        msg += f"Direction: {direction_emoji} {signal.direction}\n"
        msg += f"Entry: `{signal.entry_price:.6g}`\n"
        
        if "TP" in event:
            if event == "TP1_HIT":
                target_price = signal.tp1
                msg += f"Hit Price: `{target_price:.6g}`\n"
                msg += f"Closed: 70% of position\n"
                msg += f"Action: SL moved to Breakeven\n"
            elif event == "TP2_HIT":
                target_price = signal.tp2
                msg += f"Hit Price: `{target_price:.6g}`\n"
                msg += f"Closed: 20% of position\n"
            else: # TP3
                target_price = signal.tp3
                msg += f"Hit Price: `{target_price:.6g}`\n"
                msg += f"Closed: 10% of position (All targets hit!)\n"
                
            dist_pct = abs(target_price - signal.entry_price) / signal.entry_price * 100
            msg += f"Profit: +{dist_pct:.2f}%\n"
            
        elif event == "SL_HIT":
            msg += f"Hit Price: `{signal.sl:.6g}`\n"
            dist_pct = abs(signal.sl - signal.entry_price) / signal.entry_price * 100
            msg += f"Loss: -{dist_pct:.2f}%\n"
            
        elif event == "SL_BREAKEVEN":
            msg += f"Hit Price: `{signal.entry_price:.6g}` (Breakeven)\n"
            msg += f"Note: Prior TP profits secured.\n"
            
        msg += f"\n"
        pnl_symbol = "+" if realized_pnl > 0 else ""
        msg += f"**Realized P&L:** `${pnl_symbol}{realized_pnl:.2f}`\n"
        msg += f"**Bot Equity:** `${equity:,.2f}`\n"
        
        # Reply to the original setup signal message
        key = (signal.symbol, passport_name or "")
        reply_to = self.signal_message_ids.get(key)
        
        print(f"[Notifier] Sending {event} alert for {signal.symbol}" + (f" (reply to #{reply_to})" if reply_to else ""))
        self._send_to_group(
            msg,
            reply_to_message_id=reply_to,
            symbol=signal.symbol,
            passport_name=passport_name,
            event=event,
        )

    def _send_to_group(
        self,
        text: str,
        reply_to_message_id: int = None,
        symbol: str = None,
        passport_name: str = None,
        event: str = None,
    ) -> int | None:
        """Send a message to the trade group topic. Falls back to DM if group not configured."""
        if not self.bot_token:
            return None

        # Fall back to DM if group not configured
        if not self.group_enabled:
            return self._send_with_context(text, reply_to_message_id=reply_to_message_id,
                                           symbol=symbol, passport_name=passport_name, event=event)

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.group_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if self.topic_id:
            payload["message_thread_id"] = int(self.topic_id)
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
            payload["allow_sending_without_reply"] = True

        try:
            resp = requests.post(url, json=payload, timeout=5)
            data = resp.json()
            if data.get("ok"):
                return data["result"]["message_id"]
            self.send_error_count += 1
            logger.warning(
                "Telegram group API rejected message group_id=%s topic_id=%s symbol=%s event=%s response=%s",
                self.group_id, self.topic_id, symbol, event, data,
            )
        except Exception as e:
            self.send_error_count += 1
            logger.exception(
                "Failed to send Telegram group message group_id=%s topic_id=%s symbol=%s event=%s",
                self.group_id, self.topic_id, symbol, event,
            )
            print(f"[Notifier] Failed to send TG group message: {e}")
        return None

    def _send_with_context(
        self,
        text: str,
        reply_to_message_id: int = None,
        symbol: str = None,
        passport_name: str = None,
        event: str = None,
    ) -> int | None:
        """Call _send with optional context while preserving old subclass overrides."""
        signature = inspect.signature(self._send)
        params = signature.parameters
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in params.values()
        )

        kwargs = {}
        for key, value in {
            "reply_to_message_id": reply_to_message_id,
            "symbol": symbol,
            "passport_name": passport_name,
            "event": event,
        }.items():
            if accepts_kwargs or key in params:
                kwargs[key] = value

        return self._send(text, **kwargs)


class TelegramCommandPoller:
    """Background thread that listens to Telegram commands."""
    
    def __init__(self, notifier: TelegramNotifier, passport_runner):
        self.notifier = notifier
        self.runner = passport_runner
        self.poll_error_count = 0
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        
    def start(self):
        if self.notifier.enabled:
            print("[TelegramPoller] Starting background command listener...", flush=True)
            self.thread.start()
            
    def _poll_loop(self):
        last_update_id = 0
        start_time = time.time()
        while True:
            try:
                url = f"https://api.telegram.org/bot{self.notifier.bot_token}/getUpdates"
                params = {"offset": last_update_id + 1, "timeout": 30}
                # Use longer timeout for long-polling
                resp = requests.get(url, params=params, timeout=40).json()
                
                if resp.get("ok") and resp.get("result"):
                    for update in resp["result"]:
                        last_update_id = update["update_id"]
                        msg = update.get("message", {})
                        text = msg.get("text", "")
                        chat_id = msg.get("chat", {}).get("id")
                        msg_date = msg.get("date", 0)
                        
                        # Only respond to new messages from authorized chat
                        if msg_date > start_time and str(chat_id) == str(self.notifier.chat_id) and text:
                            cmd = text.split()[0].lower()
                            if cmd == "/summary" or cmd == "/stats":
                                print("[TelegramPoller] Received /summary command", flush=True)
                                summary = self.runner.get_summary()
                                self.notifier._send(f"{summary}")
                            elif cmd == "/status":
                                if hasattr(self.runner, "get_status_report"):
                                    status = self.runner.get_status_report()
                                else:
                                    status = "🟢 **Bot Status**\nActively scanning and monitoring positions."
                                self.notifier._send(status)
                            elif cmd == "/ping":
                                self.notifier._send("🏓 Pong! Bot is alive and well.")
                                
            except Exception as e:
                self.poll_error_count += 1
                logger.exception(
                    "Failed to poll Telegram commands chat_id=%s last_update_id=%s",
                    self.notifier.chat_id,
                    last_update_id,
                )
                print(f"[TelegramPoller] Failed to poll Telegram commands: {e}", flush=True)
                
            time.sleep(2)
