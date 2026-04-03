"""Fetch sample messages from Pumpradar Free Signal Telegram group."""
import asyncio
import json
from telethon import TelegramClient

from scripts.telethon_settings import load_telethon_settings

GROUP_NAME = "Pumpradar Free Signal"


async def main():
    api_id, api_hash, session_name = load_telethon_settings()
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()
    
    print("Connected! Searching for group...")
    
    # Find the group
    target = None
    async for dialog in client.iter_dialogs():
        if GROUP_NAME.lower() in dialog.name.lower():
            target = dialog
            print(f"Found: {dialog.name} (id: {dialog.id})")
            break
    
    if not target:
        # Try searching by username
        print(f"Group '{GROUP_NAME}' not found in dialogs. Listing all dialogs...")
        async for dialog in client.iter_dialogs():
            if "pump" in dialog.name.lower() or "radar" in dialog.name.lower() or "signal" in dialog.name.lower():
                print(f"  Potential match: {dialog.name} (id: {dialog.id})")
                target = dialog
        
        if not target:
            print("No matching group found. Here are your recent dialogs:")
            count = 0
            async for dialog in client.iter_dialogs():
                print(f"  - {dialog.name} (id: {dialog.id})")
                count += 1
                if count > 30:
                    break
            await client.disconnect()
            return
    
    # Fetch last 50 messages
    print(f"\nFetching last 50 messages from '{target.name}'...\n")
    messages = []
    async for msg in client.iter_messages(target, limit=50):
        msg_data = {
            "id": msg.id,
            "date": str(msg.date),
            "text": msg.text or "",
            "from_id": str(msg.sender_id) if msg.sender_id else None,
        }
        messages.append(msg_data)
        
        # Print each message
        print(f"--- Message {msg.id} ({msg.date}) ---")
        print(msg.text or "[no text / media only]")
        print()
    
    # Save to JSON for analysis
    with open("sample_messages.json", "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved {len(messages)} messages to sample_messages.json")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
