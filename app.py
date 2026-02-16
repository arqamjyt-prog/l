#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
import aiohttp
import re
import threading
import time
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread

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

# --- إعدادات Render ---
PORT = int(os.environ.get('PORT', 5000))
SESSION_NAME = "session"

# --- إعداد Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

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
            except:
                await asyncio.sleep(1)

# --- دالة استخراج الرقم المحسنة ---
def extract_phone_number(text, digits_to_show=6):
    # البحث عن أنماط الأرقام المختلفة
    patterns = [
        r'[\+\d]+\d{4,}',  # أرقام تبدأ بـ + أو أرقام
        r'\d{4,}',          # أرقام متتالية من 4 أرقام فأكثر
        r'X\d{4,}',         # أرقام تبدأ بـ X
        r'\b\d{1,10}\b'     # أي رقم من 1 إلى 10 أرقام
    ]
    
    full_number = "Unknown"
    
    # محاولة العثور على رقم
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            # اختيار أطول رقم (غالباً هو الرقم الكامل)
            full_number = max(matches, key=len)
            break
    
    # إذا لم يتم العثور على رقم
    if full_number == "Unknown":
        return "Unknown"
    
    # إزالة أي رموز غير مرغوب فيها
    full_number = re.sub(r'[^\dX\+]', '', full_number)
    
    # إذا كان الرقم فارغاً بعد التنظيف
    if not full_number:
        return "Unknown"
    
    # عرض الرقم حسب الطول المطلوب
    if len(full_number) > digits_to_show:
        return "..." + full_number[-digits_to_show:]
    else:
        return full_number

# --- دالة استخراج الكود ---
def extract_code(msg, text):
    try:
        if msg.reply_markup:
            for row in msg.reply_markup.rows:
                for b in row.buttons:
                    if hasattr(b, "text") and b.text.strip().isdigit():
                        return b.text.strip()
        
        code_patterns = [
            r'Code:?\s*(\d+)',
            r'كود:?\s*(\d+)',
            r'\b(\d{4,6})\b'
        ]
        
        for pattern in code_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
    except:
        pass
    
    return "Unknown"

# --- Main Telethon client ---
async def main():
    asyncio.create_task(handle_start_command())

    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    
    try:
        await client.start()
    except:
        return
    
    try:
        source = await client.get_entity(SOURCE_GROUP)
    except:
        return

    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        try:
            msg = event.message
            if not msg.message:
                return

            text = msg.message.strip()

            first_line = text.splitlines()[0].strip() if text else ""
            country_with_flag = first_line.split()[0].strip() if first_line else "Unknown"

            country_code = "Unknown"
            if "#" in first_line:
                country_part = first_line.split("#")[1].strip()
                country_code = country_part.split()[0].strip() if country_part else "Unknown"

            server_name = "Unknown"
            if "#" in first_line:
                parts = first_line.split("#")
                if len(parts) > 1:
                    after_hash = parts[1].strip().split()
                    if len(after_hash) >= 2:
                        server_name = after_hash[1]
                    elif len(after_hash) == 1:
                        potential = after_hash[0]
                        if len(potential) == 2 and potential not in ["YE", "BO", "US", "UK", "SA", "AE"]:
                            server_name = potential

            display_number = extract_phone_number(text, DIGITS_TO_SHOW)
            code = extract_code(msg, text)

            final_text = (
                "📩 *NEW MESSAGE*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"{country_with_flag} *Country:* `{country_code}`\n\n"
                f"📱 *Number:*.... `{display_number}`\n\n"
                f"🔐 *Code:* `{code}`\n\n"
                f"🖥️ *Server:* `{server_name}`\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⏳ _This message will be deleted automatically after 10 minutes._"
            )

            asyncio.create_task(send_and_delete(final_text))
        except:
            pass

    # --- [إضافة فقط] حذف إشعارات الانضمام والمغادرة فور ظهورها ---
    @client.on(events.ChatAction(chats=TARGET_CHAT_ID))
    async def delete_join_leave(event):
        try:
            if (
                event.user_joined
                or event.user_left
                or event.user_added
                or event.user_kicked
            ):
                if event.action_message:
                    await client.delete_messages(
                        event.chat_id,
                        event.action_message.id
                    )
        except:
            pass
    # --- نهاية الإضافة ---

    await client.run_until_disconnected()

# --- دالة لتشغيل البوت في خيط منفصل ---
def run_bot_in_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        try:
            loop.run_until_complete(main())
        except:
            time.sleep(10)
            continue
        time.sleep(5)

# --- متغير لتتبع حالة البوت ---
bot_started = False

# --- نقطة الدخول الرئيسية - متوافقة مع gunicorn ---
if __name__ != "__main__":
    if not bot_started:
        bot_thread = Thread(target=run_bot_in_thread, daemon=True)
        bot_thread.start()
        bot_started = True

# --- Start ---
if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    run_bot_in_thread()
