FROM python:3.9-slim

WORKDIR /app

# تثبيت الاعتماديات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الملفات
COPY . .

# التأكد من وجود ملف الجلسة
RUN ls -la

# تشغيل البوت مباشرة بدون gunicorn
CMD ["python", "app.py"]
