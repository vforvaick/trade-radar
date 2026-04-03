"""Fetch deeper history (500 messages) from Pumpradar Free Signal for statistical analysis."""
import asyncio
import json
from telethon import TelegramClient

API_ID = 19524776
API_HASH = "efa9bf74c8c1d961314310df2eda1130"
SESSION_NAME = "pumpradar_session"
GROUP_NAME = "Pumpradar Free Signal"

async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    
    target = None
    async for dialog in client.iter_dialogs():
        if GROUP_NAME.lower() in dialog.name.lower():
            target = dialog
            break
    
    if not target:
        print("Group not found!")
        await client.disconnect()
        return
    
    print(f"Fetching all messages from '{target.name}'...")
    messages = []
    async for msg in client.iter_messages(target, limit=500):
        msg_data = {
            "id": msg.id,
            "date": str(msg.date),
            "text": msg.text or "",
        }
        messages.append(msg_data)
    
    with open("all_messages.json", "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(messages)} messages to all_messages.json")
    
    # Quick categorization
    signals = [m for m in messages if "SIGNAL DETECTED" in m["text"]]
    tp1 = [m for m in messages if "TP1 DONE" in m["text"]]
    tp2 = [m for m in messages if "TP2 SMASHED" in m["text"]]
    tp3 = [m for m in messages if "TP3 JACKPOT" in m["text"]]
    sl = [m for m in messages if "SL HIT" in m["text"]]
    anomaly = [m for m in messages if "ANOMALY DETECTED" in m["text"]]
    market = [m for m in messages if m["text"].startswith("BTC:") or "Update Pasar" in m["text"]]
    
    print(f"\n=== STATS ===")
    print(f"Total messages: {len(messages)}")
    print(f"Signals: {len(signals)}")
    print(f"  LONG: {len([s for s in signals if 'LONG' in s['text']])}")
    print(f"  SHORT: {len([s for s in signals if 'SHORT' in s['text']])}")
    print(f"TP1 hit: {len(tp1)}")
    print(f"TP2 hit: {len(tp2)}")
    print(f"TP3 hit: {len(tp3)}")
    print(f"SL hit: {len(sl)}")
    print(f"BTC Anomaly alerts: {len(anomaly)}")
    print(f"Market updates: {len(market)}")
    
    # Extract R:R ratios and leverage from signals
    import re
    rr_ratios = []
    leverages = []
    confidences = []
    btc_trends = []
    
    for s in signals:
        text = s["text"]
        
        rr = re.search(r"Risk/Reward: (\d+:\d+\.?\d*)", text)
        if rr:
            rr_ratios.append(rr.group(1))
        
        lev = re.search(r"Rec\. Leverage: \*\*(\d+)x\*\*", text)
        if lev:
            leverages.append(int(lev.group(1)))
        
        conf = re.search(r"GO Confidence: (\d+)%", text)
        if conf:
            confidences.append(int(conf.group(1)))
        
        btc = re.search(r"BTC Trend: (\w+)", text)
        if btc:
            btc_trends.append(btc.group(1))
    
    print(f"\n=== SIGNAL DETAILS ===")
    if rr_ratios:
        from collections import Counter
        print(f"R:R ratios: {dict(Counter(rr_ratios))}")
    if leverages:
        print(f"Leverage range: {min(leverages)}x - {max(leverages)}x, avg: {sum(leverages)/len(leverages):.1f}x")
    if confidences:
        print(f"Confidence range: {min(confidences)}% - {max(confidences)}%, avg: {sum(confidences)/len(confidences):.1f}%")
    if btc_trends:
        from collections import Counter
        print(f"BTC Trends: {dict(Counter(btc_trends))}")
    
    # Win/loss analysis  
    total_resolved = len(tp1) + len(sl)  # TP1 = at least partial win, SL = loss
    if total_resolved > 0:
        win_rate = len(tp1) / total_resolved * 100
        print(f"\n=== WIN RATE (TP1 hit vs SL hit) ===")
        print(f"Wins (TP1+): {len(tp1)}")
        print(f"Losses (SL): {len(sl)}")
        print(f"Win rate: {win_rate:.1f}%")
    
    # Extract profit/loss percentages
    profits = []
    losses = []
    for m in tp1 + tp2 + tp3:
        pct = re.search(r"Profit:\*\* `\+?([\d.]+)%`", m["text"])
        if pct:
            profits.append(float(pct.group(1)))
    for m in sl:
        pct = re.search(r"Loss:\*\* `-([\d.]+)%`", m["text"])
        if pct:
            losses.append(float(pct.group(1)))
    
    if profits:
        print(f"\n=== PROFIT/LOSS ===")
        print(f"Avg profit on TP1: {sum([p for p in profits[:len(tp1)]])/max(len(tp1),1):.2f}%")
        print(f"All profits: {profits}")
    if losses:
        print(f"Avg loss on SL: {sum(losses)/len(losses):.2f}%")
        print(f"All losses: {losses}")
    
    # Duration analysis
    durations_win = []
    durations_loss = []
    for m in tp1:
        dur = re.search(r"Duration:\*\* (\d+)h\s*(\d+)m", m["text"])
        if dur:
            durations_win.append(int(dur.group(1)) * 60 + int(dur.group(2)))
    for m in sl:
        dur = re.search(r"Duration:\*\* (\d+)h\s*(\d+)m", m["text"])
        if dur:
            durations_loss.append(int(dur.group(1)) * 60 + int(dur.group(2)))
    
    if durations_win:
        print(f"\n=== DURATION ===")
        print(f"Avg duration to TP1: {sum(durations_win)/len(durations_win)/60:.1f}h")
    if durations_loss:
        print(f"Avg duration to SL: {sum(durations_loss)/len(durations_loss)/60:.1f}h")
    
    # Date range
    if messages:
        print(f"\n=== DATE RANGE ===")
        print(f"Oldest: {messages[-1]['date']}")
        print(f"Newest: {messages[0]['date']}")
    
    await client.disconnect()

asyncio.run(main())
