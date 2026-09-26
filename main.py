from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import threading
import time
import pandas as pd
import requests

# ==========================================
# 1. إعدادات التلجرام وبينانس
# ==========================================
TELEGRAM_BOT_TOKEN = "8617483405:AAGhNHH1A3X1twjDUU5fwdWr6rUYKMhc9gc"
TELEGRAM_CHAT_ID = "7895743860"

# قائمة أبرز العملات للتجربة السريعة
SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "DOGEUSDT",
    "DOTUSDT",
    "LINKUSDT",
]

TIMEFRAMES = ["15m", "1h"]
last_signals = {tf: {symbol: None for symbol in SYMBOLS} for tf in TIMEFRAMES}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, data=payload, timeout=10)
        print("✅ تم إرسال التنبيه إلى تيليجرام بنجاح.")
    except Exception as e:
        print(f"❌ خطأ في إرسال التلجرام: {e}")

def get_binance_klines(symbol, interval, limit=50):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if not isinstance(data, list):
            return None
        df = pd.DataFrame(
            data,
            columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_av", "trades", "tb_base_av", "tb_quote_av", "ignore"
            ],
        )
        df["close"] = df["close"].astype(float)
        df["open"] = df["open"].astype(float)
        return df
    except Exception:
        return None

def analyze_symbol(symbol, timeframe):
    global last_signals
    try:
        print(f"🔍 جاري فحص العملة: {symbol} على الفريم: {timeframe}...")
        df = get_binance_klines(symbol, timeframe, limit=50)
        if df is None or len(df) < 10:
            return

        curr_price = df["close"].iloc[-1]
        prev_price = df["close"].iloc[-2]

        # تحديد اتجاه السعر بناءً على الشمعة الحالية والسابقة
        signal_type = "BUY" if curr_price > prev_price else "SELL"

        # إرسال إشارة إذا تغير الاتجاه مقارنة بالفحص السابق
        if last_signals[timeframe].get(symbol) != signal_type:
            last_signals[timeframe][symbol] = signal_type

            distance = curr_price * 0.01
            if signal_type == "BUY":
                sl = curr_price - distance
                tp = curr_price + (distance * 2)
            else:
                sl = curr_price + distance
                tp = curr_price - (distance * 2)

            msg = (
                f"🚨 *إشارة سريعة {signal_type} [فريم {timeframe}]*\n"
                f"🪙 العملة: `{symbol}`\n"
                f"💰 سعر الدخول: `{curr_price}`\n"
                f"🎯 الهدف: `{tp:.4f}`\n"
                f"🛑 وقف الخسارة: `{sl:.4f}`"
            )
            send_telegram_alert(msg)
            print(f"🚀 تم إرسال صفقة {signal_type} للعملة {symbol} على فريم {timeframe}")

    except Exception as e:
        print(f"خطأ في تحليل العملة {symbol}: {e}")

def run_timeframe_bot(timeframe):
    print(f"🚀 بدأ تشغيل مراقبة الفريم: {timeframe}")
    while True:
        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                for symbol in SYMBOLS:
                    executor.submit(analyze_symbol, symbol, timeframe)
        except Exception as e:
            print(f"❌ خطأ في حلقة الفريم {timeframe}: {e}")

        time.sleep(30)  # فحص سريع كل 30 ثانية

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Fast Signal Bot is running successfully!")

if __name__ == "__main__":
    send_telegram_alert("🤖 *تم تشغيل بوت الإشارات السريعة بنجاح* \nسيتم إرسال الصفقات فوراً مع أول تحديث للسوق.")

    for tf in TIMEFRAMES:
        t = threading.Thread(target=run_timeframe_bot, args=(tf,))
        t.daemon = True
        t.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()
