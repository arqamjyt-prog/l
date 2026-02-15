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
import logging

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
GET_UPDATES_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

# --- Groups ---
SOURCE_GROUP = "https://t.me/+PThwytZf7Ec5Mjg0"
TARGET_CHAT_ID = -1003757848848  # رقم القناة/الدردشة الصحيحة

# --- إعدادات عرض الرقم ---
# غير هذا الرقم: 1,2,3,4,5,6,7,8,9,10 أو 0 للرقم كاملاً
DIGITS_TO_SHOW = 6  

# --- إعدادات Render ---
PORT = int(os.environ.get('PORT', 5000))
SESSION_NAME = "session"  # اسم ملف الجلسة الموجود (session.session)

# --- إعداد Flask للتأكد أن Render يعرف أن الخدمة تعمل ---
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

# --- دالة استخراج اسم السيرفر من النص ---
def extract_server_name(text):
    """
    استخراج اسم السيرفر من النص بذكاء
    """
    # تقسيم النص إلى سطور
    lines = text.split('\n')
    first_line = lines[0].strip() if lines else ""
    
    # البحث عن اسم السيرفر في أول سطر
    server_name = "Unknown"
    
    # النمط: شيء مثل #YE WS أو #YE WS something
    if "#" in first_line:
        parts = first_line.split("#")
        if len(parts) > 1:
            after_hash = parts[1].strip()
            # تقسيم ما بعد الـ #
            hash_parts = after_hash.split()
            
            if len(hash_parts) >= 2:
                # إذا كان هناك جزئين أو أكثر، الثاني غالباً هو السيرفر
                # مثال: #YE WS -> hash_parts = ["YE", "WS"] -> server = "WS"
                # مثال: #YE WS TEXT -> hash_parts = ["YE", "WS", "TEXT"] -> server = "WS"
                server_name = hash_parts[1]
            elif len(hash_parts) == 1:
                # إذا كان جزء واحد فقط، تحقق إذا كان ليس رمز دولة
                # مثال: #WS -> هذا قد يكون السيرفر مباشرة
                potential = hash_parts[0]
                # إذا كان مكون من حرفين فقط، قد يكون دولة وليس سيرفر
                if len(potential) == 2 and potential.isalpha() and potential.isupper():
                    # هذا غالباً رمز دولة، ابحث في باقي النص
                    server_name = find_server_in_rest(text)
                else:
                    server_name = potential
    
    # إذا لم نجد في أول سطر، ابحث في باقي النص
    if server_name == "Unknown":
        server_name = find_server_in_rest(text)
    
    return server_name

def find_server_in_rest(text):
    """
    البحث عن اسم السيرفر في بقية النص
    """
    # قائمة بأسماء السيرفرات المعروفة (يمكن إضافة المزيد)
    known_servers = ["WS", "VK", "FB", "IG", "TW", "TB", "LI", "SC", "WA", "TG", "AP", "GP"]
    
    # البحث في النص كله
    for server in known_servers:
        if re.search(rf'\b{server}\b', text):
            return server
    
    # البحث عن أي كلمة كبيرة مكونة من حرفين أو أكثر
    # نتجنب الكلمات التي هي أرقام فقط
    words = re.findall(r'\b[A-Z]{2,}\b', text)
    for word in words:
        # تجاهل الكلمات المكونة من حرفين فقط إذا كانت في قائمة رموز الدول
        if len(word) == 2 and word in ["YE", "BO", "US", "UK", "SA", "AE", "EG", "IQ", "SY", "JO", "PS", "LB"]:
            continue
        # إذا كانت الكلمة كبيرة وأطول من حرفين، أو موجودة في القائمة
        if len(word) > 2 or word in known_servers:
            return word
    
    # البحث عن أي مجموعة من الحروف والأرقام
    alnum_patterns = re.findall(r'\b[A-Z0-9]{3,}\b', text)
    for pattern in alnum_patterns:
        # تجاهل إذا كان رقماً فقط
        if not pattern.isdigit():
            return pattern
    
    return "Unknown"

