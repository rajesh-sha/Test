@echo off
setlocal EnableExtensions
title Cognixa SAP Diagnose
color 0B
echo.
echo Cognixa - diagnose SAP GUI scripting / session visibility
echo.

net session >nul 2>&1
if %errorlevel%==0 (
  echo ERROR: Running as Administrator.
  echo Admin cannot see a normal-user SAP GUI session.
  echo Close this window and double-click diagnose.cmd normally.
  echo.
  pause
  exit /b 10
)

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Diagnose-SAP.ps1"
echo.
echo Press any key to close...
pause >nul
endlocal
