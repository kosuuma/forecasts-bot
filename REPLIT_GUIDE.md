# Replit - Бесплатный деплой бота

## Пошагово:

1. Зайди на replit.com
2. Зарегистрируйся (Google/GitHub аккаунт)
3. Нажми "Create Repl"
4. Выбери "Python"
5. Назови "crypto-bot"
6. Нажми "Create Repl"

## Загрузка файлов:

В левой панели Replit:
1. Удали файл main.py (который создался по умолчанию)
2. Нажми правой кнопкой на папку → "Upload file"
3. Загрузи ВСЕ файлы из папки проекта:
   - main.py
   - bot.py
   - config.py
   - exchanges.py
   - signals.py
   - indicators.py
   - database.py
   - monitor.py
   - ml.py
   - requirements-replit.txt
   - .env (создай через "Secrets")

## Настройка переменных окружения:

1. Слева нажми на значок 🔒 (Secrets)
2. Добавь:
   - Key: BOT_TOKEN
   - Value: твой_токен_бота

## Установка пакетов:

В консоли (внизу) напиши:
```bash
pip install -r requirements-replit.txt
```

## Запуск:

Нажми зелёную кнопку "Run"

## Для работы 24/7:

Replit Free tier засыпает через 1 час без активности.
Чтобы бот работал постоянно:
1. Нажми "Deployments" (справа)
2. Выбери "Reserved VM" (платно) 
3. ИЛИ используй "Always On" через "Uptime Robot" (бесплатно)

## Альтернатива для 24/7 бесплатно:

Используй "Uptime Robot" (uptimerobot.com):
1. Зарегистрируйся бесплатно
2. Добавь мониторинг URL твоего Replit проекта
3. Он будет "пинговать" проект каждые 5 минут
4. Бот не будет засыпать
