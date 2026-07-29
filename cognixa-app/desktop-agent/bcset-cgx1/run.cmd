@echo off
setlocal EnableExtensions
title Cognixa BC Set + CTS automation example
color 0A
echo.
echo ============================================================
echo  Cognixa - PREFERRED On-Prem automation
echo  BC Sets (SCPR20) + CTS  - example CGX1 / ZCGX_FI_CGX1
echo ============================================================
echo.
echo This prepares the automation plan and evidence files.
echo Activation itself runs in SAP via:
echo   - ABAP ZCGX_ACTIVATE_BCSET (SCPR_ACTIVATE_BCSETS_REMOTE)
echo   - or SCPR20 Activate + SE09/STMS
echo.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Activate-BCSet.ps1"
set ERR=%ERRORLEVEL%
echo.
if exist "%~dp0bcset-run.log" type "%~dp0bcset-run.log"
echo.
if %ERR%==0 (
  echo NEXT: create BC Set once, activate, release CTS, verify OX02/T001=CGX1
) else (
  echo FAILED exit %ERR%
)
echo.
pause
endlocal & exit /b %ERR%
