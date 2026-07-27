@echo off
setlocal EnableExtensions
title Cognixa Desktop Agent - CGX1
color 0A
set ERR=1

echo.
echo ============================================================
echo  Cognixa Desktop Agent - create CGX1 on A4H
echo  Real SAP GUI write on THIS Windows PC
echo ============================================================
echo.

cd /d "%~dp0" 2>nul
if errorlevel 1 (
  echo ERROR: Cannot change to script folder.
  echo You must Extract All from the zip first.
  goto HOLD
)

echo Working folder:
echo   %CD%
echo.

echo %CD% | findstr /I /C:"\AppData\Local\Temp\" /C:"\Temp\Temp1_" /C:".zip\" >nul
if not errorlevel 1 (
  echo WARNING: This looks like a temporary / zip path.
  echo.
  echo FIX: Extract All the zip, then run run.cmd from the extracted folder.
  echo.
  goto HOLD
)

if not exist "%~dp0Run-Create-CGX1.ps1" (
  echo ERROR: Run-Create-CGX1.ps1 not found next to run.cmd
  goto HOLD
)
if not exist "%~dp0Create-CGX1.vbs" (
  echo ERROR: Create-CGX1.vbs not found next to run.cmd
  goto HOLD
)
if not exist "%~dp0payload.json" (
  echo ERROR: payload.json not found next to run.cmd
  goto HOLD
)

where powershell >nul 2>nul
if errorlevel 1 (
  echo ERROR: powershell.exe not found on PATH.
  goto HOLD
)

echo.
echo NEXT STEP:
echo   1. Type the SAP password for Rajesh1
echo   2. Press ENTER
echo   3. Keep watching this window - progress prints here
echo   4. If SAP Logon / transport popups appear, handle them
echo.
echo A copy of the run is also saved to agent-run.log
echo.

REM Do NOT redirect the whole PowerShell session - that hides progress after password.
REM The PS1 writes agent-run.log itself via Tee-Object style logging.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Create-CGX1.ps1" %*
set ERR=%ERRORLEVEL%

echo.
if exist "%~dp0agent-run.log" (
  echo ---------- agent-run.log ^(tail^) ----------
  powershell -NoProfile -Command "Get-Content -LiteralPath '%~dp0agent-run.log' -Tail 30"
  echo -----------------------------------
  echo.
)

findstr /I /C:"ParserError" /C:"MissingCatchOrFinally" /C:"Unexpected token" "%~dp0agent-run.log" >nul 2>nul
if not errorlevel 1 (
  echo FAILED: PowerShell parse error. Re-download the latest zip from Cognixa.
  set ERR=10
  goto HOLD
)

if %ERR%==0 (
  echo SUCCESS. Verify in S/4: OX02 or SE16N table T001 = CGX1
) else if %ERR%==1 (
  echo VERIFY: CGX1 not found yet ^(normal before first create^).
) else if %ERR%==10 (
  echo FAILED with exit code 10. Read the ERROR lines above.
) else (
  echo Finished with exit code %ERR%. Read the messages above and agent-run.log.
)

:HOLD
echo.
echo Press any key to close this window...
pause >nul
endlocal & exit /b %ERR%
