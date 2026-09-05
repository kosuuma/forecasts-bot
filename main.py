"""
Точка входа приложения.
Запускает Telegram-бота (long polling) и фоновый планировщик,
который каждые SCAN_INTERVAL_MINUTES анализирует все пары и
рассылает сигналы подписчикам.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from database import Database
from bot import build_dispatcher
from exchanges import fetch_klines, fetch_funding_rate, fetch_orderbook_depth
from signals import analyze, format_signal_message
from monitor import check_price_spikes, format_spike_alert, resolve_pending_signals

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")

db = Database()

# Хранилище последнего известного статуса биржи
_exchange_status = {"is_open": True, "notified": False}


async def check_exchange_status(session: aiohttp.ClientSession) -> bool:
    """
    Проверяет доступность биржи, пытаясь получить тикер.
    Возвращает True если биржа доступна, False если нет.
    """
    try:
        from exchanges import fetch_ticker_24h
        ticker = await fetch_ticker_24h(session, "BTCUSDT", exchange=config.DEFAULT_EXCHANGE)
        return ticker is not None
    except Exception:
        return False


async def scan_and_notify(bot: Bot):
    """
    Основной цикл автоматического анализа:
    для каждой отслеживаемой пары считает сигнал и рассылает
    подписчикам, чьи настройки (таймфрейм, min_confidence) подходят.
    Соблюдает rate limiting (SIGNAL_COOLDOWN_MINUTES на пару).
    """
    logger.info("Запуск планового сканирования рынка...")
    pairs = await db.get_enabled_pairs()
    subscribers = await db.get_active_subscribers()

    if not subscribers:
        logger.info("Нет активных подписчиков, сканирование пропущено.")
        return

    async with aiohttp.ClientSession() as session:
        # Проверяем статус биржи
        exchange_open = await check_exchange_status(session)

        if not exchange_open:
            if _exchange_status["is_open"]:
                # Биржа только что закрылась — уведомляем подписчиков
                _exchange_status["is_open"] = False
                _exchange_status["notified"] = False
                if not _exchange_status["notified"]:
                    for sub in subscribers:
                        try:
                            await bot.send_message(
                                sub["chat_id"],
                                "⚠️ Биржа недоступна или на техническом обслуживании.\n"
                                "Сигналы будут возобновлены после восстановления."
                            )
                        except Exception as e:
                            logger.error(f"Не удалось отправить уведомление {sub['chat_id']}: {e}")
                    _exchange_status["notified"] = True
            logger.warning("Биржа недоступна, сканирование пропущено.")
            return

        if not _exchange_status["is_open"]:
            # Биржа восстановилась
            _exchange_status["is_open"] = True
            _exchange_status["notified"] = False
            for sub in subscribers:
                try:
                    await bot.send_message(
                        sub["chat_id"],
                        "✅ Биржа снова доступна! Сигналы возобновлены."
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление {sub['chat_id']}: {e}")

    async with aiohttp.ClientSession() as session:
        # Собираем уникальные таймфреймы, которые реально нужны подписчикам
        needed_timeframes = {s["timeframe"] for s in subscribers} or {config.DEFAULT_TIMEFRAME}

        for symbol in pairs:
            # Получаем funding rate и orderbook один раз на пару
            funding_rate = None
            orderbook = None
            try:
                funding_rate = await fetch_funding_rate(session, symbol, exchange=config.DEFAULT_EXCHANGE)
            except Exception as e:
                logger.debug(f"Не удалось получить funding rate для {symbol}: {e}")
            try:
                orderbook = await fetch_orderbook_depth(session, symbol, exchange=config.DEFAULT_EXCHANGE)
            except Exception as e:
                logger.debug(f"Не удалось получить orderbook для {symbol}: {e}")

            # Кэш для данных старшего TF (чтобы не загружать повторно)
            higher_tf_cache = {}

            for tf in needed_timeframes:
                try:
                    last_signal_time = await db.get_last_signal_time(symbol)
                    if last_signal_time and datetime.utcnow() - last_signal_time < timedelta(
                        minutes=config.SIGNAL_COOLDOWN_MINUTES
                    ):
                        continue  # rate limit: слишком рано для нового сигнала по этой паре

                    df = await fetch_klines(session, symbol, tf, exchange=config.DEFAULT_EXCHANGE, limit=200)

                    # Загружаем данные старшего TF для multi-timeframe анализа
                    higher_tf = config.TF_HIERARCHY.get(tf)
                    df_higher = None
                    if higher_tf:
                        if higher_tf in higher_tf_cache:
                            df_higher = higher_tf_cache[higher_tf]
                        else:
                            try:
                                df_higher = await fetch_klines(session, symbol, higher_tf,
                                                               exchange=config.DEFAULT_EXCHANGE, limit=200)
                                higher_tf_cache[higher_tf] = df_higher
                            except Exception as e:
                                logger.debug(f"Не удалось получить {higher_tf} для {symbol}: {e}")

                    signal = analyze(df, symbol, tf, funding_rate=funding_rate, orderbook=orderbook,
                                     df_higher_tf=df_higher)
                    if not signal:
                        continue

                    await db.save_signal(signal)
                    message_text = format_signal_message(signal)

                    for sub in subscribers:
                        if sub["timeframe"] != tf:
                            continue
                        if signal.strength_pct < sub["min_confidence"]:
                            continue
                        try:
                            await bot.send_message(sub["chat_id"], message_text)
                        except Exception as e:
                            logger.error(f"Не удалось отправить сигнал пользователю {sub['chat_id']}: {e}")

                except Exception as e:
                    logger.error(f"Ошибка анализа {symbol} [{tf}]: {e}")

        # Проверка резких движений цены
        try:
            spikes = await check_price_spikes(session, pairs)
            for alert in spikes:
                text = format_spike_alert(alert)
                for sub in subscribers:
                    try:
                        await bot.send_message(sub["chat_id"], text)
                    except Exception as e:
                        logger.error(f"Не удалось отправить алерт пользователю {sub['chat_id']}: {e}")
        except Exception as e:
            logger.error(f"Ошибка проверки резких движений цены: {e}")

        # Определение исходов старых сигналов (для винрейта)
        try:
            await resolve_pending_signals(session, db)
        except Exception as e:
            logger.error(f"Ошибка определения исходов сигналов: {e}")

    logger.info("Плановое сканирование завершено.")


async def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не задан! Укажите его в файле .env")
        return

    await db.connect()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    # Dependency injection: передаём db во все хендлеры через workflow_data
    dp["db"] = db

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scan_and_notify,
        "interval",
        minutes=config.SCAN_INTERVAL_MINUTES,
        args=[bot],
        id="market_scan",
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"Планировщик запущен: анализ каждые {config.SCAN_INTERVAL_MINUTES} мин.")

    try:
        logger.info("Бот запущен (long polling)...")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем.")