# --- Main Telethon client ---
async def main():
    # شغّل listener البوت أولاً
    asyncio.create_task(handle_start_command())

    # استخدام الجلسة الموجودة بدون إنشاء جديدة
    # Telethon سيبحث تلقائياً عن ملف session.session في نفس المجلد
    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    
    try:
        # محاولة بدء الجلسة الموجودة
        await client.start()
        logger.info("تم استخدام الجلسة الموجودة بنجاح")
    except Exception as e:
        logger.error(f"فشل في استخدام الجلسة الموجودة: {e}")
        logger.info("تأكد من وجود ملف session.session في نفس المجلد")
        raise e
    
    source = await client.get_entity(SOURCE_GROUP)

    @client.on(events.NewMessage(chats=source))
    async def handler(event):
        msg = event.message
        if not msg.message:
            return

        text = msg.message.strip()

        # --- تنظيف النص واستخراج البيانات ---
        first_line = text.splitlines()[0].strip() if text else ""
        
        # استخراج الدولة
        country_code = "Unknown"
        if "#" in first_line:
            # استخراج الكود بعد # (مثل YE من #YE)
            country_part = first_line.split("#")[1].strip()
            country_code = country_part.split()[0].strip() if country_part else "Unknown"
        else:
            # إذا لم يكن هناك #، خذ أول كلمة
            country_code = first_line.split()[0].strip() if first_line else "Unknown"
            # تنظيف رمز العلم إذا وجد
            country_code = re.sub(r'[^\w]', '', country_code)

        # استخراج اسم السيرفر باستخدام الدالة الجديدة
        server_name = extract_server_name(text)

        # استخراج الرقم مع إمكانية التحكم بعدد الأرقام المعروضة
        display_number = extract_phone_number(text, DIGITS_TO_SHOW)

        # استخراج الكود
        code = extract_code(msg, text)

        # --- تنسيق الرسالة ---
        final_text = (
            "📩 *NEW MESSAGE*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🌍 *Country:* `{country_code}`\n\n"
            f"📱 *Number:*.... `{display_number}`\n\n"
            f"🔐 *Code:* `{code}`\n\n"
            f"🖥️ *Server:* `{server_name}`\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏳ _This message will be deleted automatically after 10 minutes._"
        )

        asyncio.create_task(send_and_delete(final_text))
        logger.info(f"تم إرسال رسالة جديدة: الدولة {country_code} - السيرفر {server_name} - الرقم {display_number}")

    logger.info("🟢 Running: capture ALL messages + clean format + auto delete (10 minutes) + /start handler")
    logger.info(f"📱 Showing last {DIGITS_TO_SHOW} digits of phone number")
    await client.run_until_disconnected()

# --- دالة لتشغيل البوت في خيط منفصل مع حلقة أحداث خاصة ---
def run_bot_in_thread():
    """تشغيل البوت في خيط مع حلقة أحداث خاصة"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        try:
            loop.run_until_complete(main())
        except Exception as e:
            logger.error(f"حدث خطأ في البوت: {e}")
            time.sleep(10)
            continue
        time.sleep(5)

# --- متغير لتتبع حالة البوت ---
bot_started = False

# --- نقطة الدخول الرئيسية - متوافقة مع gunicorn ---
if __name__ != "__main__":
    # هذا الجزء يعمل عندما يستخدم gunicorn
    if not bot_started:
        bot_thread = Thread(target=run_bot_in_thread, daemon=True)
        bot_thread.start()
        bot_started = True
        logger.info("✅ تم تشغيل البوت في الخلفية مع gunicorn")

# --- Start ---
if __name__ == "__main__":
    # تشغيل Flask في خيط منفصل
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # تشغيل البوت
    run_bot_in_thread()
