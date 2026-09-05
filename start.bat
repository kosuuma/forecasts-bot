@echo off
chcp 65001 >nul
title Crypto Bot - Starting...

echo ========================================
echo    Crypto Signal Bot
echo ========================================
echo.

REM Активируем venv
call venv\Scripts\activate.bat

REM Убиваем старые процессы (если есть)
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *main.py*" >nul 2>&1

REM Запускаем autosave в фоне
echo [1/2] Запуск autosave...
start "autosave" /MIN python autosave.py

REM Небольшая пауза
timeout /t 2 /nobreak >nul

REM Запускаем бота
echo [2/2] Запуск бота...
echo.
echo ========================================
echo    Бот запущен! Нажми Ctrl+C для остановки
echo ========================================
echo.
python main.py

REM При остановке — убираем autosave тоже
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *autosave*" >nul 2>&1
echo.
echo Бот и autosave остановлены.
pause
