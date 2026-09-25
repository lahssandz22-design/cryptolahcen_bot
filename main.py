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
TELEGRAM_BOT_TOKEN = "8617483405:AAGhNHH1a3X1twjDUU5fwdwr6rUYKMhc9gc"
TELEGRAM_CHAT_ID = "7895743860"

SYMBOLS = [
    # العملات الكبرى والرئيسية
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "POLUSDT", "LTCUSDT", "NEARUSDT", "APTUSDT",
    "TRXUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "FILUSDT",
    "ICPUSDT",
    # عملات الذكاء الاصطناعي والطبقة الثانية والألعاب
    "ARBUSDT", "SUIUSDT", "OPUSDT", "INJUSDT", "RENDERUSDT",
    "TIAUSDT", "SEIUSDT", "STXUSDT", "IMXUSDT", "FETUSDT",
    "RUNEUSDT", "GRTUSDT", "ALGOUSDT", "FTMUSDT", "SANTOSUSDT",
    "SANDUSDT", "MANAUSDT", "AXSUSDT", "GALAUSDT", "CHZUSDT",
    "CRVUSDT", "AAVEUSDT", "SNXUSDT", "MKRUSDT", "COMPUSDT",
    "LDOUSDT", "PENDLEUSDT", "JUPUSDT", "PYTHUSDT", "WIFUSDT",
    "PEPEUSDT", "SHIBUSDT", "FLOKIUSDT", "BOMEUSDT", "BONKUSDT",
    "JASMYUSDT", "ORDIUSDT", "SATSUSDT", "RSRUSDT", "ACEUSDT",
    "PORTALUSDT", "PIXELUSDT", "STRKUSDT", "MANTAUSDT", "ALTUSDT",
    "XAIUSDT", "AIUSDT", "NFPUSDT", "ZETAUSDT", "DYMUSDT",
    "AXLUSDT", "OMUSDT", "BBUSDT", "REZUSDT", "IOUSDT",
    "ZKUSDT", "LISTAUSDT", "BANANAUSDT", "TONUSDT", "NOTUSDT",
    "DOGSUSDT", "CATIUSDT", "HMSTRUSDT", "EIGENUSDT", "NEIROUSDT",
    "TURBOUSDT", "1000SATSUSDT", "1000RATSUSDT", "POLYXUSDT", "CFXUSDT",
    "KASUSDT", "ARUSDT", "ROSEUSDT", "OCEANUSDT", "AGIXUSDT",
    "PHBUSDT", "IDUSDT",
    # إضافات جديدة للوصول إلى 150 عملة قوية ومتوسطة
    "SXPUSDT", "CHRUSDT", "HBARUSDT", "ENJUSDT", "BATUSDT",
    "ZRXUSDT", "KNCUSDT", "IOSTUSDT", "ONTUSDT", "ZILUSDT",
    "VETUSDT", "THETAUSDT", "XTZUSDT", "EOSUSDT", "BCHUSDT",
    "XLMUSDT", "DASHUSDT", "ZECUSDT", "KSMUSDT",
    "STORJUSDT", "LRCUSDT", "ANKRUSDT", "SCUSDT", "ZENUSDT",
    "RVNUSDT", "COTIUSDT", "BLZUSDT", "HIFIUSDT", "CYBERUSDT",
    "ARKMUSDT", "MEMEUSDT", "VANRYUSDT", "AEVOUSDT", "ETHFIUSDT",
    "SAGAUSDT", "TNSRUSDT", "MERLUSDT", "ZROUSDT", "AVAILUSDT",
    "SYNUSDT", "LQTYUSDT", "COMBOUSDT", "IQUSDT", "DGBUSDT",
    "GMXUSDT", "GNSUSDT", "ILVUSDT"
]

TIMEFRAME = "1h"
MAX_OPEN_TRADES = 25

active_trades = {}
last_signals = {symbol: None for symbol in SYMBOLS}
closed_trades_history = []

# ==========================================
# 2. الدوال الأساسية للتلجرام والتحليل
# ==========================================
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
        print(f"❌ خطأ في إرسال التلجرام: {e}")

def send_telegram_photo(photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {'photo': ('performance.png', photo_bytes, 'image/png')}
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"❌ خطأ في إرسال الصورة للتلجرام: {e}")

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

def generate_and_send_performance_report():
    global closed_trades_history
    total = len(closed_trades_history)
    if total == 0:
        return

    wins = sum(1 for t in closed_trades_history if t['result'] == 'WIN')
    losses = sum(1 for t in closed_trades_history if t['result'] == 'LOSS')
    win_rate = (wins / total) * 100

    pnl_accumulative = [0]
    curr = 0
    for t in closed_trades_history:
        if t['result'] == 'WIN':
            curr += 2.0
        else:
            curr -= 1.0
        pnl_accumulative.append(curr)

    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor='#1e1e1e')
    ax.set_facecolor('#1e1e1e')
    ax.plot(pnl_accumulative, marker='o', color='#2eb85c' if curr >= 0 else '#e55353', linewidth=2)
    ax.set_title(f"Bot Performance Report: Last {total} Trades", color='white')
    ax.tick_params(colors='white')
    ax.grid(True, linestyle='--', alpha=0.3)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    buf.seek(0)
    plt.close()

    caption = (
        f"📊 *تقرير أداء آخر {total} صفقة مغلقة*\n\n"
        f"✅ الصفقات الرابحة: `{wins}`\n"
        f"❌ الصفقات الخاسرة: `{losses}`\n"
        f"🎯 نسبة النجاح (Win Rate): `{win_rate:.1f}%`\n"
        f"💰 صافي الربح التراكمي: `{curr:+.1f}R`"
    )
    send_telegram_photo(buf.getvalue(), caption=caption)
    closed_trades_history = []

