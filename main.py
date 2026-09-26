from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import os
import threading
import time
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
MAX_OPEN_TRADES_PER_TF = 20

active_trades = {tf: {} for tf in TIMEFRAMES}
last_signals = {tf: {symbol: None for symbol in SYMBOLS} for tf in TIMEFRAMES}
closed_trades_history = {tf: [] for tf in TIMEFRAMES}


def send_telegram_alert(message):
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": message,
      "parse_mode": "Markdown",
  }
  try:
    requests.post(url, data=payload, timeout=10)
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
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_av",
            "trades",
            "tb_base_av",
            "tb_quote_av",
            "ignore",
        ],
    )
    df["close"] = df["close"].astype(float)
    df["open"] = df["open"].astype(float)
    return df
  except Exception:
    return None


def analyze_symbol(symbol, timeframe):
  global active_trades
  try:
    print(
        f"🔍 جاري فحص العملة: {symbol} على الفريم: {timeframe}..."
    )
    df = get_binance_klines(symbol, timeframe, limit=50)
    if df is None or len(df) < 10:
      return

    curr_price = df["close"].iloc[-1]
    prev_price = df["close"].iloc[-2]

    if symbol in active_trades[timeframe]:
      return

    # شرط حساس جداً يعتمد على مقارنة الشمعة الحالية بالسابق لضمان ظهور صفقات بسرعة
    signal_type = None
    if curr_price > prev_price:
      signal_type = "BUY"
    else:
      signal_type = "SELL"

    # لتجنب إرسال نفس العملة بنماذج متكررة مباشرة
    if signal_type and last_signals[timeframe].get(symbol) != signal_type:
      last_signals[timeframe][symbol] = signal_type

      distance = curr_price * 0.01
      if signal_type == "BUY":
        sl = curr_price - distance
        tp = curr_price + (distance * 2)
      else:
        sl = curr_price + distance
        tp = curr_price - (distance * 2)

      msg = (
          f"🚨 *إشارة سريعة {signal_type} [فريم {timeframe}]*\n🪙 العملة:"
          f" {symbol}\n💰 سعر الدخول: {curr_price}\n🎯 الهدف:"
          f" {tp:.4f}\n🛑 وقف الخسارة: {sl:.4f}"
      )
      send_telegram_alert(msg)
      active_trades[timeframe][symbol] = {
          "type": signal_type,
          "tp": tp,
          "sl": sl,
      }
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
  send_telegram_alert(
      "🤖 *تم تشغيل بوت الإشارات السريعة التجريبي* \nسيتم إرسال الصفقات حالا."
  )

  for tf in TIMEFRAMES:
    t = threading.Thread(target=run_timeframe_bot, args=(tf,))
    t.daemon = True
    t.start()

  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHandler)
  server.serve_forever()
