# Crypto Signal Bot

Telegram-бот на **aiogram 3** для технического анализа криптовалютного рынка
и рассылки торговых сигналов на основе публичных API бирж (Binance / Bybit / OKX).

## Структура проекта

```
forecasts bot/
├── main.py          # точка входа: запуск бота + планировщик сканирования
├── bot.py           # команды и хендлеры Telegram
├── config.py        # настройки, пороги индикаторов, список пар
├── exchanges.py     # запросы к публичным API бирж (klines, тикеры, funding, orderbook)
├── indicators.py    # расчёт RSI, MACD, BB, EMA, OBV, StochRSI, ATR, паттернов
├── signals.py       # логика генерации сигналов и форматирование сообщений
├── ml.py            # ML-модель (Random Forest / Gradient Boosting)
├── database.py      # SQLite: подписчики, история, статистика
├── monitor.py       # алерты резких движений цены + TP/SL определение исхода
├── autosave.py      # автосохранение в GitHub
├── requirements.txt
└── .env.example
```

## Установка

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/Mac
```

Откройте `.env` и укажите `BOT_TOKEN`, полученный у [@BotFather](https://t.me/BotFather).

## Запуск

```bash
python main.py
```

Бот запускается в режиме long polling и параллельно поднимает планировщик
(APScheduler), который каждые `SCAN_INTERVAL_MINUTES` минут (по умолчанию 5)
проходит по всем активным парам, считает индикаторы и рассылает сигналы
подписчикам согласно их настройкам (таймфрейм, минимальная уверенность).

## Логика сигнала

Проверяется до 10 условий: RSI, MACD, Bollinger Bands, EMA50, объём, близость
к уровню поддержки/сопротивления, Funding Rate, Orderbook, Multi-TF тренд, ML.

### Базовые индикаторы (6)
- **CALL (вверх)**: RSI < 30, бычий кросс MACD, цена у нижней границы BB,
  цена у поддержки, объём выше среднего.
- **PUT (вниз)**: RSI > 70, медвежий кросс MACD, цена у верхней границы BB,
  цена у сопротивления, объём выше среднего.

### Дополнительные индикаторы (4)
- **Funding Rate**: экстремальные значения дают бонус к скору
- **Orderbook**: bid/ask ratio и spread анализ
- **Multi-Timeframe**: проверка тренда на старшем TF
- **ML**: Random Forest предсказывает вероятность win

### Сила сигнала
- 5+ подтверждений → **Strong**
- 3-4 подтверждения → **Medium**
- <3 → сигнал не отправляется (Weak)

## TP/SL и винрейт

Каждый сигнал рассчитывает:
- **Take Profit**: `entry ± ATR × 2`
- **Stop Loss**: `entry ∓ ATR × 1.5`
- **Время жизни**: `timeframe × 3` свечей

Определение исхода: проверяются свечи за время жизни сигнала.
Если TP сработал раньше SL → **win**, иначе → **loss**.
Если за время жизни ни TP, ни SL не сработали → **expired**.

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | приветствие и инструкция |
| `/subscribe` | подписка на авто-сигналы |
| `/unsubscribe` | отписка |
| `/settings` | таймфрейм и минимальная уверенность (инлайн-кнопки) |
| `/pairs` | список отслеживаемых пар |
| `/signals` | последние 10 сигналов с исходом (win/loss/expired/pending) |
| `/stats` | винрейт за неделю/месяц, разбивка по парам, статус ML |
| `/train` | обучение ML-модели на исторических данных |

## ML-модель

Бот использует **Random Forest** и **Gradient Boosting** для предсказания
вероятности win на основе исторических данных.

### Признаки
- RSI, MACD histogram, BB width, EMA distances
- Volume ratio, ATR%, StochRSI K/D
- RSI overbought/oversold, MACD positive
- OBV slope, EMA crossovers

### Обучение
- Минимум 100 сигналов с определённым исходом
- Автоматический выбор лучшей модели (RF vs GB)
- Сохранение в `ml_model.pkl`
- Команда `/train` для ручного переобучения

## Технические детали

- Кэширование запросов к биржам на 30 секунд (`CACHE_TTL_SECONDS`).
- Повторные попытки при таймаутах и `429 Too Many Requests`.
- Rate limiting: не чаще одного сигнала на пару за 30 минут.
- Все ошибки логируются в `bot.log` и в консоль.
- Свечные паттерны: Doji, Hammer, Engulfing, Morning/Evening Star,
  Three White Soldiers/Black Crows, Tweezer.

## Автосохранение в GitHub

`autosave.py` следит за папкой проекта и при любом изменении файла
автоматически делает `git commit` + `git push` — как save point в игре.

```bash
python autosave.py
```

## Репозиторий

Код запушен в приватный репозиторий: https://github.com/kosuuma/forecasts-bot

## ⚠️ Важно
Бот не даёт финансовых рекомендаций. Все сигналы основаны на техническом
анализе индикаторов и не гарантируют результат. Торговля криптовалютой
сопряжена с высоким риском потери капитала.
