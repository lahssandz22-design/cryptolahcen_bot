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
MAX_TOTAL_TRADES = 30
HISTORY_TRADES_COUNT = 20

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

total_closed_trades = []


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
    # حساب EMA 200 باستخدام مكتبة ta
    df["ema200"] = ta.trend.ema_indicator(close=df["close"], window=200)
    
    # حساب MACD باستخدام مكتبة ta
    macd_ind = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd_line"] = macd_ind.macd()
    df["macd_signal"] = macd_ind.macd_signal()
    
    return df


def run_backtest_for_symbol(symbol):
    df = fetch_klines(symbol, limit=500)
    if df is None or len(df) < 250:
        return []

    df = calculate_indicators(df)
    trades = []
    in_trade = False
    trade_detail = {}

    for i in range(201, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]

        if not in_trade:
            buy_cond = (
                (row["close"] > row["ema200"])
                and (prev_row["macd_line"] < prev_row["macd_signal"])
                and (row["macd_line"] > row["macd_signal"])
                and (row["macd_line"] < 0)
            )

            sell_cond = (
                (row["close"] < row["ema200"])
                and (prev_row["macd_line"] > prev_row["macd_signal"])
                and (row["macd_line"] < row["macd_signal"])
                and (row["macd_line"] > 0)
            )

            if buy_cond:
                entry = row["close"]
                sl = row["low"]
                risk = entry - sl if (entry - sl) > 0 else entry * 0.01
                tp = entry + (risk * RR_RATIO)
                in_trade = True
                trade_detail = {
                    "symbol": symbol,
                    "type": "BUY",
                    "entry": entry,
                    "tp": tp,
                    "sl": sl,
                }

            elif sell_cond:
                entry = row["close"]
                sl = row["high"]
                risk = sl - entry if (sl - entry) > 0 else entry * 0.01
                tp = entry - (risk * RR_RATIO)
                in_trade = True
                trade_detail = {
                    "symbol": symbol,
                    "type": "SELL",
                    "entry": entry,
                    "tp": tp,
                    "sl": sl,
                }

        else:
            if trade_detail["type"] == "BUY":
                if row["high"] >= trade_detail["tp"]:
                    trades.append(
                        {**trade_detail, "result": "WIN", "pnl": +2.0}
                    )
                    in_trade = False
                elif row["low"] <= trade_detail["sl"]:
                    trades.append(
                        {**trade_detail, "result": "LOSS", "pnl": -1.0}
                    )
                    in_trade = False

            elif trade_detail["type"] == "SELL":
                if row["low"] <= trade_detail["tp"]:
                    trades.append(
                        {**trade_detail, "result": "WIN", "pnl": +2.0}
                    )
                    in_trade = False
                elif row["high"] >= trade_detail["sl"]:
                    trades.append(
                        {**trade_detail, "result": "LOSS", "pnl": -1.0}
                    )
                    in_trade = False

    return trades


def generate_and_send_summary():
    global total_closed_trades
    if not total_closed_trades:
        return

    wins = sum(1 for t in total_closed_trades if t["result"] == "WIN")
    losses = sum(1 for t in total_closed_trades if t["result"] == "LOSS")
    total = len(total_closed_trades)
    win_rate = (wins / total) * 100 if total > 0 else 0

    pnl_accumulative = [0]
    curr = 0
    for t in total_closed_trades:
        curr += t["pnl"]
        pnl_accumulative.append(curr)

    plt.figure(figsize=(8, 4.5))
    plt.plot(
        pnl_accumulative,
        marker="o",
        color="#2eb85c" if curr >= 0 else "#e55353",
        linewidth=2,
    )
    plt.title(
        f"Backtest Performance: {total} Trades (WinRate: {win_rate:.1f}%)"
    )
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative Profit (R)")
    plt.grid(True, linestyle="--", alpha=0.6)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    plt.close()

    caption = (
        f"📊 *نتائج إحصائيات استراتيجية MACD + EMA200*\n\n"
        f"إجمالي الصفقات: `{total}`\n"
        f"✅ الصفقات الرابحة: `{wins}`\n"
        f"❌ الصفقات الخاسرة: `{losses}`\n"
        f"🎯 نسبة النجاح: `{win_rate:.1f}%`\n"
        f"💰 صافي الربح: `{curr:+.1f}R`"
    )

    send_telegram_photo(buf.getvalue(), caption=caption)


# ==================== 5. الحلقة الرئيسية ====================
async def bot_loop():
    global total_closed_trades
    send_telegram_message(
        "🚀 *تم تشغيل بوت استراتيجية MACD + EMA200 على Render بنجاح!*"
    )

    all_backtest_trades = []
    for sym in SYMBOLS:
        t_list = run_backtest_for_symbol(sym)
        all_backtest_trades.extend(t_list)
        if len(all_backtest_trades) >= HISTORY_TRADES_COUNT:
            break

    total_closed_trades = all_backtest_trades[:HISTORY_TRADES_COUNT]

    for idx, tr in enumerate(total_closed_trades, 1):
        msg = (
            f"📜 *صفقة تاريخية مغلقة (#{idx})*\n"
            f"العملة: `{tr['symbol']}` | النوع: `{tr['type']}`\n"
            f"النتيجة: `{'✅ WIN (+2R)' if tr['result'] == 'WIN' else '❌ LOSS (-1R)'}`"
        )
        send_telegram_message(msg)
        await asyncio.sleep(0.5)

    generate_and_send_summary()

    send_telegram_message("👀 البوت الآن في وضع المراقبة اللحظية...")

    while len(total_closed_trades) < MAX_TOTAL_TRADES:
        for sym in SYMBOLS:
            df = fetch_klines(sym, limit=250)
            if df is None:
                continue

            df = calculate_indicators(df)
            row = df.iloc[-1]
            prev_row = df.iloc[-2]

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
                msg = (
                    f"🚨 *إشارة جديدة على فريم 4h*\n\n"
                    f"العملة: `{sym}`\n"
                    f"النوع: `{trade_type}`\n"
                    f"سعر الدخول: `{entry}`"
                )
                send_telegram_message(msg)

        await asyncio.sleep(600)


def start_bot_thread():
    asyncio.run(bot_loop())


if __name__ == "__main__":
    t = threading.Thread(target=start_bot_thread)
    t.start()
    run_flask()
