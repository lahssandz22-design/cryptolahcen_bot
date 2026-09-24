import asyncio
import io
import os
import threading
import time
from flask import Flask
import matplotlib.pyplot as plt
import pandas as pd
import requests
import ta

# ==================== 1. سيرفر لإبقاء Render شغالاً ====================
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running smoothly on Render!"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# ==================== 2. إعدادات بوت التداول ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8617483405:AAGhNHH1A3X1twjDUU5fwdWr6rUYKMhc9gc")
CHAT_ID = os.environ.get("CHAT_ID", "7895743860")

TIMEFRAME = "4h"
RR_RATIO = 2.0
BATCH_SIZE = 20  # إرسال تقرير وصورة لكل 20 صفقة مغلقة

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
    "MATICUSDT",
    "LTCUSDT",
    "NEARUSDT",
    "APTUSDT",
    "TRXUSDT",
]


# ==================== 3. وظائف التلجرام ====================
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"خطأ في إرسال الرسالة: {e}")


def send_telegram_photo(photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {"photo": ("chart.png", photo_bytes, "image/png")}
    data = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"خطأ في إرسال الصورة: {e}")


# ==================== 4. التحليل والاختبار ====================
def fetch_klines(symbol, interval=TIMEFRAME, limit=500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
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
                "qav",
                "num_trades",
                "taker_base",
                "taker_quote",
                "ignore",
            ],
        )
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["open"] = df["open"].astype(float)
        return df
    except Exception as e:
        print(f"خطأ في جلب بيانات {symbol}: {e}")
        return None


def calculate_indicators(df):
    df["ema200"] = ta.trend.ema_indicator(close=df["close"], window=200)
    macd_ind = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd_line"] = macd_ind.macd()
    df["macd_signal"] = macd_ind.macd_signal()
    return df


def generate_and_send_batch_summary(trade_batch, batch_number):
    if not trade_batch:
        return

    wins = sum(1 for t in trade_batch if t["result"] == "WIN")
    losses = sum(1 for t in trade_batch if t["result"] == "LOSS")
    total = len(trade_batch)
    win_rate = (wins / total) * 100 if total > 0 else 0

    pnl_accumulative = [0]
    curr = 0
    for t in trade_batch:
        curr += t["pnl"]
        pnl_accumulative.append(curr)

    plt.figure(figsize=(8, 4.5))
    plt.plot(
        pnl_accumulative,
        marker="o",
        color="#2eb85c" if curr >= 0 else "#e55353",
        linewidth=2,
    )
    plt.title(f"Batch #{batch_number} Performance: {total} Trades (WinRate: {win_rate:.1f}%)")
    plt.xlabel("Trade Number in Batch")
    plt.ylabel("Cumulative Profit (R)")
    plt.grid(True, linestyle="--", alpha=0.6)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    plt.close()

    caption = (
        f"📊 *تقرير أداء الدفعة رقم ({batch_number})*\n"
        f"_(لعزلة تامة لـ {total} صفقات مغلقة)_ \n\n"
        f"• إجمالي صفقات هذه الدفعة: `{total}`\n"
        f"• ✅ الصفقات الرابحة: `{wins}`\n"
        f"• ❌ الصفقات الخاسرة: `{losses}`\n"
        f"• 🎯 نسبة النجاح: `{win_rate:.1f}%`\n"
        f"• 💰 صافي الربح: `{curr:+.1f}R`"
    )

    send_telegram_photo(buf.getvalue(), caption=caption)


