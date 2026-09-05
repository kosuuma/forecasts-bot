"""
Telegram-бот на aiogram 3: команды, настройки, подписка на авто-сигналы.
"""
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from database import Database

logger = logging.getLogger("bot")

router = Router()


# ---------------------------------------------------------------------------
# Главное меню (ReplyKeyboard — всегда внизу)
# ---------------------------------------------------------------------------
def main_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с основными командами."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 Сигналы"),
                KeyboardButton(text="📈 Статистика"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="📋 Пары"),
            ],
            [
                KeyboardButton(text="✅ Подписаться"),
                KeyboardButton(text="❌ Отписаться"),
            ],
            [
                KeyboardButton(text="🔍 Проверить"),
                KeyboardButton(text="🔔 Алерты цены"),
            ],
        ],
        resize_keyboard=True,
    )


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, db: Database):
    text = (
        "👋 Привет! Я бот для анализа криптовалютного рынка.\n\n"
        "Я слежу за 20+ парами на нескольких таймфреймах и отправляю "
        "сигналы, когда совпадает несколько технических индикаторов.\n\n"
        "👇 Используй кнопки внизу для быстрого доступа:"
    )
    await message.answer(text, reply_markup=main_keyboard())


# ---------------------------------------------------------------------------
# ReplyKeyboard хендлеры (кнопки внизу)
# ---------------------------------------------------------------------------
@router.message(F.text == "📊 Сигналы")
async def btn_signals(message: Message, db: Database):
    await cmd_signals(message, db)


@router.message(F.text == "📈 Статистика")
async def btn_stats(message: Message, db: Database):
    await cmd_stats(message, db)


@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message, db: Database):
    await cmd_settings(message, db)


@router.message(F.text == "📋 Пары")
async def btn_pairs(message: Message, db: Database):
    await cmd_pairs(message, db)


@router.message(F.text == "✅ Подписаться")
async def btn_subscribe(message: Message, db: Database):
    await cmd_subscribe(message, db)


@router.message(F.text == "❌ Отписаться")
async def btn_unsubscribe(message: Message, db: Database):
    await cmd_unsubscribe(message, db)


@router.message(F.text == "🔔 Алерты цены")
async def btn_toggle_price_alerts(message: Message, db: Database):
    chat_id = message.chat.id
    settings = await db.get_settings(chat_id)
    new_value = not settings["price_alerts"]
    await db.update_settings(chat_id, price_alerts=int(new_value))
    if new_value:
        await message.answer("🔔 Алерты о движении цены включены!", reply_markup=main_keyboard())
    else:
        await message.answer("🔕 Алерты о движении цены отключены.", reply_markup=main_keyboard())


