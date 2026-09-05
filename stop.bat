@echo off
title Stop Bot

echo Stopping bot and autosave...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *Crypto Bot*" >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *autosave*" >nul 2>&1
echo Done.
timeout /t 2 /nobreak >nul
