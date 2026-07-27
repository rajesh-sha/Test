@echo off
REM Cognixa CGX1 — SAP GUI diagnostics (prefer 32-bit PowerShell for 32-bit SAP GUI)
setlocal
title Cognixa - diagnose SAP GUI scripting / session visibility
color 0A

echo.
echo Cognixa - diagnose SAP GUI scripting / session visibility
echo.

REM Admin cmd CANNOT see a normal-user SAP GUI session via COM.
net session >nul 2>&1
if %errorlevel%==0 (
  echo ERROR: This window is running as Administrator.
  echo.
  echo Admin cannot see a normal-user SAP GUI session.
  echo Close this window. Double-click diagnose.cmd WITHOUT Run as administrator.
  echo.
  pause
  exit /b 2
)

cd /d "%~dp0" 2>nul
if errorlevel 1 (
  echo ERROR: Cannot change to script folder. Extract All from the zip first.
  pause
  exit /b 1
)

if not exist "%~dp0Diagnose-SAP.ps1" (
  echo ERROR: Diagnose-SAP.ps1 not found next to diagnose.cmd
  pause
  exit /b 1
)
if not exist "%~dp0Detect-SapSessions.vbs" (
  echo WARNING: Detect-SapSessions.vbs missing - VBS detect will be skipped.
  echo.
)

REM Prefer 32-bit PowerShell: SAP GUI is almost always 32-bit.
set "PS32=%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
set "PS64=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if exist "%PS32%" (
  echo Using 32-bit PowerShell: %PS32%
  echo.
  "%PS32%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Diagnose-SAP.ps1"
) else (
  echo Using PowerShell: %PS64%
  echo.
  "%PS64%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Diagnose-SAP.ps1"
)

echo.
pause
endlocal
