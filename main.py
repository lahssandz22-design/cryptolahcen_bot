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

# الفريم الزمني الجديد (ساعة واحدة)
TIMEFRAME = "1h"

# قاموس لتتبع حالة التقاطع السابقة لكل عملة لمنع تكرار التنبيه
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

def analyze_symbol(symbol):
    """تحليل زوج واحد وفحص تقاطع الماكدي على فريم الساعة"""
    df = get_binance_klines(symbol, TIMEFRAME)
    if df is None or len(df) < 30:
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
    
    # فحص آخر شمعة مغلقة
    prev_macd = df['macd'].iloc[-3]
    prev_signal = df['signal'].iloc[-3]
    
    curr_macd = df['macd'].iloc[-2]
    curr_signal = df['signal'].iloc[-2]
    
    close_price = df['close'].iloc[-2]
    recent_low = df['low'].iloc[-11:-1].min()   
    recent_high = df['high'].iloc[-11:-1].max() 

    signal_type = None
    
    # 1. تقاطع شراء
    if prev_macd <= prev_signal and curr_macd > curr_signal:
        signal_type = "BUY"
    # 2. تقاطع بيع
    elif prev_macd >= prev_signal and curr_macd < curr_signal:
        signal_type = "SELL"

    # معالجة الإشارة وإرسال التنبيه
    if signal_type and last_signals.get(symbol) != signal_type:
        last_signals[symbol] = signal_type
        
        if signal_type == "BUY":
            risk = close_price - recent_low
            tp_price = close_price + (risk * 2)
            
            msg = (
                f"🟢 *إشارة شراء (MACD 1H)* 🟢\n\n"
                f"• *الزوج:* `{symbol}`\n"
                f"• *الفريم:* `{TIMEFRAME}`\n"
                f"• *سعر الإغلاق:* `${close_price:,.4f}`\n"
                f"• *وقف الخسارة:* `${recent_low:,.4f}`\n"
                f"• *الهدف المقترح (1:2):* `${tp_price:,.4f}`\n"
                f"• *قيمة MACD:* `{curr_macd:.4f}`"
            )
        else: # SELL
            risk = recent_high - close_price
            tp_price = close_price - (risk * 2)
            
            msg = (
                f"🔴 *إشارة بيع (MACD 1H)* 🔴\n\n"
                f"• *الزوج:* `{symbol}`\n"
                f"• *الفريم:* `{TIMEFRAME}`\n"
                f"• *سعر الإغلاق:* `${close_price:,.4f}`\n"
                f"• *وقف الخسارة:* `${recent_high:,.4f}`\n"
                f"• *الهدف المقترح (1:2):* `${tp_price:,.4f}`\n"
                f"• *قيمة MACD:* `{curr_macd:.4f}`"
            )
        
        print(f"🚨 تم العثور على إشارة {signal_type} لـ {symbol}")
        send_telegram_alert(msg)

# ==========================================
# 3. تشغيل الفحص المتوازي (Multi-threading)
# ==========================================
def run_bot():
    print(f"✅ تم تشغيل بوت إشارات تقاطع MACD على فريم [{TIMEFRAME}] لـ {len(SYMBOLS)} عملة...")
    send_telegram_alert(f"🤖 *تم تشغيل بوت إشارات MACD*\nجاري مراقبة `{len(SYMBOLS)}` عملة على فريم `{TIMEFRAME}`.")

    while True:
        print(f"🔄 بدء دورة فحص جديدة لـ {len(SYMBOLS)} عملة...")
        
        # استخدام ThreadPoolExecutor لتسريع فحص العملات بالتوازي
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(analyze_symbol, SYMBOLS)
            
        print("✅ اكتملت دورة الفحص. الانتظار للدورة القادمة...")
        
        # الانتظار 3 دقائق (180 ثانية) نظراً لأن الفريم أصبح ساعة واحدة، لتحديث البيانات بانتظام مع اغلاق الشموع
        time.sleep(180)

if __name__ == "__main__":
    run_bot()
