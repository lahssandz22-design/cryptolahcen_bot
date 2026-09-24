import io
import time
from concurrent.futures import ThreadPoolExecutor
import matplotlib.pyplot as plt
import pandas as pd
import requests

# ==================== الإعدادات ====================
TELEGRAM_TOKEN = "8617483405:AAGhNHH1A3X1twjDUU5fwdWr6rUYKMhc9gc"
CHAT_ID = "7895743860"

TIMEFRAME = "4h"

# قائمة لحفظ ومتابعة الصفقات المفتوحة حالياً
active_trades = []

# ==================== وظائف التلجرام ====================
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"خطأ في إرسال الرسالة: {e}")


def send_telegram_photo(photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {"photo": ("stats.png", photo_bytes, "image/png")}
    data = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"خطأ في إرسال الصورة: {e}")


# ==================== جلب العملات والحسابات ====================
def get_all_usdt_symbols():
    """جلب جميع أزواج USDT المتاحة للتداول في Binance"""
    url = "https://api.binance.com/api/v3/exchangeInfo"
    try:
        res = requests.get(url, timeout=10).json()
        symbols = [
            s["symbol"]
            for s in res["symbols"]
            if s["symbol"].endswith("USDT")
            and s["status"] == "TRADING"
            and not s["symbol"].endswith(("UPUSDT", "DOWNUSDT", "BEARUSDT", "BULLUSDT"))
        ]
        return symbols
    except Exception as e:
        print(f"خطأ في جلب قائمة العملات: {e}")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    return macd_line, signal_line


def get_klines(symbol, limit=600):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={TIMEFRAME}&limit={limit}"
    try:
        res = requests.get(url, timeout=10).json()
        if not isinstance(res, list):
            return None
        df = pd.DataFrame(res).iloc[:, :6]
        df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception:
        return None


# ==================== الباك تيست ورسم النتائج ====================
def backtest_last_20_trades(df, symbol):
    """محاكاة استراتيجية التداول واستخراج آخر 20 صفقة تاريخية مغلقة"""
    df["ema200"] = calculate_ema(df["close"], 200)
    df["macd"], df["signal"] = calculate_macd(df["close"])

    completed_trades = []

    for i in range(200, len(df) - 1):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]

        buy_cond = (
            (curr["close"] > curr["ema200"])
            and (prev["macd"] < prev["signal"])
            and (curr["macd"] > curr["signal"])
            and (curr["macd"] < 0)
        )

        sell_cond = (
            (curr["close"] < curr["ema200"])
            and (prev["macd"] > prev["signal"])
            and (curr["macd"] < curr["signal"])
            and (curr["macd"] > 0)
        )

        entry_type = None
        if buy_cond:
            entry_type = "BUY"
        elif sell_cond:
            entry_type = "SELL"

        if entry_type:
            entry_price = curr["close"]

            if entry_type == "BUY":
                stop_loss = df["low"].iloc[i - 5 : i].min()
                risk = entry_price - stop_loss
                if risk <= 0:
                    continue
                take_profit = entry_price + (risk * 2)
            else:
                stop_loss = df["high"].iloc[i - 5 : i].max()
                risk = stop_loss - entry_price
                if risk <= 0:
                    continue
                take_profit = entry_price - (risk * 2)

            result = None
            exit_price = 0
            for j in range(i + 1, len(df)):
                future_high = df["high"].iloc[j]
                future_low = df["low"].iloc[j]

                if entry_type == "BUY":
                    if future_low <= stop_loss:
                        result = "LOSS"
                        exit_price = stop_loss
                        break
                    elif future_high >= take_profit:
                        result = "WIN"
                        exit_price = take_profit
                        break
                elif entry_type == "SELL":
                    if future_high >= stop_loss:
                        result = "LOSS"
                        exit_price = stop_loss
                        break
                    elif future_low <= take_profit:
                        result = "WIN"
                        exit_price = take_profit
                        break

            if result:
                completed_trades.append(
                    {
                        "type": entry_type,
                        "entry": entry_price,
                        "exit": exit_price,
                        "result": result,
                    }
                )

    return completed_trades[-20:]


