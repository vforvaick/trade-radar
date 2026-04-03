import sys
import os

# Ensure bot can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from bot.notifier import TelegramNotifier
from bot.signals import Signal

class MockNotifier(TelegramNotifier):
    def __init__(self):
        super().__init__(bot_token="fake", chat_id="fake")
        self.sent_messages = []
        
    def _send(self, text: str, reply_to_message_id: int = None):
        print("\n" + "="*50)
        print("TELEGRAM MESSAGE PREVIEW")
        print("="*50)
        print(text)
        print("="*50 + "\n")
        self.sent_messages.append(text)

def run_tests():
    n = MockNotifier()
    
    # Create sample signal
    sig = Signal(
        symbol='BTCUSDT', 
        direction='LONG', 
        entry_price=50000.0, 
        tp1=52000.0, 
        tp2=54000.0, 
        tp3=56000.0, 
        sl=49000.0, 
        leverage=7, 
        risk_reward=2.08, 
        confidence=75.0, 
        btc_trend='Uptrend'
    )
    
    print("Testing TP1_HIT...")
    n.send_tp_sl_alert(sig, 'TP1_HIT', realized_pnl=350.0, equity=1350.0, passport_name="📊 [Aggressive]")
    
    print("Testing SL_BREAKEVEN...")
    n.send_tp_sl_alert(sig, 'SL_BREAKEVEN', realized_pnl=0.0, equity=1350.0, passport_name="📊 [Aggressive]")
    
    print("Testing TP3_HIT...")
    n.send_tp_sl_alert(sig, 'TP3_HIT', realized_pnl=50.0, equity=1400.0, passport_name="📊 [Aggressive]")
    
    print("Testing SL_HIT...")
    n.send_tp_sl_alert(sig, 'SL_HIT', realized_pnl=-150.0, equity=850.0, passport_name="🛡️ [Conservative]")

if __name__ == "__main__":
    run_tests()
