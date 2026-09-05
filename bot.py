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
# /stats — винрейт за неделю/месяц
# ---------------------------------------------------------------------------
@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    week = await db.get_stats(days=7)
    month = await db.get_stats(days=30)

    text = (
        "📊 Статистика\n\n"
        "🗓 За неделю:\n"
        f"  Сигналов: {week['total_signals']} | ✅ Win: {week['wins']} | ❌ Loss: {week['losses']} | ⏰ Expired: {week['expired']}\n"
        f"  Винрейт: {week['winrate']}%\n\n"
        "🗓 За месяц:\n"
        f"  Сигналов: {month['total_signals']} | ✅ Win: {month['wins']} | ❌ Loss: {month['losses']} | ⏰ Expired: {month['expired']}\n"
        f"  Винрейт: {month['winrate']}%\n"
    )

    by_pair = await db.get_stats_by_pair(days=7)
    if by_pair:
        text += "\n📈 По парам (за неделю):\n"
        for p in by_pair[:10]:
            text += f"  {p['symbol'][:-4]}/{p['symbol'][-4:]}: {p['winrate']}% ({p['wins']}W/{p['losses']}L)\n"

    from ml import load_model
    ml_model = load_model()
    if ml_model:
        text += f"\n🤖 ML модель: {ml_model['model_name']} (accuracy: {ml_model['accuracy']:.0%})\n"
    else:
        text += "\n🤖 ML модель: не обучена\n"

    await message.answer(text, reply_markup=main_keyboard())


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
