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

def fetch_top_usdt_symbols():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        symbols = []
        for s in data.get('symbols', []):
            if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT':
                symbol_name = s['symbol']
                if not any(stable in symbol_name for stable in ['USDC', 'FDUSD', 'TUSD', 'USDP', 'BUSD']):
                    symbols.append(symbol_name)
        result = symbols[:50]
        print(f"✅ تم بنجاح جلب {len(result)} عملة من بينانس.")
        return result
    except Exception as e:
        print(f"❌ فشل جلب العملات من بينانس بسبب الخطأ: {e}، سيتم استخدام القائمة الاحتياطية.")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

SYMBOLS = fetch_top_usdt_symbols()
TIMEFRAME = "1h"

# قاموس لتسجيل وقت آخر إشارة لكل عملة لمنع التكرار
last_signal_times = {}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"خطأ في التيليجرام: {e}")

def get_binance_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
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
    except Exception as e:
        print(f"❌ خطأ جلب شموع العملة {symbol}: {e}")
        return None

def analyze_market():
    print(f"🔍 جاري فحص السوق لـ {len(SYMBOLS)} عملة والبحث عن إشارات جديدة...")
    for symbol in SYMBOLS:
        try:
            df = get_binance_klines(symbol, TIMEFRAME, limit=100)
            if df is None or len(df) < 30:
                print(f"⚠️ تخطي العملة {symbol} لعدم توفر بيانات كافية.")
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

            # إذا وجدت إشارة جديدة لشمعة جديدة، أرسلها فوراً
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

def run_bot():
    print(f"🚀 بدأ تشغيل بوت الماكد بنجاح، مراقبة {len(SYMBOLS)} عملة...")
    try:
        send_telegram_alert("🤖 *تم تشغيل بوت التداول بنجاح وبدون توقف!*")
    except:
        pass
    
    while True:
        try:
            analyze_market()
        except Exception as e:
            print(f"خطأ عام: {e}")
        
        print("💤 انتظار الدورة القادمة...")
        time.sleep(120) # فحص السوق كل دقيقتين

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        return

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()
