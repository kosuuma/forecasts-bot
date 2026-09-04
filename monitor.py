"""
Дополнительный мониторинг:
1. Резкие движения цены (>PRICE_SPIKE_PCT за 5 минут) — отдельные алерты.
2. Определение исхода отправленных сигналов (win/loss) для подсчёта винрейта.
"""
import logging

import aiohttp

import config
from database import Database
from exchanges import fetch_klines

logger = logging.getLogger("monitor")

# Храним последнюю известную цену по каждой паре, чтобы считать движение за 5 минут
_last_prices: dict = {}


async def check_price_spikes(session: aiohttp.ClientSession, pairs: list) -> list:
    """
    Проверяет резкие движения цены за последние 5 минут по списку пар.
    Возвращает список алертов вида {"symbol": ..., "change_pct": ..., "price": ...}
    """
    alerts = []
    for symbol in pairs:
        try:
            df = await fetch_klines(session, symbol, "1m", exchange=config.DEFAULT_EXCHANGE, limit=6)
            if len(df) < 6:
                continue
            price_5m_ago = float(df["close"].iloc[0])
            price_now = float(df["close"].iloc[-1])
            change_pct = (price_now - price_5m_ago) / price_5m_ago * 100

            if abs(change_pct) >= config.PRICE_SPIKE_PCT:
                alerts.append({"symbol": symbol, "change_pct": round(change_pct, 2), "price": price_now})
        except Exception as e:
            logger.error(f"Ошибка проверки движения цены для {symbol}: {e}")
    return alerts


def format_spike_alert(alert: dict) -> str:
    direction = "🚀 РОСТ" if alert["change_pct"] > 0 else "🔻 ПАДЕНИЕ"
    return (
        "⚡ РЕЗКОЕ ДВИЖЕНИЕ ЦЕНЫ ⚡\n"
        f"🪙 {alert['symbol'][:-4]}/{alert['symbol'][-4:]}\n"
        f"{direction}: {alert['change_pct']:+.2f}% за 5 минут\n"
        f"💰 Текущая цена: {alert['price']}"
    )


async def resolve_pending_signals(session: aiohttp.ClientSession, db: Database):
    """
    Проверяет сигналы и определяет исход (win/loss/expired) по TP/SL уровням.
    Загружает свечи за время жизни сигнала и проверяет, какой уровень сработал раньше.
    """
    from datetime import datetime

    pending = await db.get_pending_signals()
    for sig in pending:
        try:
            # Сколько минут прошло с момента сигнала
            created = datetime.strptime(sig["created_at"], "%Y-%m-%d %H:%M:%S")
            now = datetime.utcnow()
            elapsed_minutes = (now - created).total_seconds() / 60

            # Если время жизни истекло — проверяем, был ли TP/SL за это время
            expiry = sig["expiry_minutes"] or 15

            # Загружаем свечи за всё время жизни сигнала
            limit_needed = int(expay // 1) + 2  # примерно по 1 свече в минуту (1m TF)
            if limit_needed > 500:
                limit_needed = 500

            df = await fetch_klines(session, sig["symbol"], "1m",
                                    exchange=config.DEFAULT_EXCHANGE, limit=limit_needed)
            if df.empty or len(df) < 2:
                continue

            entry_price = float(sig["price"])
            direction = sig["direction"]
            tp_price = sig.get("tp_price")
            sl_price = sig.get("sl_price")

            # Если нет TP/SL —fallback к старой логике
            if not tp_price or not sl_price:
                current_price = float(df["close"].iloc[-1])
                moved_up = current_price > entry_price
                outcome = "win" if (
                    (direction == "UP" and moved_up) or
                    (direction == "DOWN" and not moved_up)
                ) else "loss"
                await db.update_outcome(sig["id"], outcome)
                continue

            # Проверяем каждую свечу после сигнала — какой уровень сработал раньше
            outcome = None
            for _, candle in df.iterrows():
                high = float(candle["high"])
                low = float(candle["low"])

                if direction == "UP":
                    if high >= tp_price:
                        outcome = "win"
                        break
                    if low <= sl_price:
                        outcome = "loss"
                        break
                else:  # DOWN
                    if low <= tp_price:
                        outcome = "win"
                        break
                    if high >= sl_price:
                        outcome = "loss"
                        break

            # Если время вышло, а TP/SL не сработали —expired
            if outcome is None:
                if elapsed_minutes >= expiry:
                    outcome = "expired"
                else:
                    continue  # Ещё рано проверять, ждём

            await db.update_outcome(sig["id"], outcome)
            logger.info(f"Сигнал #{sig['id']} ({sig['symbol']} {direction}) → {outcome}")
        except Exception as e:
            logger.error(f"Ошибка определения исхода сигнала #{sig['id']}: {e}")
