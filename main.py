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

# قائمة أبرز 100 زوج USDT
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
    "NEARUSDT", "MATICUSDT", "LTCUSDT", "UNIUSDT", "FILUSDT",
    "ATOMUSDT", "ETCUSDT", "XLMUSDT", "BCHUSDT", "APTUSDT",
    "SUIUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "RNDRUSDT",
    "TIAUSDT", "SEIUSDT", "FETUSDT", "AGIXUSDT", "RENDERUSDT",
    "PEPEUSDT", "SHIBUSDT", "FLOKIUSDT", "BONKUSDT", "WIFUSDT",
    "ARUSDT", "IMXUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT",
    "GALAUSDT", "CHZUSDT", "CRVUSDT", "AAVEUSDT", "MKRUSDT",
    "SNXUSDT", "COMPUSDT", "LDOUSDT", "RUNEUSDT", "KASUSDT",
    "PYTHUSDT", "JUPUSDT", "STRKUSDT", "PORTALUSDT", "MAVUSDT",
    "PENDLEUSDT", "ACEUSDT", "NFPUSDT", "XAIUSDT", "AIUSDT",
    "BBUSDT", "REZUSDT", "IOUSDT", "ZKUSDT", "BANANAUSDT",
    "RENDERUSDT", "TONUSDT", "HMSTRUSDT", "CATIUSDT", "DOGSUSDT",
    "NEIROUSDT", "TURBOUSDT", "1000SATSUSDT", "1000RATSUSDT", "ORDIUSDT",
    "BOMEUSDT", "MEWUSDT", "SLERFUSDT", "POLUSDT", "EGLDUSDT",
    "ALGOUSDT", "HBARUSDT", "FTMUSDT", "FLOWUSDT", "THETAUSDT",
    "XTZUSDT", "EOSUSDT", "KAVAUSDT", "CHRUSDT", "GMXUSDT",
    "STXUSDT", "CFXUSDT", "LQTYUSDT", "SSVUSDT", "OCEANUSDT",
    "JASMYUSDT", "HOTUSDT", "ENJUSDT", "BATUSDT", "ZILUSDT"
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
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"❌ خطأ في إرسال التلجرام: {e}")

def send_telegram_photo(photo_bytes, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {'photo': ('performance.png', photo_bytes, 'image/png')}
    data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"❌ خطأ في إرسال الصورة للتلجرام: {e}")

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
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        return df
    except Exception:
        return None

def generate_performance_chart(trades_batch, timeframe):
    wins = sum(1 for t in trades_batch if t['result'] == 'WIN')
    losses = sum(1 for t in trades_batch if t['result'] == 'LOSS')
    win_rate = (wins / len(trades_batch)) * 100 if len(trades_batch) > 0 else 0

    fig, ax = plt.subplots(figsize=(6, 4))
    categories = ['الربح (WIN)', 'الخسارة (LOSS)']
    counts = [wins, losses]
    colors = ['#2ecc71', '#e74c3c']

    ax.bar(categories, counts, color=colors)
    ax.set_title(f"فريم ({timeframe}) - آخر {len(trades_batch)} صفقة (النجاح: {win_rate:.1f}%)", fontsize=11, fontweight='bold')
    ax.set_ylabel('عدد الصفقات')

    for i, v in enumerate(counts):
        ax.text(i, v + 0.1, str(v), ha='center', fontweight='bold')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()

