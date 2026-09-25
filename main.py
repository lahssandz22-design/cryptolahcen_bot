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
# 1. إعدادات التلجرام وقائمة الـ 200 زوج
# ==========================================
TELEGRAM_BOT_TOKEN = "8617483405:AAGhNHH1A3X1twjDUU5fwdWr6rUYKMhc9gc"
TELEGRAM_CHAT_ID = "7895743860"

SYMBOLS = [
    # الكبرى والرئيسية
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", 
    "DOGEUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT",
    "ETCUSDT", "NEARUSDT", "APTUSDT", "SUIUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
    "RENDERUSDT", "FETUSDT", "AGIXUSDT", "OCEANUSDT", "TIAUSDT", "SEIUSDT", "SHIBUSDT",
    "PEPEUSDT", "FLOKIUSDT", "ICPUSDT", "FILUSDT", "STXUSDT", "IMXUSDT", "RUNEUSDT",
    "GRTUSDT", "ALGOUSDT", "FTMUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT", "GALAUSDT",
    "CHZUSDT", "CRVUSDT", "AAVEUSDT", "SNXUSDT", "MKRUSDT", "COMPUSDT", "LDOUSDT",
    "PENDLEUSDT", "JUPUSDT", "PYTHUSDT", "WIFUSDT", "BONKUSDT", "JASMYUSDT", "ORDIUSDT",
    # عملات الطبقة الثانية والذكاء الاصطناعي والألعاب
    "SATSUSDT", "RSRUSDT", "ACEUSDT", "PORTALUSDT", "PIXELUSDT", "STRKUSDT", "MANTAUSDT",
    "ALTUSDT", "XAIUSDT", "AIUSDT", "NFPUSDT", "ZETAUSDT", "DYMUSDT", "AXLUSDT",
    "OMUSDT", "BBUSDT", "REZUSDT", "IOUSDT", "ZKUSDT", "LISTAUSDT", "BANANAUSDT",
    "TONUSDT", "NOTUSDT", "DOGSUSDT", "CATIUSDT", "HMSTRUSDT", "EIGENUSDT", "NEIROUSDT",
    "TURBOUSDT", "1000SATSUSDT", "1000RATSUSDT", "POLYXUSDT", "CFXUSDT", "KASUSDT",
    "ARUSDT", "ROSEUSDT", "PHBUSDT", "IDUSDT", "SXPUSDT", "CHRUSDT", "HBARUSDT",
    "ENJUSDT", "BATUSDT", "ZRXUSDT", "KNCUSDT", "IOSTUSDT", "ONTUSDT", "ZILUSDT",
    "VETUSDT", "THETAUSDT", "XTZUSDT", "EOSUSDT", "BCHUSDT", "XLMUSDT", "DASHUSDT",
    "ZECUSDT", "KSMUSDT", "STORJUSDT", "LRCUSDT", "ANKRUSDT", "SCUSDT", "ZENUSDT",
    "RVNUSDT", "COTIUSDT", "BLZUSDT", "HIFIUSDT", "CYBERUSDT", "ARKMUSDT", "MEMEUSDT",
    # عملات إضافية لتغطية نطاق واسع ومتوسط (أكثر من 200 زوج)
    "VANRYUSDT", "AEVOUSDT", "ETHFIUSDT", "SAGAUSDT", "TNSRUSDT", "MERLUSDT", "ZROUSDT",
    "AVAILUSDT", "SYNUSDT", "LQTYUSDT", "COMBOUSDT", "IQUSDT", "DGBUSDT", "GMXUSDT",
    "GNSUSDT", "ILVUSDT", "POLUSDT", "BOMEUSDT", "SANTOSUSDT", "LazioUSDT", "PORTOUSDT",
    "ALPINEUSDT", "PSGUSDT", "BARUSDT", "CITYUSDT", "INTERUSDT", "ACMUSDT", "ASRUSDT",
    "ATMUSDT", "OGUSDT", "GALUSDT", "HQUSDT", "HIGHUSDT", "HOOKUSDT", "IDEXUSDT",
    "MAGICUSDT", "VOXELUSDT", "GHSTUSDT", "UNIUSDT", "SPELLUSDT", "KP3RUSDT", "BIFIUSDT",
    "FARMUSDT", "MDTUSDT", "STPTUSDT", "RADUSDT", "POLSUSDT", "ALPHAUSDT", "BAKEUSDT",
    "BURGERUSDT", "C98USDT", "DEXEUSDT", "DFUSDT", "DKAUSDT", "FORUSDT", "FRONTUSDT",
    "GTCUSDT", "HARDUSDT", "KEEPUSDT", "LITUSDT", "MOVRUSDT", "NULSUSDT", "OXTUSDT",
    "PERPUSDT", "PONDUSDT", "QIUSDT", "QTUMUSDT", "RAYUSDT", "REEFUSDT", "RFUELUSDT",
    "RLCUSDT", "SCRTUSDT", "SUNUSDT", "SUPERUSDT", "TKOUSDT", "TLMUSDT", "TRUUSDT",
    "UNFIUSDT", "VIDTUSDT", "WNXMUSDT", "XEMUSDT", "YFIUSDT", "YFIIUSDT", "PROMUSDT",
    "BLURUSDT", "ACEUSDT", "PORTALUSDT", "PIXELUSDT", "MAVUSDT", "PENDLEUSDT", "SUIUSDT"
]

