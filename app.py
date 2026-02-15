#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import re
from telethon import TelegramClient, events
from flask import Flask
import threading
import os
import logging
import sys
import datetime

# إعداد التسجيل
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
DIGITS_TO_SHOW = 6  

# --- إنشاء تطبيق Flask للخادم ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running! Last message time: " + str(getattr(home, 'last_time', 'Never'))

@app.route('/health')
def health():
    return "OK", 200

@app.route('/status')
def status():
    return {
        'status': 'running',
        'last_message': str(getattr(home, 'last_time', 'Never')),
        'target_chat': TARGET_CHAT_ID,
        'source_group': SOURCE_GROUP
    }

# --- إرسال وحذف بعد 10 دقائق ---
async def send_and_delete(text):
    try:
        logger.info(f"Sending message to {TARGET_CHAT_ID}")
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
                logger.info(f"Message sent successfully, ID: {message_id}")

        await asyncio.sleep(600)  # 10 دقائق

        async with aiohttp.ClientSession() as session:
            await session.post(
                DELETE_URL,
                data={
                    "chat_id": TARGET_CHAT_ID,
                    "message_id": message_id
                }
            )
        logger.info(f"Message {message_id} deleted after 10 minutes")
    except Exception as e:
        logger.error(f"Error in send_and_delete: {e}")

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
                            logger.info(f"Start command received from {chat_id}")
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
        r'Code:?\s*(\d+)',
        r'كود:?\s*(\d+)',
        r'([Cc]ode)[:\s]*(\d+)',
        r'([Kk]od)[:\s]*(\d+)',
        r'is[:\s]*(\d+)',
        r'\b(\d{4,8})\b'
    ]
    
    for pattern in code_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            for group in match.groups():
                if group and str(group).isdigit():
                    return str(group)
    
    return "Unknown"

# --- تشغيل خادم Flask في thread منفصل ---
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# --- الدالة الرئيسية ---
async def main():
    try:
        # تشغيل Flask في thread منفصل
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("🌐 Flask server started on port " + os.environ.get("PORT", "5000"))
        
        # تشغيل معالج أوامر البوت
        asyncio.create_task(handle_start_command())
        
        # إنشاء جلسة Telethon
        client = TelegramClient("session", api_id, api_hash)
        await client.start()
        
        # التحقق من الاتصال
        me = await client.get_me()
        logger.info(f"✅ Bot connected as: {me.username or me.first_name}")
        
        # الاتصال بالمصدر
        try:
            source = await client.get_entity(SOURCE_GROUP)
            logger.info(f"✅ Connected to source group: {SOURCE_GROUP}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to source: {e}")
            logger.info("Trying to join group first...")
            try:
                await client.join_chat(SOURCE_GROUP)
                source = await client.get_entity(SOURCE_GROUP)
                logger.info(f"✅ Joined and connected to source group")
            except Exception as e2:
                logger.error(f"❌ Failed to join group: {e2}")
                return
        
        @client.on(events.NewMessage(chats=source))
        async def handler(event):
            try:
                msg = event.message
                if not msg.message:
                    return
                
                text = msg.message.strip()
                logger.info(f"📩 New message received: {text[:100]}...")
                
                # تنظيف النص
                first_line = text.splitlines()[0].strip() if text else ""
                country_only = first_line.split("#")[0].strip() if first_line else "Unknown"
                
                # اسم السيرفر
                server_name = "Unknown"
                if "#" in first_line:
                    parts = first_line.split("#")[1].split()
                    server_name = parts[0].strip() if parts else "Unknown"
                
                # استخراج الرقم
                display_number = extract_phone_number(text, DIGITS_TO_SHOW)
                
                # استخراج الكود
                code = extract_code(msg, text)
                
                # تنسيق الرسالة
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
                
                logger.info(f"Formatted message prepared")
                
                # تحديث وقت آخر رسالة
                home.last_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # إرسال الرسالة
                asyncio.create_task(send_and_delete(final_text))
                
            except Exception as e:
                logger.error(f"Error in message handler: {e}")
        
        logger.info("🟢 Bot is now listening for messages...")
        logger.info(f"📱 Showing last {DIGITS_TO_SHOW} digits of phone number")
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"❌ Main error: {e}")
        sys.exit(1)

# --- نقطة الدخول الرئيسية ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
