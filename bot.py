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
    """Клавиатура с основными командами — не нужно набирать вручную."""
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


# ---------------------------------------------------------------------------
# /subscribe /unsubscribe
# ---------------------------------------------------------------------------
@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, db: Database):
    await db.subscribe(message.chat.id)
    await message.answer(
        "✅ Вы подписались на автоматические сигналы.\n"
        "Настроить таймфрейм и порог уверенности можно через ⚙️ Настройки.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, db: Database):
    await db.unsubscribe(message.chat.id)
    await message.answer(
        "🔕 Вы отписались от автоматических сигналов.",
        reply_markup=main_keyboard(),
    )


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------
def settings_keyboard(current_tf: str, current_conf: int, subscribed: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Таймфреймы
    for tf in config.TIMEFRAMES:
        label = f"✅ {tf}" if tf == current_tf else tf
        builder.button(text=label, callback_data=f"set_tf:{tf}")
    builder.adjust(len(config.TIMEFRAMES))

    # Уверенность — с галочкой
    conf_builder = InlineKeyboardBuilder()
    for conf in (50, 60, 70, 80):
        label = f"✅ {conf}%+" if conf == current_conf else f"{conf}%+"
        conf_builder.button(text=label, callback_data=f"set_conf:{conf}")
    conf_builder.adjust(4)

    # Кнопка подписки — toggle
    sub_builder = InlineKeyboardBuilder()
    sub_label = "🔕 Отписаться" if subscribed else "🔔 Подписаться"
    sub_builder.button(text=sub_label, callback_data="toggle_sub")

    builder.attach(conf_builder)
    builder.attach(sub_builder)
    return builder.as_markup()


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database):
    settings = await db.get_settings(message.chat.id)
    text = (
        "⚙️ Настройки\n\n"
        f"Таймфрейм: {settings['timeframe']}\n"
        f"Мин. уверенность: {settings['min_confidence']}%\n"
        f"Частота проверки: {settings['frequency_minutes']} мин\n"
        f"Подписка: {'включена ✅' if settings['subscribed'] else 'выключена ❌'}\n\n"
        "Выберите таймфрейм и минимальную уверенность сигнала:"
    )
    await message.answer(
        text,
        reply_markup=settings_keyboard(
            settings["timeframe"],
            settings["min_confidence"],
            settings["subscribed"],
        ),
    )


@router.callback_query(F.data.startswith("set_tf:"))
async def cb_set_timeframe(query: CallbackQuery, db: Database):
    tf = query.data.split(":", 1)[1]
    await db.update_settings(query.from_user.id, timeframe=tf)
    await query.answer(f"Таймфрейм установлен: {tf}")
    settings = await db.get_settings(query.from_user.id)
    await query.message.edit_reply_markup(
        reply_markup=settings_keyboard(
            settings["timeframe"],
            settings["min_confidence"],
            settings["subscribed"],
        )
    )


@router.callback_query(F.data.startswith("set_conf:"))
async def cb_set_confidence(query: CallbackQuery, db: Database):
    conf = int(query.data.split(":", 1)[1])
    await db.update_settings(query.from_user.id, min_confidence=conf)
    await query.answer(f"Минимальная уверенность: {conf}%")
    settings = await db.get_settings(query.from_user.id)
    await query.message.edit_reply_markup(
        reply_markup=settings_keyboard(
            settings["timeframe"],
            settings["min_confidence"],
            settings["subscribed"],
        )
    )


@router.callback_query(F.data == "toggle_sub")
async def cb_toggle_subscription(query: CallbackQuery, db: Database):
    settings = await db.get_settings(query.from_user.id)
    if settings["subscribed"]:
        await db.unsubscribe(query.from_user.id)
        await query.answer("🔕 Подписка отключена")
    else:
        await db.subscribe(query.from_user.id)
        await query.answer("🔔 Подписка включена")
    settings = await db.get_settings(query.from_user.id)
    await query.message.edit_reply_markup(
        reply_markup=settings_keyboard(
            settings["timeframe"],
            settings["min_confidence"],
            settings["subscribed"],
        )
    )


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
        lines.append(
            f"{icon} {s['symbol'][:-4]}/{s['symbol'][-4:]} {arrow} {s['timeframe']} "
            f"| {s['strength_label']} {s['strength_pct']}% | {s['created_at']}"
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

    await message.answer("🔄 Начинаю обучение ML-модели...")

    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
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
    df = pd.DataFrame([dict(zip(cols, r)) for r in rows])

    if len(df) < 50:
        await message.answer(f"⚠️ Недостаточно данных для обучения: {len(df)} сигналов (нужно минимум 50)")
        return

    result = train_model(df, min_samples=50)
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