TIMEFRAME = "1h"
MAX_OPEN_TRADES = 50  

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

def generate_performance_chart(trades_batch):
    wins = sum(1 for t in trades_batch if t['result'] == 'WIN')
    losses = sum(1 for t in trades_batch if t['result'] == 'LOSS')
    win_rate = (wins / len(trades_batch)) * 100 if len(trades_batch) > 0 else 0

    fig, ax = plt.subplots(figsize=(6, 4))
    categories = ['الربح (WIN)', 'الخسارة (LOSS)']
    counts = [wins, losses]
    colors = ['#2ecc71', '#e74c3c']

    ax.bar(categories, counts, color=colors)
    ax.set_title(f"نتائج آخر {len(trades_batch)} صفقة (نسبة النجاح: {win_rate:.1f}%)", fontsize=12, fontweight='bold')
    ax.set_ylabel('عدد الصفقات')

    for i, v in enumerate(counts):
        ax.text(i, v + 0.1, str(v), ha='center', fontweight='bold')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()

def check_and_close_trades():
    global active_trades, closed_trades_history
    for symbol in list(active_trades.keys()):
        trade = active_trades[symbol]
        df = get_binance_klines(symbol, TIMEFRAME, limit=10)
        if df is None:
            continue
        curr_price = df['close'].iloc[-1]
        
        if trade['type'] == 'BUY':
            if curr_price >= trade['tp']:
                trade['result'] = 'WIN'
                closed_trades_history.append(trade)
                send_telegram_alert(f"🎯 *تم تحقيق الهدف (WIN)* للعملة {symbol} بسعر {curr_price}")
                del active_trades[symbol]
            elif curr_price <= trade['sl']:
                trade['result'] = 'LOSS'
                closed_trades_history.append(trade)
                send_telegram_alert(f"🛑 *ضرب وقف الخسارة (LOSS)* للعملة {symbol} بسعر {curr_price}")
                del active_trades[symbol]
        elif trade['type'] == 'SELL':
            if curr_price <= trade['tp']:
                trade['result'] = 'WIN'
                closed_trades_history.append(trade)
                send_telegram_alert(f"🎯 *تم تحقيق الهدف (WIN)* للعملة {symbol} بسعر {curr_price}")
                del active_trades[symbol]
            elif curr_price >= trade['sl']:
                trade['result'] = 'LOSS'
                closed_trades_history.append(trade)
                send_telegram_alert(f"🛑 *ضرب وقف الخسارة (LOSS)* للعملة {symbol} بسعر {curr_price}")
                del active_trades[symbol]

        if len(closed_trades_history) >= 20:
            batch = closed_trades_history[:20]
            closed_trades_history = closed_trades_history[20:]
            chart_bytes = generate_performance_chart(batch)
            wins = sum(1 for t in batch if t['result'] == 'WIN')
            losses = sum(1 for t in batch if t['result'] == 'LOSS')
            wr = (wins / 20) * 100
            caption = f"📊 *تقرير أداء آخر 20 صفقة*\n✅ صفقات ناجحة: {wins}\n❌ صفقات خاسرة: {losses}\n📈 نسبة الربح: {wr:.1f}%"
            send_telegram_photo(chart_bytes, caption)

def analyze_symbol(symbol):
    global active_trades
    df = get_binance_klines(symbol, TIMEFRAME, limit=250)
    if df is None or len(df) < 50:
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

    signal_type = None

    # شروط التقاطع الجديدة حسب طلبك تماماً:
    # شراء: تقاطع صعوداً وتحت خط الصفر
    if prev_macd <= prev_signal and curr_macd > curr_signal and curr_macd < 0:
        signal_type = "BUY"
    # بيع: تقاطع هبوطاً وفوق خط الصفر
    elif prev_macd >= prev_signal and curr_macd < curr_signal and curr_macd > 0:
        signal_type = "SELL"

    if signal_type and last_signals.get(symbol) != signal_type:
        last_signals[symbol] = signal_type
        
        distance = curr_price * 0.015
        if signal_type == "BUY":
            sl = curr_price - distance
            tp = curr_price + (distance * 2)
        else:
            sl = curr_price + distance
            tp = curr_price - (distance * 2)

        msg = f"إشارة {signal_type} للعملة {symbol}\nسعر الدخول: {curr_price}"
        send_telegram_alert(msg)
        active_trades[symbol] = {"type": signal_type, "tp": tp, "sl": sl}

def run_bot():
    print(f"🚀 بدأ تشغيل البوت في الخلفية لمراقبة العملات ({len(SYMBOLS)} زوجاً)...")
    send_telegram_alert(f"🤖 *تم تشغيل بوت التداول بنجاح لمراقبة ({len(SYMBOLS)} زوجاً)* بالشروط الجديدة!")
    while True:
        check_and_close_trades()
        with ThreadPoolExecutor(max_workers=25) as executor:
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
