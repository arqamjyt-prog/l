#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import aiohttp
import re
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread
import logging
import time

# إعداد التسجيل للأخطاء
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Telethon API ---
api_id = 33981047
api_hash = "e08732b52ada5ec02e5ae44e76e1461a"

# --- Bot API ---
BOT_TOKEN = "8261995856:AAHwJK1L-iiD9TsZCKJqpAThlzvhAvADBwk"
SEND_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
DELETE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"

# --- Groups ---
SOURCE_GROUP = "https://t.me/+PThwytZf7Ec5Mjg0"
TARGET_CHAT_ID = -1003757848848  # رقم القناة/الدردشة الصحيحة

# --- إعدادات عرض الرقم ---
DIGITS_TO_SHOW = 6  

# --- إعدادات Render ---
PORT = int(os.environ.get('PORT', 5000))

# --- تحديد مسار الجلسة بشكل صحيح ---
# Render يستخدم نظام ملفات مؤقت، لذلك نحتاج للتأكد من المسار
SESSION_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(SESSION_DIR, "session")
logger.info(f"مسار الجلسة: {SESSION_PATH}")

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
    try:
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
                logger.info(f"تم إرسال الرسالة بنجاح: {message_id}")

        await asyncio.sleep(600)  # 10 دقائق

        async with aiohttp.ClientSession() as session:
            await session.post(
                DELETE_URL,
                data={
                    "chat_id": TARGET_CHAT_ID,
                    "message_id": message_id
                }
            )
        logger.info(f"تم حذف الرسالة: {message_id}")
    except Exception as e:
        logger.error(f"خطأ في send_and_delete: {e}")

# --- دالة استخراج الرقم ---
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

# --- دالة استخراج الكود ---
def extract_code(msg, text):
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
    
    return "Unknown"

# --- دالة للتحقق من وجود الجلسة ---
def check_session_files():
    """التحقق من وجود ملفات الجلسة"""
    session_file = f"{SESSION_PATH}.session"
    if os.path.exists(session_file):
        logger.info(f"✅ تم العثور على ملف الجلسة: {session_file}")
        return True
    else:
        logger.error(f"❌ لم يتم العثور على ملف الجلسة: {session_file}")
        # عرض جميع الملفات في المجلد للمساعدة في التصحيح
        files = os.listdir(SESSION_DIR)
        logger.info(f"الملفات الموجودة: {files}")
        return False

# --- الوظيفة الرئيسية ---
async def main():
    # التحقق من وجود الجلسة أولاً
    if not check_session_files():
        logger.error("لا يمكن المتابعة بدون ملف الجلسة")
        return

    # إنشاء العميل مع المسار الصحيح
    client = TelegramClient(SESSION_PATH, api_id, api_hash)
    
    try:
        # محاولة الاتصال
        await client.connect()
        
        # التحقق من تسجيل الدخول
        if await client.is_user_authorized():
            logger.info("✅ تم تسجيل الدخول بنجاح باستخدام الجلسة الموجودة")
            me = await client.get_me()
            logger.info(f"✅ تم تسجيل الدخول كـ: {me.first_name} (ID: {me.id})")
        else:
            logger.error("❌ الجلسة غير صالحة أو منتهية الصلاحية")
            return
            
        # الحصول على المجموعة المصدر
        try:
            source = await client.get_entity(SOURCE_GROUP)
            logger.info(f"✅ تم الاتصال بالمجموعة المصدر: {SOURCE_GROUP}")
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بالمجموعة المصدر: {e}")
            return

        # إعداد معالج الأحداث
        @client.on(events.NewMessage(chats=source))
        async def handler(event):
            try:
                msg = event.message
                if not msg.message:
                    return

                logger.info("📩 تم استلام رسالة جديدة من المجموعة")
                text = msg.message.strip()

                # تنظيف النص
                first_line = text.splitlines()[0].strip() if text else ""
                country_only = first_line.split("#")[0].strip() if first_line else "Unknown"

                server_name = "Unknown"
                if "#" in first_line:
                    parts = first_line.split("#")
                    if len(parts) > 1:
                        server_parts = parts[1].split()
                        if server_parts:
                            server_name = server_parts[0].strip()

                display_number = extract_phone_number(text, DIGITS_TO_SHOW)
                code = extract_code(msg, text)

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

                logger.info(f"معالجة الرسالة: {country_only} - {display_number}")
                asyncio.create_task(send_and_delete(final_text))
                
            except Exception as e:
                logger.error(f"خطأ في معالج الأحداث: {e}")

        logger.info("✅ البوت يعمل بنجاح على Render")
        logger.info(f"🟢 في انتظار الرسائل من {SOURCE_GROUP}")
        
        # البقاء متصلاً
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل البوت: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()

# --- تشغيل البوت مع Flask ---
if __name__ == "__main__":
    # تشغيل Flask في خيط منفصل
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info(f"🚀 Flask server بدأ على المنفذ {PORT}")
    
    # تشغيل البوت في حلقة لا نهائية مع إعادة التشغيل عند الفشل
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("تم إيقاف البوت يدوياً")
            break
        except Exception as e:
            logger.error(f"حدث خطأ وسيتم إعادة التشغيل بعد 10 ثواني: {e}")
            time.sleep(10)
            continue