def generate_stats_image(symbol, trades):
    """إنشاء رسم بياني دائري لنتائج آخر 20 صفقة تاريخية"""
    wins = sum(1 for t in trades if t["result"] == "WIN")
    losses = sum(1 for t in trades if t["result"] == "LOSS")
    total = len(trades)

    if total == 0:
        return None

    win_rate = (wins / total) * 100
    labels = [f"رابحة ({wins})", f"خاسرة ({losses})"]
    sizes = [wins, losses]
    colors = ["#2ecc71", "#e74c3c"]

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        startangle=140,
        textprops={"fontsize": 12, "color": "white", "weight": "bold"},
    )
    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#1e1e1e")

    plt.title(
        f"نتائج آخر {total} صفقة تاريخية لـ {symbol}\nنسبة النجاح: {win_rate:.1f}%",
        color="white",
        fontsize=13,
        pad=15,
    )

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf


# ==================== تتبع الصفقات الحية ====================
def check_active_trades():
    """مراقبة الصفقات المفتوحة وتنبيه المستخدم فور ضرب الهدف أو الوقف"""
    global active_trades
    if not active_trades:
        return

    print(f"🔍 جاري فحص الصفقات النشطة ({len(active_trades)} صفقة مفتوحة)...")
    remaining_trades = []

    for trade in active_trades:
        symbol = trade["symbol"]
        df = get_klines(symbol, limit=5)
        if df is None or len(df) == 0:
            remaining_trades.append(trade)
            continue

        latest_high = df["high"].iloc[-1]
        latest_low = df["low"].iloc[-1]

        closed = False
        status_msg = ""

        if trade["type"] == "BUY":
            if latest_high >= trade["tp"]:
                closed = True
                status_msg = (
                    f"🎉 *تم إغلاق صفقة رابحة! (Take Profit)* 🟢\n"
                    f"• *الرمز:* `{symbol}`\n"
                    f"• *نوع الصفقة:* `شراء (BUY)`\n"
                    f"• *سعر الدخول:* `{trade['entry']:,.4f}`\n"
                    f"• *سعر الإغلاق (الهدف):* `{trade['tp']:,.4f}`"
                )
            elif latest_low <= trade["sl"]:
                closed = True
                status_msg = (
                    f"🔻 *تم إغلاق صفقة خاسرة (Stop Loss)* 🔴\n"
                    f"• *الرمز:* `{symbol}`\n"
                    f"• *نوع الصفقة:* `شراء (BUY)`\n"
                    f"• *سعر الدخول:* `{trade['entry']:,.4f}`\n"
                    f"• *سعر الإغلاق (الوقف):* `{trade['sl']:,.4f}`"
                )

        elif trade["type"] == "SELL":
            if latest_low <= trade["tp"]:
                closed = True
                status_msg = (
                    f"🎉 *تم إغلاق صفقة رابحة! (Take Profit)* 🟢\n"
                    f"• *الرمز:* `{symbol}`\n"
                    f"• *نوع الصفقة:* `بيع (SELL)`\n"
                    f"• *سعر الدخول:* `{trade['entry']:,.4f}`\n"
                    f"• *سعر الإغلاق (الهدف):* `{trade['tp']:,.4f}`"
                )
            elif latest_high >= trade["sl"]:
                closed = True
                status_msg = (
                    f"🔻 *تم إغلاق صفقة خاسرة (Stop Loss)* 🔴\n"
                    f"• *الرمز:* `{symbol}`\n"
                    f"• *نوع الصفقة:* `بيع (SELL)`\n"
                    f"• *سعر الدخول:* `{trade['entry']:,.4f}`\n"
                    f"• *سعر الإغلاق (الوقف):* `{trade['sl']:,.4f}`"
                )

        if closed:
            send_telegram_message(status_msg)
            print(f"✅ تم إغلاق وتنبيه صفقة {symbol}")
        else:
            remaining_trades.append(trade)

    active_trades = remaining_trades


