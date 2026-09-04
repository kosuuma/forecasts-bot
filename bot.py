"""
Telegram-бот на aiogram 3: команды, настройки, подписка на авто-сигналы.
"""
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from database import Database

logger = logging.getLogger("bot")

router = Router()


def get_db(message_or_query) -> Database:
    """Достаёт объект Database из workflow_data диспетчера (передаётся через middleware/DI)."""
    # В aiogram 3 зависимости передаются через аргументы хендлера (dependency injection),
    # см. main.py — там db регистрируется как workflow_data.
    raise NotImplementedError  # не используется, оставлено для ясности архитектуры


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, db: Database):
    text = (
        "👋 Привет! Я бот для анализа криптовалютного рынка.\n\n"
        "Я слежу за 20+ парами на нескольких таймфреймах и отправляю "
        "сигналы, когда совпадает несколько технических индикаторов "
        "(RSI, MACD, Bollinger Bands, EMA, объём, уровни поддержки/сопротивления).\n\n"
        "📋 Команды:\n"
        "/subscribe — подписаться на авто-сигналы\n"
        "/unsubscribe — отписаться\n"
        "/settings — настроить таймфрейм и уверенность\n"
        "/pairs — список отслеживаемых пар\n"
        "/signals — последние 10 сигналов\n"
        "/stats — статистика винрейта\n\n"
        "⚠️ Это не финансовая рекомендация. Торговля криптовалютой связана "
        "с высоким риском, всегда проводите собственный анализ."
    )
    await message.answer(text)


# ---------------------------------------------------------------------------
# /subscribe /unsubscribe
# ---------------------------------------------------------------------------
@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, db: Database):
    await db.subscribe(message.chat.id)
    await message.answer(
        "✅ Вы подписались на автоматические сигналы.\n"
        "Настроить таймфрейм и порог уверенности можно через /settings."
    )


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, db: Database):
    await db.unsubscribe(message.chat.id)
    await message.answer("🔕 Вы отписались от автоматических сигналов.")


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------
def settings_keyboard(current_tf: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tf in config.TIMEFRAMES:
        label = f"✅ {tf}" if tf == current_tf else tf
        builder.button(text=label, callback_data=f"set_tf:{tf}")
    builder.adjust(len(config.TIMEFRAMES))

    conf_builder = InlineKeyboardBuilder()
    for conf in (50, 60, 70, 80):
        conf_builder.button(text=f"{conf}%+", callback_data=f"set_conf:{conf}")
    conf_builder.adjust(4)

    builder.attach(conf_builder)
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
    await message.answer(text, reply_markup=settings_keyboard(settings["timeframe"]))


@router.callback_query(F.data.startswith("set_tf:"))
async def cb_set_timeframe(query: CallbackQuery, db: Database):
    tf = query.data.split(":", 1)[1]
    await db.update_settings(query.from_user.id, timeframe=tf)
    await query.answer(f"Таймфрейм установлен: {tf}")
    settings = await db.get_settings(query.from_user.id)
    await query.message.edit_reply_markup(reply_markup=settings_keyboard(settings["timeframe"]))


@router.callback_query(F.data.startswith("set_conf:"))
async def cb_set_confidence(query: CallbackQuery, db: Database):
    conf = int(query.data.split(":", 1)[1])
    await db.update_settings(query.from_user.id, min_confidence=conf)
    await query.answer(f"Минимальная уверенность: {conf}%")


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
    await message.answer(text)


# ---------------------------------------------------------------------------
# /signals — последние 10 сигналов
# ---------------------------------------------------------------------------
@router.message(Command("signals"))
async def cmd_signals(message: Message, db: Database):
    recent = await db.get_recent_signals(limit=10)
    if not recent:
        await message.answer("Пока нет истории сигналов.")
        return

    lines = ["📜 Последние 10 сигналов:\n"]
    outcome_icons = {"win": "🟢", "loss": "🔴", "pending": "⏳"}
    for s in recent:
        arrow = "▲" if s["direction"] == "UP" else "▼"
        icon = outcome_icons.get(s["outcome"], "⏳")
        lines.append(
            f"{icon} {s['symbol'][:-4]}/{s['symbol'][-4:]} {arrow} {s['timeframe']} "
            f"| {s['strength_label']} {s['strength_pct']}% | {s['created_at']}"
        )
    await message.answer("\n".join(lines))


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
        f"  Сигналов: {week['total_signals']} | Win: {week['wins']} | Loss: {week['losses']}\n"
        f"  Винрейт: {week['winrate']}%\n\n"
        "🗓 За месяц:\n"
        f"  Сигналов: {month['total_signals']} | Win: {month['wins']} | Loss: {month['losses']}\n"
        f"  Винрейт: {month['winrate']}%\n"
    )

    by_pair = await db.get_stats_by_pair(days=7)
    if by_pair:
        text += "\n📈 По парам (за неделю):\n"
        for p in by_pair[:10]:
            text += f"  {p['symbol'][:-4]}/{p['symbol'][-4:]}: {p['winrate']}% ({p['wins']}W/{p['losses']}L)\n"

    await message.answer(text)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp
