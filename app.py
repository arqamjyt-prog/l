#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import re
import os
from aiohttp import web
from telethon import TelegramClient, events

# --- Telethon API ---
api_id = 33981047
api_hash = "e08732b52ada5ec02e5ae44e76e1461a"

# --- Bot API ---
BOT_TOKEN = "8261995856:AAHwJK1L-iiD9TsZCKJqpAThlzvhAvADBwk"
SEND_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
DELETE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
GET_UPDATES_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

# --- Groups ---
SOURCE_GROUP = "https://t.me/+PThwytZf7Ec5Mjg0"
TARGET_CHAT_ID = -1003757848848

# --- إعدادات عرض الرقم ---
DIGITS_TO_SHOW = 6  

# --- إرسال وحذف بعد 10 دقائق ---
async def send_and_delete(text):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            SEND_URL,
            data={
                "chat_id": TARGET_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown"
            }
        ) as resp:
            data = await resp.json()
            if not data.get("ok"):
                print("Send failed:", data)
                return
            message_id = data["result"]["message_id"]

    await asyncio.sleep(600)

    async with aiohttp.ClientSession() as session:
        await session.post(
            DELETE_URL,
            data={
                "chat_id": TARGET_CHAT_ID,
                "message_id": message_id
            }
        )

# --- الاستماع لأوامر البوت (/start) ---
async def handle_start_command():
    offset = 0
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(GET_UPDATES_URL, params={"offset": offset, "timeout": 30}) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        await asyncio.sleep(1)
                        continue

                    for update in data["result"]:
                        offset = update["update_id"] + 1
                        msg = update.get("message")
                        if not msg:
                            continue
                        text = msg.get("text", "")
                        chat_id = msg["chat"]["id"]

                        if text == "/start":
                            await session.post(
                                SEND_URL,
                                data={"chat_id": chat_id, "text": "Hi\n@sms_free2bot"}
                            )
            except Exception as e:
                print("Error in start command handler:", e)
                await asyncio.sleep(1)

# --- استخراج الرقم ---
def extract_phone_number(text, digits_to_show=6):
    patterns = [
        r'[\+\d]+\d{8,}',
        r'\d{8,}',
        r'X\d{5,}',
        r'\d{5,}'
    ]

    full_number = "Unknown"

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            full_number = match.group()
            break

    if full_number == "Unknown":
        return "Unknown"

    if digits_to_show == 0:
        return full_number

    if len(full_number) > digits_to_show:
        return "..." + full_number[-digits_to_show:]
    else:
        return full_number

# --- استخراج الكود ---
def extract_code(msg, text):
    if msg.reply_markup:
        for row in msg.reply_markup.rows:
            for b in row.buttons:
                if hasattr(b, "text") and b.text.strip().isdigit():
                    return b.text.strip()

    patterns = [
        r'Code:?\s*(\d+)',
        r'كود:?\s*(\d+)',
        r'\b(\d{4,6})\b'
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)

    return "Unknown"

# --- Web Server (Render requirement) ---
async def web_server():
    async def root(request):
        return web.json_response({"status": "ok", "service": "telegram-listener"})

    async def health(request):
        return web.Response(text="healthy")

    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"🌐 Web server running on port {port}")

# --- Main Telethon client ---
async def main():
    asyncio.create_task(handle_start_command())
    asyncio.create_task(web_server())

    client = TelegramClient("session", api_id, api_hash)
    await client.start()
    source = await client.get_entity(SOURCE_GROUP)

    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        msg = event.message
        if not msg.message:
            return

        text = msg.message.strip()

        first_line = text.splitlines()[0].strip() if text else ""
        country_only = first_line.split("#")[0].strip() if first_line else "Unknown"

        server_name = "Unknown"
        if "#" in first_line:
            server_name = first_line.split("#")[1].split()[0].strip()

        display_number = extract_phone_number(text, DIGITS_TO_SHOW)
        code = extract_code(msg, text)

        final_text = (
            "📩 *NEW MESSAGE*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🌍 *Country:* `{country_only}`\n\n"
            f"📱 *Number:* `{display_number}`\n\n"
            f"🔐 *Code:* `{code}`\n\n"
            f"🖥️ *Server:* `{server_name}`\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏳ _This message will be deleted automatically after 10 minutes._"
        )

        asyncio.create_task(send_and_delete(final_text))

    print("🟢 Render service started successfully")
    await client.run_until_disconnected()

# --- Start ---
asyncio.run(main())