# ==================== 5. الحلقة الرئيسية ====================
async def bot_loop():
    send_telegram_message("🚀 *تم تشغيل بوت تتبع الصفقات وتقديم التقارير الدورية (كل 20 صفقة)*")

    active_live_trades = []
    current_batch_trades = []
    batch_count = 1

    while True:
        for sym in SYMBOLS:
            df = fetch_klines(sym, limit=250)
            if df is None:
                continue

            df = calculate_indicators(df)
            row = df.iloc[-1]
            prev_row = df.iloc[-2]

            # 1. متابعة الصفقات المفتوحة للتحقق من وصولها للهدف أو الوقف
            for trade in active_live_trades[:]:
                if trade["symbol"] == sym:
                    if trade["type"] == "BUY":
                        if row["high"] >= trade["tp"]:
                            msg = (
                                f"🎉 *إغلاق صفقة رابحة (WIN)*\n"
                                f"• الرمز: `{sym}` | النوع: `BUY`\n"
                                f"• النتيجة: `✅ حققت الهدف (+2R)`"
                            )
                            send_telegram_message(msg)
                            closed_trade = {**trade, "result": "WIN", "pnl": 2.0}
                            current_batch_trades.append(closed_trade)
                            active_live_trades.remove(trade)

                        elif row["low"] <= trade["sl"]:
                            msg = (
                                f"🛑 *إغلاق صفقة خاسرة (LOSS)*\n"
                                f"• الرمز: `{sym}` | النوع: `BUY`\n"
                                f"• النتيجة: `❌ ضربت الوقف (-1R)`"
                            )
                            send_telegram_message(msg)
                            closed_trade = {**trade, "result": "LOSS", "pnl": -1.0}
                            current_batch_trades.append(closed_trade)
                            active_live_trades.remove(trade)

                    elif trade["type"] == "SELL":
                        if row["low"] <= trade["tp"]:
                            msg = (
                                f"🎉 *إغلاق صفقة رابحة (WIN)*\n"
                                f"• الرمز: `{sym}` | النوع: `SELL`\n"
                                f"• النتيجة: `✅ حققت الهدف (+2R)`"
                            )
                            send_telegram_message(msg)
                            closed_trade = {**trade, "result": "WIN", "pnl": 2.0}
                            current_batch_trades.append(closed_trade)
                            active_live_trades.remove(trade)

                        elif row["high"] >= trade["sl"]:
                            msg = (
                                f"🛑 *إغلاق صفقة خاسرة (LOSS)*\n"
                                f"• الرمز: `{sym}` | النوع: `SELL`\n"
                                f"• النتيجة: `❌ ضربت الوقف (-1R)`"
                            )
                            send_telegram_message(msg)
                            closed_trade = {**trade, "result": "LOSS", "pnl": -1.0}
                            current_batch_trades.append(closed_trade)
                            active_live_trades.remove(trade)

                    # فحص هل اكتملت الدفعة الحالية (20 صفقة)؟
                    if len(current_batch_trades) >= BATCH_SIZE:
                        send_telegram_message(f"📈 *اكتملت الدفعة رقم ({batch_count}) بـ 20 صفقة مغلقة. جاري إعداد التقرير...*")
                        generate_and_send_batch_summary(current_batch_trades, batch_count)
                        # تصفير القائمة لبدء دفعة جديدة كلياً (بدون تكرار)
                        current_batch_trades = []
                        batch_count += 1

            # 2. البحث عن صفقات جديدة بشرط عدم وجود صفقة مفتوحة على نفس العملة
            is_already_open = any(t["symbol"] == sym for t in active_live_trades)

            if not is_already_open:
                buy_signal = (
                    (row["close"] > row["ema200"])
                    and (prev_row["macd_line"] < prev_row["macd_signal"])
                    and (row["macd_line"] > row["macd_signal"])
                    and (row["macd_line"] < 0)
                )

                sell_signal = (
                    (row["close"] < row["ema200"])
                    and (prev_row["macd_line"] > prev_row["macd_signal"])
                    and (row["macd_line"] < row["macd_signal"])
                    and (row["macd_line"] > 0)
                )

                if buy_signal or sell_signal:
                    trade_type = "BUY" if buy_signal else "SELL"
                    entry = row["close"]

                    if buy_signal:
                        sl = row["low"]
                        risk = entry - sl if (entry - sl) > 0 else entry * 0.01
                        tp = entry + (risk * RR_RATIO)
                    else:
                        sl = row["high"]
                        risk = sl - entry if (sl - entry) > 0 else entry * 0.01
                        tp = entry - (risk * RR_RATIO)

                    new_trade = {
                        "symbol": sym,
                        "type": trade_type,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                    }
                    active_live_trades.append(new_trade)

                    icon = "🟢" if trade_type == "BUY" else "🔴"
                    send_telegram_message(
                        f"🚨 *إشارة تداول جديدة ({trade_type} {icon})*\n"
                        f"• الرمز: `{sym}` | الدخول: `{entry:.4f}`\n"
                        f"• الوقف: `{sl:.4f}` | الهدف: `{tp:.4f}`\n"
                        f"📊 الحالية في الدفعة: `{len(current_batch_trades)}/{BATCH_SIZE}`"
                    )

        await asyncio.sleep(600)  # الفحص كل 10 دقائق


def start_bot_thread():
    asyncio.run(bot_loop())


if __name__ == "__main__":
    t = threading.Thread(target=start_bot_thread)
    t.start()
    run_flask()
