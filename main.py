import time
import requests
import pandas as pd
import ta
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. إعدادات التلجرام وبينانس
# ==========================================
TELEGRAM_BOT_TOKEN = "869642227:AAGNB88pBF_kJzEVBLzFQrBGv7yRG5f3Js4"
TELEGRAM_CHAT_ID = "7895743860"

# قائمة الـ 50 عملة (القوية والمتوسطة)
SYMBOLS = [
    # العملات الكبرى والقوية جداً (الصف الأول)
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
    
    # العملات القوية والمتوسطة ذات السيولة العالية (الصف الثاني)
    "MATICUSDT", "LTCUSDT", "NEARUSDT", "APTUSDT", "TRXUSDT",
    "UNIUSDT", "ATOMUSDT", "ETCUSDT", "FILUSDT", "ARBUSDT",
    "SUIUSDT", "OPUSDT", "INJUSDT", "RENDERUSDT", "TIAUSDT",
    "SEIUSDT", "STXUSDT", "IMXUSDT", "FETUSDT", "RUNEUSDT",
    
    # العملات المتوسطة والناشطة في التداول
    "ICPUSDT", "GRTUSDT", "ALGOUSDT", "FTMUSDT",
    "SANDUSDT", "MANAUSDT", "AXSUSDT", "GALAUSDT", "CHZUSDT",
    "CRVUSDT", "AAVEUSDT", "SNXUSDT", "MKRUSDT", "COMPUSDT",
    "LDOUSDT", "PENDLEUSDT", "JUPUSDT", "PYTHUSDT", "WIFUSDT"
]

# الفريم الزمني
TIMEFRAME = "1h"

# الحد الأقصى للصفقات المفتوحة في نفس الوقت
MAX_OPEN_TRADES = 25

# تتبع الصفقات المفتوحة حالياً (العملة -> نوع الصفقة BUY/SELL)
active_trades = {}

# قاموس لتتبع آخر إشارة لكل عملة
last_signals = {symbol: None for symbol in SYMBOLS}

# ==========================================
# 2. الدوال الأساسية للتحليل والإرسال
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

def check_trade_closures(symbol, df, curr_price):
    """التحقق مما إذا تم ضرب الهدف أو وقف الخسارة لإغلاق الصفقة وتفريغ مكان"""
    if symbol not in active_trades:
        return
        
    trade_info = active_trades[symbol]
    trade_type = trade_info['type']
    tp = trade_info['tp']
    sl = trade_info['sl']
    
    closed = False
    result_msg = ""
    
    if trade_type == "BUY":
        if curr_price >= tp:
            closed = True
            result_msg = f"🎯 *تم تحقيق الهدف (TP)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"
        elif curr_price <= sl:
            closed = True
            result_msg = f"🛑 *تم ضرب وقف الخسارة (SL)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"
            
    elif trade_type == "SELL":
        if curr_price <= tp:
            closed = True
            result_msg = f"🎯 *تم تحقيق الهدف (TP)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"
        elif curr_price >= sl:
            closed = True
            result_msg = f"🛑 *تم ضرب وقف الخسارة (SL)* للعملة `{symbol}` بسعر `{curr_price:,.4f}`"
            
    if closed:
        print(f"🔒 إغلاق الصفقة: {symbol}")
        send_telegram_alert(result_msg)
        # إزالة الصفقة من القائمة النشطة وتصفير إشارتها ليتمكن البوت من دخولها لاحقاً
        del active_trades[symbol]
        last_signals[symbol] = None

def analyze_symbol(symbol):
    global active_trades
    
    df = get_binance_klines(symbol, TIMEFRAME)
    if df is None or len(df) < 30:
        return

    curr_price = df['close'].iloc[-2]
    
    # 1. فحص ما إذا كانت الصفقة مفتوحة مسبقاً لمتابعة إغلاقها (هدف أو وقف خسارة)
    if symbol in active_trades:
        check_trade_closures(symbol, df, curr_price)
        return

    # إذا وصل عدد الصفقات المفتوحة للحد الأقصى (25)، نتوقف عن فتح صفقات جديدة
    if len(active_trades) >= MAX_OPEN_TRADES:
        return

    # حساب الماكدي (12, 26, 9)
    macd_object = ta.trend.MACD(
        close=df['close'],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )
    
    df['macd'] = macd_object.macd()
    df['signal'] = macd_object.macd_signal()
    
    prev_macd = df['macd'].iloc[-3]
    prev_signal = df['signal'].iloc[-3]
    
    curr_macd = df['macd'].iloc[-2]
    curr_signal = df['signal'].iloc[-2]
    
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
        else: # SELL
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
        
        # تسجيل الصفقة كنشطة
        active_trades[symbol] = {
            'type': signal_type,
            'tp': tp_price,
            'sl': sl_price
        }
        
        print(f"🚨 تم فتح صفقة {signal_type} لـ {symbol} (المجموع: {len(active_trades)})")
        send_telegram_alert(msg)

# ==========================================
# 3. تشغيل الفحص المتوازي
# ==========================================
def run_bot():
    print(f"✅ تم تشغيل البوت بحد أقصى {MAX_OPEN_TRADES} صفقة على فريم [{TIMEFRAME}]...")
    send_telegram_alert(f"🤖 *تم تشغيل بوت الماكدي*\n• مراقبة `{len(SYMBOLS)}` عملة\n• الحد الأقصى للصفقات النشطة: `{MAX_OPEN_TRADES}` صفقة.")

    while True:
        print(f"🔄 بدء دورة فحص جديدة...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(analyze_symbol, SYMBOLS)
            
        print(f"✅ انتهت الدورة. الصفقات النشطة حالياً: {len(active_trades)}/{MAX_OPEN_TRADES}")
        time.sleep(180)

if __name__ == "__main__":
    run_bot()
