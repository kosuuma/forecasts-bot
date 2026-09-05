@echo off
title Crypto Bot

call venv\Scripts\activate.bat

echo [1/2] Starting autosave...
start "autosave" /MIN python autosave.py

timeout /t 2 /nobreak >nul

echo [2/2] Starting bot...
echo.
python main.py

taskkill /F /IM python.exe /FI "WINDOWTITLE eq *autosave*" >nul 2>&1
echo Bot stopped.
pause
