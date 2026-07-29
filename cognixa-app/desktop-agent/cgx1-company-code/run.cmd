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

REM Admin cmd CANNOT see a normal-user SAP GUI session via COM.
net session >nul 2>&1
if %errorlevel%==0 (
  echo ERROR: This window is running as Administrator.
  echo.
  echo Your SAP Easy Access is running as a normal user.
  echo An Admin agent cannot see that SAP session ^(shows 0 sessions^).
  echo.
  echo FIX:
  echo   1. Close this Admin window
  echo   2. Keep SAP Easy Access open
  echo   3. In File Explorer, double-click run.cmd NORMALY
  echo      ^(do NOT choose Run as administrator^)
  echo.
  goto HOLD
)

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

REM Prefer 32-bit PowerShell: SAP GUI is almost always 32-bit.
REM 64-bit PowerShell GetActiveObject often reports 0 sessions while Easy Access is open.
set "PSEXE=%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PSEXE%" set "PSEXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PSEXE%" (
  where powershell >nul 2>nul
  if errorlevel 1 (
    echo ERROR: powershell.exe not found.
    goto HOLD
  )
  set "PSEXE=powershell"
)

echo Using PowerShell:
echo   %PSEXE%
echo.

echo.
echo IMPORTANT - do this FIRST or you will get "0 sessions":
echo   1. SAP GUI Alt+F12 -^> Options -^> Accessibility ^& Scripting
echo      Enable scripting = ON
echo   2. FULLY close SAP Logon/GUI, then log on again
echo   3. Easy Access open for Rajesh1 / client 800
echo   4. Optional: run diagnose.cmd first ^(must show sessions ^>= 1^)
echo   5. Double-click run.cmd normally ^(NOT as Administrator^)
echo   6. Agent now uses 32-bit PowerShell + VBS GetObject detect
echo.
echo In this window:
echo   - Press ENTER only when asked ^(do NOT type password on that line^)
echo   - Watch for STEP^| lines; Allow scripting popups in SAP
echo.
echo A copy of the run is also saved to agent-run.log
echo.

REM Do NOT redirect the whole PowerShell session - that hides progress after password.
"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Create-CGX1.ps1" %*
set ERR=%ERRORLEVEL%

echo.
if exist "%~dp0agent-run.log" (
  echo ---------- agent-run.log ^(tail^) ----------
  "%PSEXE%" -NoProfile -Command "Get-Content -LiteralPath '%~dp0agent-run.log' -Tail 30"
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
