@echo off
taskkill /F /IM python.exe >nul 2>&1
powershell -Command "Get-Process cmd | Where-Object {$_.MainWindowTitle -eq 'autosave' -or $_.MainWindowTitle -eq 'Crypto Bot'} | Stop-Process -Force" >nul 2>&1
exit