# ==================== تحليل ومراقبة الفرص الجديد ====================
def process_symbol(symbol):
    global active_trades

    # تجنب تكرار فتح نفس العملة إذا كانت مفتوحة حالياً
    if any(t["symbol"] == symbol for t in active_trades):
        return

    df = get_klines(symbol, limit=600)
    if df is None or len(df) < 205:
        return

    df["ema200"] = calculate_ema(df["close"], 200)
    df["macd"], df["signal"] = calculate_macd(df["close"])

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    buy_signal = (
        (curr["close"] > curr["ema200"])
        and (prev["macd"] < prev["signal"])
        and (curr["macd"] > curr["signal"])
        and (curr["macd"] < 0)
    )

    sell_signal = (
        (curr["close"] < curr["ema200"])
        and (prev["macd"] > prev["signal"])
        and (curr["macd"] < curr["signal"])
        and (curr["macd"] > 0)
    )

    if buy_signal or sell_signal:
        signal_type = "BUY" if buy_signal else "SELL"
        entry_p = curr["close"]

        if buy_signal:
            sl = df["low"].iloc[-6:-1].min()
            risk = entry_p - sl
            if risk <= 0:
                return
            tp = entry_p + (risk * 2)
        else:
            sl = df["high"].iloc[-6:-1].max()
            risk = sl - entry_p
            if risk <= 0:
                return
            tp = entry_p - (risk * 2)

        # إضافة الصفقة إلى قائمة المراقبة الحية
        new_trade = {
            "symbol": symbol,
            "type": signal_type,
            "entry": entry_p,
            "sl": sl,
            "tp": tp,
        }
        active_trades.append(new_trade)

        # حساب الباك تيست التاريخي
        trades = backtest_last_20_trades(df, symbol)
        wins = sum(1 for t in trades if t["result"] == "WIN")
        losses = sum(1 for t in trades if t["result"] == "LOSS")

        msg = (
            f"🚨 *إشارة تداول جديدة ({signal_type} {'🟢' if buy_signal else '🔴'})*\n"
            f"• *الرمز:* `{symbol}`\n"
            f"• *الفريم:* `{TIMEFRAME}`\n"
            f"• *سعر الدخول:* `{entry_p:,.4f}`\n"
            f"• *وقف الخسارة:* `{sl:,.4f}`\n"
            f"• *الهدف (1:2):* `{tp:,.4f}`\n\n"
            f"📊 *أداء آخر {len(trades)} صفقة تاريخية:*\n"
            f"✅ صفقات رابحة: `{wins}`\n"
            f"❌ صفقات خاسرة: `{losses}`"
        )

        img_buf = generate_stats_image(symbol, trades)

        if img_buf:
            send_telegram_photo(img_buf, caption=msg)
        else:
            send_telegram_message(msg)

        print(f"تم إرسال صفقة لـ {symbol}.")


# ==================== التشغيل الرئيسي المستمر ====================
def main():
    print("بدء تشغيل بوت التداول المستمر على السيرفر...")
    send_telegram_message(
        f"🚀 *تم تشغيل بوت التداول المباشر (عمل مستمر 24/7)*\n"
        f"• الفريم: `{TIMEFRAME}`\n"
        f"• نسبة العائد: `1:2`\n"
        f"• متابعة حية للصفقات: `مفعّلة ✅`"
    )

    symbols = get_all_usdt_symbols()
    print(f"تم العثور على {len(symbols)} زوج تداول.")

    while True:
        try:
            # 1. متابعة وفحص الصفقات المفتوحة
            check_active_trades()

            # 2. فحص جميع الأزواج للبحث عن فرص جديدة
            print("🔄 جاري فحص الأزواج للبحث عن فرص جديدة...")
            with ThreadPoolExecutor(max_workers=8) as executor:
                executor.map(process_symbol, symbols)

            print("انتظار 5 دقائق قبل الفحص والتحديث التالي...")
            time.sleep(300)

        except Exception as e:
            print(f"حدث خطأ غير متوقع: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
