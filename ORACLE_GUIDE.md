# Oracle Cloud Free Tier - Пошаговая инструкция

## 1. Регистрация
1. Перейди на oracle.com/cloud/free
2. Нажми "Start for free"
3. Заполни форму (имя, email, пароль)
4. Подтверди email
5. Введи адрес и данные карты (для верификации)
6. Выбери регион (лучше Frankfurt или Amsterdam для Европы)
7. Заверши регистрацию

## 2. Создание сервера (VM Instance)
1. В консоли Oracle Cloud перейди в "Compute" → "Instances"
2. Нажми "Create Instance"
3. Настройки:
   - Name: crypto-bot
   - Image: Ubuntu 22.04 (или Ubuntu 24.04)
   - Shape: VM.Standard.E2.1.Micro (Always Free)
   - VCN: создай новую (или выбери существующую)
   - Subnet: Public
   - SSH Keys: загрузи свой публичный ключ
4. Нажми "Create"
5. Дождись статуса "Running"
6. Скопируй Public IP адрес

## 3. Подключение к серверу
С своего ПК:
```bash
ssh ubuntu@ТВОЙ_IP
```

## 4. Загрузка файлов бота
С своего ПК:
```bash
cd "D:\AI PROJECTS\forecasts bot"
scp -r . ubuntu@ТВОЙ_IP:/home/ubuntu/crypto-bot
```

## 5. Установка Docker на сервере
На сервере:
```bash
cd ~/crypto-bot
bash oracle-deploy.sh
```

## 6. Настройка .env
На сервере:
```bash
cd ~/crypto-bot
nano .env
```
Вставь:
```
BOT_TOKEN=твой_токен_от_ботфазера
DEFAULT_EXCHANGE=binance
SCAN_INTERVAL_MINUTES=5
DB_PATH=signals.db
```
Сохрани: Ctrl+O, Enter, Ctrl+X

## 7. Запуск бота
```bash
docker-compose up -d
```

## 8. Проверка
```bash
bash manage.sh status
bash manage.sh logs
```

## 9. Управление (можно с телефона)
```bash
# Остановить
bash manage.sh stop

# Запустить
bash manage.sh start

# Логи
bash manage.sh logs

# Обновить (после изменений на ПК)
bash manage.sh update
```

## SSH с телефона
Установи приложение:
- **Termius** (iOS/Android) — бесплатно
- **JuiceSSH** (Android) — бесплатно

Добавь подключение:
- Host: ТВОЙ_IP
- Username: ubuntu
- Password: твой пароль (или SSH ключ)