def check_trade_closures(symbol, df, curr_price):
    if symbol not in active_trades:
        return

    trade_info = active_trades[symbol]
    trade_type = trade_info['type']
    tp = trade_info['tp']
    sl = trade_info['sl']

    closed = False
    result_type = ""
    result_msg = ""

    if trade_type == "BUY":
        if curr_price >= tp:
            closed = True
            result_type = "WIN"
            result_msg = f"🎯 *تم تحقيق الهدف (TP)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"
        elif curr_price <= sl:
            closed = True
            result_type = "LOSS"
            result_msg = f"🛑 *تم ضرب وقف الخسارة (SL)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"
            
    elif trade_type == "SELL":
        if curr_price <= tp:
            closed = True
            result_type = "WIN"
            result_msg = f"🎯 *تم تحقيق الهدف (TP)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"
        elif curr_price >= sl:
            closed = True
            result_type = "LOSS"
            result_msg = f"🛑 *تم ضرب وقف الخسارة (SL)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"

    if closed:
        print(f"🔒 إغلاق الصفقة: {symbol} النتيجة: {result_type}")
        send_telegram_alert(result_msg)
        closed_trades_history.append({"symbol": symbol, "result": result_type})
        active_trades.pop(symbol, None)
        last_signals[symbol] = None

        if len(closed_trades_history) >= 20:
            generate_and_send_performance_report()

def analyze_symbol(symbol):
    global active_trades
    df = get_binance_klines(symbol, TIMEFRAME)
    if df is None or len(df) < 30:
        return

    curr_price = df['close'].iloc[-2]

    if symbol in active_trades:
        check_trade_closures(symbol, df, curr_price)
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

    recent_low = df['low'].iloc[-11:-1].min()
    recent_high = df['high'].iloc[-11:-1].max()

    signal_type = None
    if prev_macd <= prev_signal and curr_macd > curr_signal:
        signal_type = "BUY"
    elif prev_macd >= prev_signal and curr_macd < curr_signal:
        signal_type = "SELL"

    if signal_type and last_signals.get(symbol) != signal_type:
        last_signals[symbol] = signal_type

        if signal_type == "BUY":
            risk = curr_price - recent_low
            tp_price = curr_price + (risk * 2)
            sl_price = recent_low
            msg = (
                f"🟢 *إشارة شراء جديدة (MACD 1H)* 🟢\n\n"
                f"• *الزوج:* `{symbol}`\n"
                f"• *سعر الدخول:* `${curr_price:,.4f}`\n"
                f"• *وقف الخسارة:* `${sl_price:,.4f}`\n"
                f"• *الهدف (1:2):* `${tp_price:,.4f}`\n"
                f"• *الصفقات النشطة حالياً:* `{len(active_trades) + 1}/{MAX_OPEN_TRADES}`"
            )
        else:
            risk = recent_high - curr_price
            tp_price = curr_price - (risk * 2)
            sl_price = recent_high
            msg = (
                f"🔴 *إشارة بيع جديدة (MACD 1H)* 🔴\n\n"
                f"• *الزوج:* `{symbol}`\n"
                f"• *سعر الدخول:* `${curr_price:,.4f}`\n"
                f"• *وقف الخسارة:* `${sl_price:,.4f}`\n"
                f"• *الهدف (1:2):* `${tp_price:,.4f}`\n"
                f"• *الصفقات النشطة حالياً:* `{len(active_trades) + 1}/{MAX_OPEN_TRADES}`"
            )

        active_trades[symbol] = {
            "type": signal_type,
            "tp": tp_price,
            "sl": sl_price
        }
        print(f"🚨 تم فتح صفقة {signal_type} لـ {symbol}")
        send_telegram_alert(msg)

# ==========================================
# 3. تشغيل الفحص المتوازي والسيرفر
# ==========================================
def run_bot():
    print(f"✅ تم تشغيل البوت بحد أقصى {MAX_OPEN_TRADES} صفقة على فريم [{TIMEFRAME}] لمراقبة {len(SYMBOLS)} عملة...")
    while True:
        print(f"🔄 بدء دورة فحص جديدة لـ {len(SYMBOLS)} عملة...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(analyze_symbol, SYMBOLS)

        print(f"✅ انتهت الدورة. الصفقات النشطة حالياً: {len(active_trades)}/{MAX_OPEN_TRADES} | صفقات السجل حتى الآن: {len(closed_trades_history)}/20")
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
    # إرسال رسالة التليجرام فور بدء تشغيل السيرفر مباشرة
    print("🚀 جاري إرسال تنبيه التشغيل عبر التليجرام...")
    send_telegram_alert(f"🤖 *تم تشغيل بوت التداول بنجاح!*\n• مراقبة `{len(SYMBOLS)}` عملة رقمية 🚀\n• وضع الحماية مفعّل 🔒")

    # تشغيل حلقة البوت في الخلفية
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    # تشغيل سيرفر الويب الخاص بـ Render
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()
