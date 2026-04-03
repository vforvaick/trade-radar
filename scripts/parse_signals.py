import json
import re
import pandas as pd
from datetime import datetime

# Load all messages
with open("all_messages.json", "r", encoding="utf-8") as f:
    messages = json.load(f)

# Sort messages oldest first to simulate timeline
messages.sort(key=lambda x: str(x["date"]))

parsed_signals = []
active_trades = {}

def parse_number(text, regex_pattern):
    match = re.search(regex_pattern, text)
    return float(match.group(1).replace(",", "")) if match else None

for msg in messages:
    text = msg["text"]
    date = msg["date"]
    
    # 1. Parse Signals (Entry)
    if "SIGNAL DETECTED" in text:
        direction = "LONG" if "LONG" in text else "SHORT"
        
        symbol_match = re.search(r"\*\*Symbol:\*\* #([A-Z0-9]+)", text)
        if not symbol_match:
            continue
        symbol = symbol_match.group(1)
        
        entry = parse_number(text, r"\*\*Entry:\*\* `([\d.]+)`")
        tp1 = parse_number(text, r"TP1: `([\d.]+)`")
        tp2 = parse_number(text, r"TP2: `([\d.]+)`")
        tp3 = parse_number(text, r"TP3: `([\d.]+)`")
        sl = parse_number(text, r"\*\*Stop Loss:\*\* `([\d.]+)`")
        
        rr_match = re.search(r"Risk/Reward: ([\d.]+:\d+\.?\d*)", text)
        rr = rr_match.group(1) if rr_match else None
        
        lev_match = re.search(r"Rec\. Leverage: \*\*(\d+)x\*\*", text)
        lev = int(lev_match.group(1)) if lev_match else None
        
        btc_match = re.search(r"BTC Trend: (\w+)", text)
        btc = btc_match.group(1) if btc_match else None
        
        conf_match = re.search(r"GO Confidence: (\d+)%", text)
        conf = int(conf_match.group(1)) if conf_match else None
        
        insight_match = re.search(r"Confidence: \d+%(.*?)\(Action: GO\)", text, re.DOTALL)
        insight = insight_match.group(1).strip() if insight_match else None
        
        trade = {
            "signal_id": msg["id"],
            "date_signal": date,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "tp1_target": tp1,
            "tp2_target": tp2,
            "tp3_target": tp3,
            "sl_target": sl,
            "leverage": lev,
            "risk_reward": rr,
            "confidence_pct": conf,
            "btc_trend": btc,
            "ai_insight": insight,
            # Outcomes
            "status": "OPEN",
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "sl_hit": False,
            "tp1_date": None,
            "tp2_date": None,
            "tp3_date": None,
            "sl_date": None,
            "tp1_profit_pct": None,
            "tp2_profit_pct": None,
            "tp3_profit_pct": None,
            "sl_loss_pct": None,
        }
        
        # We index by symbol to match outcomes later
        active_trades[symbol] = trade
        parsed_signals.append(trade)

    # 2. Parse Outcomes (TP/SL)
    elif "TP1 DONE" in text or "TP2 SMASHED" in text or "TP3 JACKPOT" in text or "SL HIT" in text:
        symbol_match = re.search(r"\*\*Symbol:\*\* #\d+ (?:LONG|SHORT) ([A-Z0-9]+)", text)
        if not symbol_match:
            # Maybe shorter format without number
            symbol_match = re.search(r"\*\*Symbol:\*\* #([A-Z0-9]+)", text)
            
        if not symbol_match:
            continue
            
        symbol = symbol_match.group(1)
        
        # Only process if we have the entry signal for it
        if symbol not in active_trades:
            continue
            
        trade = active_trades[symbol]
        
        profit_match = re.search(r"Profit:\*\* `\+?([\d.]+)%`", text)
        loss_match = re.search(r"Loss:\*\* `-([\d.]+)%`", text)
        
        if "TP1 DONE" in text:
            trade["tp1_hit"] = True
            trade["tp1_date"] = date
            trade["status"] = "TP1"
            if profit_match:
                trade["tp1_profit_pct"] = float(profit_match.group(1))
                
        elif "TP2 SMASHED" in text:
            trade["tp2_hit"] = True
            trade["tp2_date"] = date
            trade["status"] = "TP2"
            if profit_match:
                trade["tp2_profit_pct"] = float(profit_match.group(1))
                
        elif "TP3 JACKPOT" in text:
            trade["tp3_hit"] = True
            trade["tp3_date"] = date
            trade["status"] = "TP3_CLOSED"
            if profit_match:
                trade["tp3_profit_pct"] = float(profit_match.group(1))
            # Trade is fully closed
            if symbol in active_trades:
                del active_trades[symbol]
                
        elif "SL HIT" in text:
            trade["sl_hit"] = True
            trade["sl_date"] = date
            trade["status"] = "SL_CLOSED"
            if loss_match:
                trade["sl_loss_pct"] = float(loss_match.group(1))
            # Trade is fully closed
            if symbol in active_trades:
                del active_trades[symbol]

# Convert to DataFrame
df = pd.DataFrame(parsed_signals)

# Save to CSV
df.to_csv("trade_ledger.csv", index=False)
print(f"Parsed {len(df)} signals into trade_ledger.csv")
print(df["status"].value_counts())
