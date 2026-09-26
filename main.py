from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import threading
import time
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
import ta

# ==========================================
# إعدادات بوت التلجرام وبينانس (بالتوكن الجديد)
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
        return symbols[:100] # ضبط العدد على 100 لضمان استقرار التشغيل على الهاتف
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

SYMBOLS = fetch_top_usdt_symbols()
TIMEFRAME = "1h"

last_signal_times = {}
active_trades = []      
closed_trades_history = [] 

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

def send_telegram_photo(photo_bytes, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {'photo': ('stats.png', photo_bytes, 'image/png')}
    data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"خطأ في إرسال الصورة: {e}")

def get_binance_klines(symbol, interval, limit=250):
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
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        return df
    except Exception:
        return None

def generate_stats_image():
    if not closed_trades_history:
        return None
    
    recent = closed_trades_history[-20:]
    wins = sum(1 for t in recent if t['result'] == 'WIN')
    losses = sum(1 for t in recent if t['result'] == 'LOSS')
    total = len(recent)
    win_rate = (wins / total) * 100 if total > 0 else 0

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie([wins, losses], labels=[f'ربح ({wins})', f'خسارة ({losses})'], 
           colors=['#2ecc71', '#e74c3c'], autopct='%1.1f%%', startangle=140, 
           textprops={'color': 'white', 'weight': 'bold'})
    ax.set_facecolor('#1e1e1e')
    fig.patch.set_facecolor('#1e1e1e')
    plt.title(f"إحصائيات آخر {total} صفقة (Win Rate: {win_rate:.1f}%)", color='white', weight='bold', fontsize=12)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()

def monitor_and_analyze_market():
    print(f"🚀 بدء فحص السوق لـ {len(SYMBOLS)} عملة على فريم {TIMEFRAME}...")
    while True:
        try:
            global active_trades
            for trade in active_trades[:]:
                df_check = get_binance_klines(trade['symbol'], TIMEFRAME, limit=5)
                if df_check is not None and not df_check.empty:
                    current_price = df_check['close'].iloc[-1]
                    high_price = df_check['high'].iloc[-1]
                    low_price = df_check['low'].iloc[-1]
                    
                    if trade['type'] == 'BUY':
                        if high_price >= trade['tp']:
                            trade['result'] = 'WIN'
                            closed_trades_history.append(trade)
                            active_trades.remove(trade)
                            send_telegram_alert(f"🟢 *تم تحقيق الهدف بربح! (TP)*\n🪙 العملة: `{trade['symbol']}`\n💰 سعر الخروج: `{trade['tp']}`")
                            check_and_send_stats()
                        elif low_price <= trade['sl']:
                            trade['result'] = 'LOSS'
                            closed_trades_history.append(trade)
                            active_trades.remove(trade)
                            send_telegram_alert(f"🔴 *ضرب وقف الخسارة (SL)*\n🪙 العملة: `{trade['symbol']}`\n📉 سعر الخروج: `{trade['sl']}`")
                            check_and_send_stats()
                    elif trade['type'] == 'SELL':
                        if low_price <= trade['tp']:
                            trade['result'] = 'WIN'
                            closed_trades_history.append(trade)
                            active_trades.remove(trade)
                            send_telegram_alert(f"🟢 *تم تحقيق الهدف بربح! (TP)*\n🪙 العملة: `{trade['symbol']}`\n💰 سعر الخروج: `{trade['tp']}`")
                            check_and_send_stats()
                        elif high_price >= trade['sl']:
                            trade['result'] = 'LOSS'
                            closed_trades_history.append(trade)
                            active_trades.remove(trade)
                            send_telegram_alert(f"🔴 *ضرب وقف الخسارة (SL)*\n🪙 العملة: `{trade['symbol']}`\n📈 سعر الخروج: `{trade['sl']}`")
                            check_and_send_stats()

            for symbol in SYMBOLS:
                df = get_binance_klines(symbol, TIMEFRAME, limit=220)
                if df is None or len(df) < 205:
                    continue
                
                df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)
                macd_object = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
                df["macd"] = macd_object.macd()
                df["signal"] = macd_object.macd_signal()

                curr_price = df['close'].iloc[-2]
                curr_ema200 = df['ema200'].iloc[-2]
                current_candle_time = df['timestamp'].iloc[-2]

                prev_macd = df["macd"].iloc[-3]
                prev_signal = df["signal"].iloc[-3]
                curr_macd = df["macd"].iloc[-2]
                curr_signal = df["signal"].iloc[-2]

                signal_type = None

                if curr_price > curr_ema200:
                    if prev_macd <= prev_signal and curr_macd > curr_signal and curr_macd < 0:
                        signal_type = "BUY"
                elif curr_price < curr_ema200:
                    if prev_macd >= prev_signal and curr_macd < curr_signal and curr_macd > 0:
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

                    msg = (
                        f"🚨 *إشارة دخول جديدة ({signal_type})*\n"
                        f"🪙 العملة: `{symbol}`\n"
                        f"⏱ الفريم: `{TIMEFRAME}`\n"
                        f"📊 الاتجاه (فلتر EMA 200): مع الاتجاه\n"
                        f"💰 سعر الدخول: `{curr_price}`\n"
                        f"🎯 الهدف (TP): `{tp:.4f}`\n"
                        f"🛑 وقف الخسارة (SL): `{sl:.4f}`\n"
                        f"⚖️ نسبة المخاطر والعائد: 1:2"
                    )
                    send_telegram_alert(msg)
                    
                    active_trades.append({
                        'symbol': symbol,
                        'type': signal_type,
                        'entry': curr_price,
                        'tp': tp,
                        'sl': sl
                    })
                
                time.sleep(0.3)

        except Exception as e:
            print(f"خطأ في حلقة التحليل: {e}")
        
        time.sleep(60)

def check_and_send_stats():
    if len(closed_trades_history) % 5 == 0:
        img_bytes = generate_stats_image()
        if img_bytes:
            recent = closed_trades_history[-20:]
            wins = sum(1 for t in recent if t['result'] == 'WIN')
            losses = sum(1 for t in recent if t['result'] == 'LOSS')
            caption = f"📊 *تقرير أداء آخر {len(recent)} صفقات منفذة*\n✅ صفقات رابحة: `{wins}`\n❌ صفقات خاسرة: `{losses}`"
            send_telegram_photo(img_bytes, caption)

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Trading Bot with EMA200 & MACD is running successfully!")
    def log_message(self, format, *args):
        return

if __name__ == "__main__":
    send_telegram_alert("🤖 *تم تشغيل بوت التداول المطور بنجاح (EMA 200 + MACD)*\n📈 يتم مراقبة العملات رقمية بنجاح.")

    bot_thread = threading.Thread(target=monitor_and_analyze_market)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()
