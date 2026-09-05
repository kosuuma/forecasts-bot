@echo off
taskkill /F /IM python.exe >nul 2>&1
taskkill /FI "WINDOWTITLE eq *Crypto Bot*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq *autosave*" /F >nul 2>&1
exit
