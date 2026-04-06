#!/usr/bin/env python3
"""
Utility: Find Telegram group_id and topic_id (message_thread_id).

Usage:
  1. Invite your bot to the Trader Zone group
  2. Send any message in the Tradar: Trade Radar topic
  3. Run: CRYPTOPASS_TG_TOKEN=your-token python scripts/get_telegram_ids.py

Output: list of recent chats with their IDs and topic IDs.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests

token = os.environ.get("CRYPTOPASS_TG_TOKEN", "").strip()
if not token:
    print("ERROR: Set CRYPTOPASS_TG_TOKEN env var first")
    sys.exit(1)

resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"limit": 50}, timeout=10).json()

if not resp.get("ok"):
    print("ERROR:", resp)
    sys.exit(1)

seen = {}
for upd in resp.get("result", []):
    msg = upd.get("message") or upd.get("channel_post") or {}
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    chat_title = chat.get("title") or chat.get("username") or "DM"
    chat_type = chat.get("type", "unknown")
    thread_id = msg.get("message_thread_id")
    if chat_id and chat_id not in seen:
        seen[chat_id] = {"title": chat_title, "type": chat_type, "thread_ids": set()}
    if chat_id and thread_id:
        seen[chat_id]["thread_ids"].add(thread_id)

print("\n=== Telegram Chats Found ===\n")
for cid, info in seen.items():
    print(f"  Title: {info['title']}")
    print(f"  Type:  {info['type']}")
    print(f"  Chat ID: {cid}  ← set as CRYPTOPASS_TG_GROUP_ID for groups")
    if info["thread_ids"]:
        for tid in info["thread_ids"]:
            print(f"  Topic ID (message_thread_id): {tid}  ← set as CRYPTOPASS_TG_TRADE_TOPIC_ID")
    print()

print("If your group is not listed, send a message in the topic first, then re-run.")
