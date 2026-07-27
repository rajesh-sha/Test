@echo off
setlocal
cd /d "%~dp0"
echo.
echo Cognixa Desktop Agent — create CGX1 on A4H (real SAP GUI write)
echo Prefer BC Sets for bulk. This agent is residual / last resort.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Create-CGX1.ps1" %*
set ERR=%ERRORLEVEL%
echo.
if %ERR%==0 (
  echo Done. Verify in S/4: OX02 or SE16N table T001 = CGX1
) else (
  echo Exit code %ERR%. See README.md
)
exit /b %ERR%
