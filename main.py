from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import os
import threading
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import requests
import ta

# ==========================================
# 1. إعدادات التلجرام وبينانس
# ==========================================
TELEGRAM_BOT_TOKEN = "8617483405:AAGhNHH1A3X1twjDUU5fwdWr6rUYKMhc9gc"
TELEGRAM_CHAT_ID = "7895743860"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "POLUSDT", "LTCUSDT", "NEARUSDT", "APTUSDT",
    "TRXUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "FILUSDT",
    "ICPUSDT", "ARBUSDT", "SUIUSDT", "OPUSDT", "INJUSDT"
]

TIMEFRAME = "1h"
MAX_OPEN_TRADES = 25

active_trades = {}
last_signals = {symbol: None for symbol in SYMBOLS}
closed_trades_history = []

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        print(f"Telegram response: {response.text}")
    except Exception as e:
        print(f"❌ خطأ في إرسال التلجرام: {e}")

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
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        return df
    except Exception:
        return None

def analyze_symbol(symbol):
    global active_trades
    df = get_binance_klines(symbol, TIMEFRAME)
    if df is None or len(df) < 30:
        return
    curr_price = df['close'].iloc[-2]
    if symbol in active_trades:
        return
    if len(active_trades) >= MAX_OPEN_TRADES:
        return

    macd_object = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd_object.macd()
    df["signal"] = macd_object.macd_signal()

    prev_macd = df["macd"].iloc[-3]
    prev_signal = df["signal"].iloc[-3]
    curr_macd = df["macd"].iloc[-2]
    curr_signal = df["signal"].iloc[-2]

    if prev_macd <= prev_signal and curr_macd > curr_signal:
        signal_type = "BUY"
    elif prev_macd >= prev_signal and curr_macd < curr_signal:
        signal_type = "SELL"
    else:
        signal_type = None

    if signal_type and last_signals.get(symbol) != signal_type:
        last_signals[symbol] = signal_type
        msg = f"إشارة {signal_type} للعملة {symbol} بسعر {curr_price}"
        send_telegram_alert(msg)
        active_trades[symbol] = {"type": signal_type, "tp": curr_price, "sl": curr_price}

def run_bot():
    print("🚀 بدأ تشغيل البوت في الخلفية...")
    send_telegram_alert("🤖 *تم تشغيل بوت التداول بنجاح!*")
    while True:
        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(analyze_symbol, SYMBOLS)
        time.sleep(180)

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Trading Bot is running successfully!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()
