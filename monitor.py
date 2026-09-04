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
    Проверяет сигналы старше 15 минут и определяет исход (win/loss)
    сравнивая цену на момент проверки с ценой сигнала.
    """
    pending = await db.get_pending_signals(older_than_minutes=15)
    for sig in pending:
        try:
            df = await fetch_klines(session, sig["symbol"], "1m", exchange=config.DEFAULT_EXCHANGE, limit=1)
            if df.empty:
                continue
            current_price = float(df["close"].iloc[-1])
            entry_price = float(sig["price"])

            moved_up = current_price > entry_price
            outcome = "win" if (
                (sig["direction"] == "UP" and moved_up) or
                (sig["direction"] == "DOWN" and not moved_up)
            ) else "loss"

            await db.update_outcome(sig["id"], outcome)
            logger.info(f"Сигнал #{sig['id']} ({sig['symbol']} {sig['direction']}) закрыт как {outcome}")
        except Exception as e:
            logger.error(f"Ошибка определения исхода сигнала #{sig['id']}: {e}")