# ---------------------------------------------------------------------------
# /subscribe /unsubscribe
# ---------------------------------------------------------------------------
@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, db: Database):
    chat_id = message.chat.id
    await db.subscribe(chat_id)
    await message.answer(
        "✅ Вы подписались на автоматические сигналы.\n"
        "Настроить таймфрейм и порог уверенности можно через ⚙️ Настройки.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, db: Database):
    chat_id = message.chat.id
    await db.unsubscribe(chat_id)
    await message.answer(
        "🔕 Вы отписались от автоматических сигналов.",
        reply_markup=main_keyboard(),
    )


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------
def settings_keyboard(current_tf: str, current_conf: int, subscribed: bool, price_alerts: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Таймфреймы
    for tf in config.TIMEFRAMES:
        label = f"✅ {tf}" if tf == current_tf else tf
        builder.button(text=label, callback_data=f"set_tf:{tf}")
    builder.adjust(len(config.TIMEFRAMES))

    # Уверенность — с галочкой
    conf_builder = InlineKeyboardBuilder()
    for conf in (0, 25, 40, 60):
        label = f"✅ {conf}%+" if conf == current_conf else f"{conf}%+"
        conf_builder.button(text=label, callback_data=f"set_conf:{conf}")
    conf_builder.adjust(4)

    # Кнопки toggle
    sub_builder = InlineKeyboardBuilder()
    sub_label = "🔕 Отписаться" if subscribed else "🔔 Подписаться"
    sub_builder.button(text=sub_label, callback_data="toggle_sub")

    alert_label = "🔕 Выкл алерты цены" if price_alerts else "🔔 Вкл алерты цены"
    sub_builder.button(text=alert_label, callback_data="toggle_alerts")
    sub_builder.adjust(2)

    builder.attach(conf_builder)
    builder.attach(sub_builder)
    return builder.as_markup()


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database):
    chat_id = message.chat.id
    settings = await db.get_settings(chat_id)
    text = (
        "⚙️ Настройки\n\n"
        f"Таймфрейм: {settings['timeframe']}\n"
        f"Мин. уверенность: {settings['min_confidence']}%\n"
        f"Подписка: {'включена ✅' if settings['subscribed'] else 'выключена ❌'}\n"
        f"Алерты цены: {'включены ✅' if settings['price_alerts'] else 'выключены ❌'}\n\n"
        "Выберите таймфрейм и минимальную уверенность сигнала:"
    )
    await message.answer(
        text,
        reply_markup=settings_keyboard(
            settings["timeframe"],
            settings["min_confidence"],
            settings["subscribed"],
            settings["price_alerts"],
        ),
    )


@router.callback_query(F.data.startswith("set_tf:"))
async def cb_set_timeframe(query: CallbackQuery, db: Database):
    tf = query.data.split(":", 1)[1]
    chat_id = query.message.chat.id
    await db.update_settings(chat_id, timeframe=tf)
    await query.answer(f"Таймфрейм установлен: {tf}")
    settings = await db.get_settings(chat_id)
    try:
        await query.message.edit_reply_markup(
            reply_markup=settings_keyboard(
                settings["timeframe"],
                settings["min_confidence"],
                settings["subscribed"],
                settings["price_alerts"],
            )
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("set_conf:"))
async def cb_set_confidence(query: CallbackQuery, db: Database):
    conf = int(query.data.split(":", 1)[1])
    chat_id = query.message.chat.id
    await db.update_settings(chat_id, min_confidence=conf)
    await query.answer(f"Минимальная уверенность: {conf}%")
    settings = await db.get_settings(chat_id)
    try:
        await query.message.edit_reply_markup(
            reply_markup=settings_keyboard(
                settings["timeframe"],
                settings["min_confidence"],
                settings["subscribed"],
                settings["price_alerts"],
            )
        )
    except Exception:
        pass


@router.callback_query(F.data == "toggle_sub")
async def cb_toggle_subscription(query: CallbackQuery, db: Database):
    chat_id = query.message.chat.id
    settings = await db.get_settings(chat_id)
    if settings["subscribed"]:
        await db.unsubscribe(chat_id)
        await query.answer("🔕 Подписка отключена")
    else:
        await db.subscribe(chat_id)
        await query.answer("🔔 Подписка включена")
    settings = await db.get_settings(chat_id)
    try:
        await query.message.edit_reply_markup(
            reply_markup=settings_keyboard(
                settings["timeframe"],
                settings["min_confidence"],
                settings["subscribed"],
                settings["price_alerts"],
            )
        )
    except Exception:
        pass


@router.callback_query(F.data == "toggle_alerts")
async def cb_toggle_price_alerts(query: CallbackQuery, db: Database):
    chat_id = query.message.chat.id
    settings = await db.get_settings(chat_id)
    new_value = not settings["price_alerts"]
    await db.update_settings(chat_id, price_alerts=int(new_value))
    if new_value:
        await query.answer("🔔 Алерты цены включены")
    else:
        await query.answer("🔕 Алерты цены отключены")
    settings = await db.get_settings(chat_id)
    try:
        await query.message.edit_reply_markup(
            reply_markup=settings_keyboard(
                settings["timeframe"],
                settings["min_confidence"],
                settings["subscribed"],
                settings["price_alerts"],
            )
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# /pairs
# ---------------------------------------------------------------------------
@router.message(Command("pairs"))
async def cmd_pairs(message: Message, db: Database):
    pairs = await db.get_all_pairs()
    enabled = [p["symbol"] for p in pairs if p["enabled"]]
    text = "📋 Отслеживаемые пары:\n\n" + ", ".join(
        f"{s[:-4]}/{s[-4:]}" for s in enabled
    )
    await message.answer(text, reply_markup=main_keyboard())


# ---------------------------------------------------------------------------
# /signals — последние 10 сигналов
# ---------------------------------------------------------------------------
@router.message(Command("signals"))
async def cmd_signals(message: Message, db: Database):
    recent = await db.get_recent_signals(limit=10)
    if not recent:
        await message.answer("Пока нет истории сигналов.", reply_markup=main_keyboard())
        return

    lines = ["📜 Последние 10 сигналов:\n"]
    outcome_icons = {"win": "🟢", "loss": "🔴", "pending": "⏳", "expired": "⚪"}
    for s in recent:
        arrow = "▲" if s["direction"] == "UP" else "▼"
        icon = outcome_icons.get(s["outcome"], "⏳")
        pair = f"{s['symbol'][:-4]}/{s['symbol'][-4:]}"
        lines.append(
            f"{icon} {pair} {arrow} {s['timeframe']} "
            f"{s['strength_pct']}% | {s['created_at']}"
        )
    await message.answer("\n".join(lines), reply_markup=main_keyboard())


# ---------------------------------------------------------------------------
# /stats — статистика с выбором периода
# ---------------------------------------------------------------------------
def stats_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 День", callback_data="stats:1")
    builder.button(text="📅 Неделя", callback_data="stats:7")
    builder.button(text="📅 Месяц", callback_data="stats:30")
    builder.button(text="📅 Всё время", callback_data="stats:999")
    builder.adjust(4)
    return builder.as_markup()


def winrate_bar(winrate: float) -> str:
    """Визуальный бар винрейта."""
    filled = round(winrate / 5)
    empty = 20 - filled
    if winrate >= 70:
        color = "🟩"
    elif winrate >= 50:
        color = "🟨"
    else:
        color = "🟥"
    return color * filled + "⬜️" * empty


async def _build_stats_text(db: Database, days: int) -> str:
    stats = await db.get_stats(days=days)
    streak = await db.get_streak(days=days)
    by_pair = await db.get_stats_by_pair(days=days)
    by_tf = await db.get_stats_by_timeframe(days=days)

    period_name = {1: "День", 7: "Неделя", 30: "Месяц", 999: "Всё время"}.get(days, f"{days}д")

    # Стрик
    streak_text = "—"
    if streak["count"] > 0:
        if streak["type"] == "win":
            streak_text = f"🔥 {streak['count']} побед подряд"
        else:
            streak_text = f"💔 {streak['count']} поражений подряд"

    # Бар винрейта
    bar = winrate_bar(stats["winrate"])

    lines = [
        f"📊 Статистика — {period_name}\n",
        f"Winrate: {stats['winrate']}%",
        bar,
        "",
        f"📈 Всего сигналов: {stats['total_signals']}",
        f"✅ Побед: {stats['wins']}",
        f"❌ Поражений: {stats['losses']}",
        f"⏳ В ожидании: {stats['pending']}",
        f"⏰ Истекло: {stats['expired']}",
        f"🎲 Серия: {streak_text}",
    ]

    # По таймфреймам
    if by_tf:
        lines.append("\n⏱ По таймфреймам:")
        for t in by_tf[:5]:
            emoji = "🟩" if t["winrate"] >= 60 else "🟨" if t["winrate"] >= 50 else "🟥"
            lines.append(f"  {emoji} {t['timeframe']}: {t['winrate']}% ({t['wins']}W/{t['losses']}L)")

    # Топ пар
    if by_pair:
        lines.append("\n🏆 Топ пар:")
        sorted_pairs = sorted(by_pair, key=lambda x: x["winrate"], reverse=True)
        for p in sorted_pairs[:5]:
            emoji = "🥇" if p == sorted_pairs[0] else "🥈" if p == sorted_pairs[1] else "🥉" if p == sorted_pairs[2] else "  "
            lines.append(f"  {emoji} {p['symbol'][:-4]}/{p['symbol'][-4:]}: {p['winrate']}% ({p['wins']}W/{p['losses']}L)")

    # ML модель
    from ml import load_model
    ml_model = load_model()
    if ml_model:
        lines.append(f"\n🤖 ML: {ml_model['model_name']} ({ml_model['accuracy']:.0%})")
    else:
        lines.append("\n🤖 ML: не обучена")

    return "\n".join(lines)


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    text = await _build_stats_text(db, days=7)
    await message.answer(text, reply_markup=stats_keyboard())


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats(query: CallbackQuery, db: Database):
    days = int(query.data.split(":")[1])
    text = await _build_stats_text(db, days=days)
    await query.message.edit_text(text, reply_markup=stats_keyboard())
    await query.answer()


@router.message(Command("train"))
async def cmd_train(message: Message, db: Database):
    from ml import train_model, MODEL_PATH
    from indicators import calculate_all
    from exchanges import fetch_klines
    from datetime import datetime, timedelta, timezone

    await message.answer("🔄 Собираю данные для обучения ML...")

    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
    cursor = await db._conn.execute(
        """SELECT symbol, timeframe, direction, strength_label, strength_pct,
                  price, created_at, outcome
           FROM signals_history
           WHERE outcome != 'pending' AND created_at >= ?""",
        (cutoff,),
    )
    rows = await cursor.fetchall()
    cols = ["symbol", "timeframe", "direction", "strength_label", "strength_pct",
            "price", "created_at", "outcome"]

    import pandas as pd
    signals_df = pd.DataFrame([dict(zip(cols, r)) for r in rows])

    if len(signals_df) < 15:
        await message.answer(f"⚠️ Недостаточно данных для обучения: {len(signals_df)} сигналов (нужно минимум 15)")
        return

    unique_pairs = signals_df[["symbol", "timeframe"]].drop_duplicates()
    indicator_dfs = []

    async with __import__("aiohttp").ClientSession() as session:
        for _, row in unique_pairs.iterrows():
            symbol = row["symbol"]
            tf = row["timeframe"]
            try:
                df_kl = await fetch_klines(session, symbol, tf, exchange=config.DEFAULT_EXCHANGE, limit=300)
                if df_kl is not None and len(df_kl) >= 50:
                    df_kl = calculate_all(df_kl)
                    df_kl["symbol"] = symbol
                    df_kl["timeframe"] = tf
                    indicator_dfs.append(df_kl)
            except Exception as e:
                logger.debug(f"Не удалось получить данные для {symbol} {tf}: {e}")

    if not indicator_dfs:
        await message.answer("❌ Не удалось загрузить данные для обучения.", reply_markup=main_keyboard())
        return

    all_indicators = pd.concat(indicator_dfs, ignore_index=True)

    merged_rows = []
    for _, sig in signals_df.iterrows():
        mask = (all_indicators["symbol"] == sig["symbol"]) & (all_indicators["timeframe"] == sig["timeframe"])
        ind = all_indicators[mask]
        if ind.empty:
            continue
        try:
            sig_time = datetime.strptime(sig["created_at"], "%Y-%m-%d %H:%M:%S")
            ind_copy = ind.copy()
            ind_dt = pd.to_datetime(ind_copy["open_time"], unit="ms", utc=True).dt.tz_localize(None)
            ind_copy["_diff"] = abs((ind_dt - sig_time).dt.total_seconds())
            rsi_col = ind_copy["rsi"] if "rsi" in ind_copy.columns else pd.Series(dtype=float)
            valid_mask = rsi_col.notna() if not rsi_col.empty else pd.Series([False]*len(ind_copy))
            if valid_mask.any():
                valid_ind = ind_copy[valid_mask]
                closest = valid_ind.loc[valid_ind["_diff"].idxmin()]
                merged_rows.append(closest.to_dict() | {"outcome": sig["outcome"]})
        except Exception:
            continue

    if not merged_rows:
        await message.answer("❌ Не удалось сопоставить сигналы с индикаторами.", reply_markup=main_keyboard())
        return

    df_train = pd.DataFrame(merged_rows)

    result = train_model(df_train, min_samples=15)
    if result:
        await message.answer(
            f"✅ ML модель обучена!\n\n"
            f"📊 Модель: {result['model_name']}\n"
            f"🎯 Accuracy: {result['accuracy']:.0%}\n"
            f"  RandomForest: {result['rf_accuracy']:.0%}\n"
            f"  GradientBoosting: {result['gb_accuracy']:.0%}\n"
            f"📁 Сохранена: {MODEL_PATH}",
            reply_markup=main_keyboard(),
        )
    else:
        await message.answer("❌ Не удалось обучить модель. Проверьте логи.", reply_markup=main_keyboard())


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp
