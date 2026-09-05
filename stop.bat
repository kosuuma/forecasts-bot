@echo off
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq autosave" >nul 2>&1
taskkill /F /IM cmd.exe /FI "WINDOWTITLE eq Crypto Bot" >nul 2>&1
