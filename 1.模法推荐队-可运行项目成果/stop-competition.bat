@echo off
setlocal
cd /d "%~dp0"

echo [Team 16] Stopping the competition runtime...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-competition.ps1"
set "exit_code=%ERRORLEVEL%"

echo.
pause
exit /b %exit_code%
