#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import re
import os
from telethon import TelegramClient, events
from flask import Flask
import threading
import logging

# إعداد التسجيل (logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
TARGET_CHAT_ID = -1003757848848  # رقم القناة/الدردشة الصحيحة

# --- إعدادات عرض الرقم ---
# غير هذا الرقم: 1,2,3,4,5,6,7,8,9,10 أو 0 للرقم كاملاً
DIGITS_TO_SHOW = 6  

# --- إعدادات Render ---
PORT = int(os.environ.get('PORT', 8080))
HOST = '0.0.0.0'

# --- إنشاء تطبيق Flask للخادم ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return "Healthy", 200

def run_flask():
    """تشغيل خادم Flask"""
    app.run(host=HOST, port=PORT)

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
                logger.error(f"Send failed: {data}")
                return
            message_id = data["result"]["message_id"]

    await asyncio.sleep(600)  # 10 دقائق

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
                logger.error(f"Error in start command handler: {e}")
                await asyncio.sleep(1)

# --- دالة استخراج الرقم مع خيارات عرض مرنة ---
def extract_phone_number(text, digits_to_show=6):
    """
    استخراج رقم الهاتف وعرض آخر digits_to_Show أرقام
    digits_to_show: 1-10 أو 0 لعرض الرقم كاملاً
    """
    # أنماط مختلفة للأرقام
    patterns = [
        r'[\+\d]+\d{8,}',  # أرقام بطول 8+ (مع +)
        r'\d{8,}',          # أرقام بطول 8+ (بدون +)
        r'X\d{5,}',         # نمط X متبوعاً بأرقام
        r'\d{5,}'           # أي 5 أرقام أو أكثر
    ]
    
    full_number = "Unknown"
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            full_number = match.group()
            break
    
    if full_number == "Unknown":
        return "Unknown"
    
    # إذا digits_to_show = 0، اعرض الرقم كاملاً
    if digits_to_show == 0:
        return full_number
    
    # عرض آخر digits_to_Show أرقام
    if len(full_number) > digits_to_show:
        return "..." + full_number[-digits_to_show:]
    else:
        return full_number

# --- دالة استخراج الكود من الأزرار أو النص ---
def extract_code(msg, text):
    # البحث في الأزرار أولاً
    if msg.reply_markup:
        for row in msg.reply_markup.rows:
            for b in row.buttons:
                if hasattr(b, "text") and b.text.strip().isdigit():
                    return b.text.strip()
    
    # إذا لم نجد في الأزرار، ابحث في النص
    code_patterns = [
        r'Code:?\s*(\d+)',     # Code: 12345
        r'كود:?\s*(\d+)',       # كود: 12345
        r'\b(\d{4,6})\b'        # أي 4-6 أرقام منفصلة
    ]
    
    for pattern in code_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return "Unknown"

# --- Main Telethon client ---
async def main():
    # شغّل listener البوت أولاً
    asyncio.create_task(handle_start_command())

    # إنشاء مجلد session إذا لم يكن موجوداً
    if not os.path.exists('sessions'):
        os.makedirs('sessions')

    client = TelegramClient("sessions/session", api_id, api_hash)
    await client.start()
    source = await client.get_entity(SOURCE_GROUP)
    logger.info(f"Connected to source group: {SOURCE_GROUP}")

    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        msg = event.message
        if not msg.message:
            return

        text = msg.message.strip()

        # --- تنظيف النص ---
        first_line = text.splitlines()[0].strip() if text else ""
        country_only = first_line.split("#")[0].strip() if first_line else "Unknown"

        # اسم السيرفر بدون #
        server_name = "Unknown"
        if "#" in first_line:
            server_name = first_line.split("#")[1].split()[0].strip()

        # استخراج الرقم مع إمكانية التحكم بعدد الأرقام المعروضة
        # استخدام DIGITS_TO_SHOW من الإعدادات العامة
        display_number = extract_phone_number(text, DIGITS_TO_SHOW)

        # استخراج الكود
        code = extract_code(msg, text)

        # --- تنسيق الرسالة ---
        final_text = (
            "📩 *NEW MESSAGE*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🌍 *Country:* `{country_only}`\n\n"
            f"📱 *Number:*.... `{display_number}`\n\n"
            f"🔐 *Code:* `{code}`\n\n"
            f"🖥️ *Server:* `{server_name}`\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏳ _This message will be deleted automatically after 10 minutes._"
        )

        asyncio.create_task(send_and_delete(final_text))
        logger.info(f"Message processed: {country_only} - {display_number}")

    logger.info("🟢 Running: capture ALL messages + clean format + auto delete (10 minutes) + /start handler")
    logger.info(f"📱 Showing last {DIGITS_TO_SHOW} digits of phone number")
    await client.run_until_disconnected()

# --- Start ---
if __name__ == "__main__":
    # تشغيل خادم Flask في thread منفصل
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask server started on port {PORT}")
    
    # تشغيل البوت
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error in main: {e}")
