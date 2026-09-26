from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import threading
import time
import pandas as pd
import requests
import ta

# ==========================================
# 1. إعدادات بوت التلجرام وبينانس
# ==========================================
TELEGRAM_BOT_TOKEN = "8617483405:AAGhNHH1A3X1twjDUU5fwdWr6rUYKMhc9gc"
TELEGRAM_CHAT_ID = "7895743860"

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"خطأ في التيليجرام: {e}")

TIMEFRAME = "1h"
last_signal_times = {}

# قائمة عملات احتياطية صلبة ومضمونة لتجنب أي تعليق في جلب الـ API الخارجي
BACKUP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT"
]

def get_binance_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        # استخدام timeout قصير جداً لمنع تعليق البوت نهائياً
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, list):
            return None
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close'] = df['close'].astype(float)
        return df
    except Exception:
        return None

def run_bot():
    print("🚀 تم بدء تنفيذ دالة التداول بنجاح.")
    try:
        send_telegram_alert("🤖 *تم تشغيل البوت بنجاح وبدأ مراقبة السوق!*")
    except Exception:
        pass

    while True:
        print("🔄 [دورة جديدة] بدء فحص العملات...")
        for symbol in BACKUP_SYMBOLS:
            try:
                df = get_binance_klines(symbol, TIMEFRAME, limit=100)
                if df is None or len(df) < 30:
                    continue
                    
                curr_price = df['close'].iloc[-2]
                current_candle_time = df['timestamp'].iloc[-2]

                # حساب مؤشر الماكد
                macd_object = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
                df["macd"] = macd_object.macd()
                df["signal"] = macd_object.macd_signal()

                prev_macd = df["macd"].iloc[-3]
                prev_signal = df["signal"].iloc[-3]
                curr_macd = df["macd"].iloc[-2]
                curr_signal = df["signal"].iloc[-2]

                signal_type = None
                if prev_macd <= prev_signal and curr_macd > curr_signal:
                    signal_type = "BUY"
                elif prev_macd >= prev_signal and curr_macd < curr_signal:
                    signal_type = "SELL"

                if signal_type and last_signal_times.get(symbol) != current_candle_time:
                    last_signal_times[symbol] = current_candle_time
                    
                    distance = curr_price * 0.015
                    if signal_type == "BUY":
                        sl = curr_price - distance
                        tp = curr_price + (distance * 2)
                    else:
                        sl = curr_price + distance
                        tp = curr_price - (distance * 2)

                    msg = f"🚨 *إشارة دخول جديدة ({signal_type})*\n🪙 العملة: `{symbol}`\n⏱ الفريم: `{TIMEFRAME}`\n💰 سعر الدخول: `{curr_price}`\n🎯 الهدف (TP): `{tp:.4f}`\n🛑 وقف الخسارة (SL): `{sl:.4f}`\n⚖️ نسبة المخاطر والعائد: 1:2"
                    send_telegram_alert(msg)
                    print(f"✨ تم إرسال إشارة للعملة: {symbol} [{signal_type}]")
            except Exception as e:
                print(f"خطأ في تحليل العملة {symbol}: {e}")
            
            time.sleep(1)

        print("💤 انتهت الدورة الحالية، انتظار دقيقتين للدورة القادمة...")
        time.sleep(120)

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        return

if __name__ == "__main__":
    print("🌐 تشغيل الخادم السحابي وخيط البوت...")
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()
