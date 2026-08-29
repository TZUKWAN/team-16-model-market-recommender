@echo off
setlocal
cd /d "%~dp0"

echo [Team 16] Starting the competition runtime...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-competition.ps1"
set "exit_code=%ERRORLEVEL%"

if not "%exit_code%"=="0" (
  echo.
  echo [Team 16] Startup failed. Review the message and log path above.
) else (
  echo.
  echo [Team 16] Startup completed successfully.
)

echo.
pause
exit /b %exit_code%
