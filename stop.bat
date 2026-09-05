@echo off
taskkill /F /IM python.exe >nul 2>&1
powershell -Command "$self = [System.Diagnostics.Process]::GetCurrentProcess().Id; Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.ProcessId -ne $self -and ($_.CommandLine -like '*start.bat*' -or $_.CommandLine -like '*autosave*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