def check_and_close_trades(timeframe):
    global active_trades, closed_trades_history
    tf_trades = active_trades[timeframe]
    for symbol in list(tf_trades.keys()):
        df = get_binance_klines(symbol, timeframe, limit=10)
        if df is None:
            continue
        curr_price = df['close'].iloc[-1]
        trade = tf_trades[symbol]
        
        if trade['type'] == 'BUY':
            if curr_price >= trade['tp']:
                trade['result'] = 'WIN'
                closed_trades_history[timeframe].append(trade)
                send_telegram_alert(f"🎯 *[فريم {timeframe}] تحقيق هدف (WIN)*\nالعملة: {symbol} بسعر {curr_price}")
                del tf_trades[symbol]
            elif curr_price <= trade['sl']:
                trade['result'] = 'LOSS'
                closed_trades_history[timeframe].append(trade)
                send_telegram_alert(f"🛑 *[فريم {timeframe}] ضرب وقف خسارة (LOSS)*\nالعملة: {symbol} بسعر {curr_price}")
                del tf_trades[symbol]
        elif trade['type'] == 'SELL':
            if curr_price <= trade['tp']:
                trade['result'] = 'WIN'
                closed_trades_history[timeframe].append(trade)
                send_telegram_alert(f"🎯 *[فريم {timeframe}] تحقيق هدف (WIN)*\nالعملة: {symbol} بسعر {curr_price}")
                del tf_trades[symbol]
            elif curr_price >= trade['sl']:
                trade['result'] = 'LOSS'
                closed_trades_history[timeframe].append(trade)
                send_telegram_alert(f"🛑 *[فريم {timeframe}] ضرب وقف خسارة (LOSS)*\nالعملة: {symbol} بسعر {curr_price}")
                del tf_trades[symbol]

        if len(closed_trades_history[timeframe]) >= 20:
            batch = closed_trades_history[timeframe][:20]
            closed_trades_history[timeframe] = closed_trades_history[timeframe][20:]
            chart_bytes = generate_performance_chart(batch, timeframe)
            wins = sum(1 for t in batch if t['result'] == 'WIN')
            losses = sum(1 for t in batch if t['result'] == 'LOSS')
            wr = (wins / 20) * 100
            caption = f"📊 *تقرير أداء فريم ({timeframe}) - آخر 20 صفقة*\n✅ صفقات ناجحة: {wins}\n❌ صفقات خاسرة: {losses}\n📈 نسبة الربح: {wr:.1f}%"
            send_telegram_photo(chart_bytes, caption)

def analyze_symbol(symbol, timeframe):
    global active_trades
    try:
        df = get_binance_klines(symbol, timeframe, limit=250)
        if df is None or len(df) < 50:
            return
            
        curr_price = df['close'].iloc[-2]

        if symbol in active_trades[timeframe]:
            return
        if len(active_trades[timeframe]) >= MAX_OPEN_TRADES_PER_TF:
            return

        macd_object = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd"] = macd_object.macd()
        df["signal"] = macd_object.macd_signal()

        curr_macd = df["macd"].iloc[-2]
        curr_signal = df["signal"].iloc[-2]

        signal_type = None

        # شرط مرن وسريع بناءً على اتجاه الزخم الحالي (MACD):
        # شراء: خط الماكد فوق خط الإشارة وتحت الصفر
        if curr_macd > curr_signal and curr_macd < 0:
            signal_type = "BUY"
        # بيع: خط الماكد تحت خط الإشارة وفوق الصفر
        elif curr_macd < curr_signal and curr_macd > 0:
            signal_type = "SELL"

        if signal_type and last_signals[timeframe].get(symbol) != signal_type:
            last_signals[timeframe][symbol] = signal_type
            
            distance = curr_price * 0.015
            if signal_type == "BUY":
                sl = curr_price - distance
                tp = curr_price + (distance * 2)
            else:
                sl = curr_price + distance
                tp = curr_price - (distance * 2)

            msg = f"🚨 *إشارة {signal_type} [فريم {timeframe}]*\n🪙 العملة: {symbol}\n💰 سعر الدخول: {curr_price}\n🎯 الهدف: {tp:.4f}\n🛑 وقف الخسارة: {sl:.4f}"
            send_telegram_alert(msg)
            active_trades[timeframe][symbol] = {"type": signal_type, "tp": tp, "sl": sl}
    except Exception as e:
        print(f"خطأ في تحليل العملة {symbol} على فريم {timeframe}: {e}")

def run_timeframe_bot(timeframe):
    print(f"🚀 بدأ تشغيل مراقبة الفريم: {timeframe}")
    while True:
        try:
            check_and_close_trades(timeframe)
            with ThreadPoolExecutor(max_workers=10) as executor:
                for symbol in SYMBOLS:
                    executor.submit(analyze_symbol, symbol, timeframe)
        except Exception as e:
            print(f"❌ خطأ في حلقة الفريم {timeframe}: {e}")
        
        time.sleep(60 if timeframe == "15m" else 120)

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Flexible MACD Trading Bot is running successfully!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    send_telegram_alert(f"🤖 *تم تحديث وتفعيل بوت التداول (الاستراتيجية المرنة)*\nالفريمات المفعلة: `15m` و `1h`\nعدد الأزواج المراقبَة: {len(SYMBOLS)} زوجاً.")

    for tf in TIMEFRAMES:
        t = threading.Thread(target=run_timeframe_bot, args=(tf,))
        t.daemon = True
        t.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()
