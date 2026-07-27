@echo off
setlocal EnableExtensions
title Cognixa Desktop Agent - CGX1
color 0A

echo.
echo ============================================================
echo  Cognixa Desktop Agent - create CGX1 on A4H
echo  Real SAP GUI write on THIS Windows PC
echo ============================================================
echo.

REM Always work from the folder that contains this .cmd
cd /d "%~dp0" 2>nul
if errorlevel 1 (
  echo ERROR: Cannot change to script folder.
  echo You must Extract All from the zip first.
  goto :HOLD
)

echo Working folder:
echo   %CD%
echo.

REM Detect common "running from inside a zip" / temp extract paths
echo %CD% | findstr /I /C:"\AppData\Local\Temp\" /C:"\Temp\Temp1_" /C:".zip\" >nul
if not errorlevel 1 (
  echo WARNING: This looks like a temporary / zip path.
  echo Windows cannot reliably run the agent from inside the zip.
  echo.
  echo FIX:
  echo   1. Close this window
  echo   2. In File Explorer select the zip -^> Extract All
  echo   3. Open the extracted cgx1-company-code folder
  echo   4. Double-click run.cmd there
  echo.
  goto :HOLD
)

if not exist "%~dp0Run-Create-CGX1.ps1" (
  echo ERROR: Run-Create-CGX1.ps1 not found next to run.cmd
  echo Extract the FULL zip folder, do not run from inside the archive.
  goto :HOLD
)
if not exist "%~dp0Create-CGX1.vbs" (
  echo ERROR: Create-CGX1.vbs not found next to run.cmd
  goto :HOLD
)
if not exist "%~dp0payload.json" (
  echo ERROR: payload.json not found next to run.cmd
  goto :HOLD
)

where powershell >nul 2>nul
if errorlevel 1 (
  echo ERROR: powershell.exe not found on PATH.
  echo Install Windows PowerShell, then retry.
  goto :HOLD
)

echo Starting PowerShell agent...
echo A password prompt should appear next.
echo Status is also written to agent-run.log in this folder.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Create-CGX1.ps1" %* > "%~dp0agent-run.log" 2>&1
set ERR=%ERRORLEVEL%

echo.
echo ---------- agent-run.log ----------
type "%~dp0agent-run.log"
echo -----------------------------------
echo.

if %ERR%==0 (
  echo SUCCESS. Verify in S/4: OX02 or SE16N table T001 = CGX1
) else if %ERR%==1 (
  echo VERIFY: CGX1 not found yet ^(normal before first create^).
) else (
  echo FAILED with exit code %ERR%.
  echo Common causes:
  echo   - Ran from inside the zip ^(Extract All first^)
  echo   - SAP GUI not open / scripting disabled
  echo   - Wrong Logon entry name: S4HANA2023 SHARED GUI
  echo   - Password cancelled / empty
  echo See README.md and agent-run.log
)

:HOLD
echo.
echo Press any key to close this window...
pause >nul
endlocal & exit /b %ERR%
