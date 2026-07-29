@echo off
REM Cognixa UI — start local server and open browser (Windows)
setlocal EnableExtensions
title Cognixa
cd /d "%~dp0"

echo.
echo ============================================================
echo  Cognixa — local run
echo ============================================================
echo.

echo %CD% | findstr /I /C:"\AppData\Local\Temp\" /C:"\.zip\" >nul
if not errorlevel 1 (
  echo ERROR: You are still inside a Temp / zip path.
  echo.
  echo FIX:
  echo   1. Close this window
  echo   2. Right-click Cognixa-UI-source-only.zip -^> Extract All
  echo   3. Open the extracted folder
  echo   4. Double-click START-COGNIXA.cmd
  echo.
  pause
  exit /b 1
)

if not exist "%~dp0Cognixa.html" (
  echo ERROR: Cognixa.html not found next to this .cmd
  pause
  exit /b 1
)
if not exist "%~dp0support.js" (
  echo ERROR: support.js missing. Re-extract the full zip.
  pause
  exit /b 1
)
if not exist "%~dp0vendor\react.production.min.js" (
  echo ERROR: vendor\react*.js missing. Re-extract the full zip.
  pause
  exit /b 1
)

set PORT=8765
set URL=http://127.0.0.1:%PORT%/Cognixa.html

where py >nul 2>nul
if not errorlevel 1 (
  echo Starting: py -m http.server %PORT%
  echo Open: %URL%
  echo.
  start "" "%URL%"
  py -m http.server %PORT%
  goto END
)

where python >nul 2>nul
if not errorlevel 1 (
  echo Starting: python -m http.server %PORT%
  echo Open: %URL%
  echo.
  start "" "%URL%"
  python -m http.server %PORT%
  goto END
)

where python3 >nul 2>nul
if not errorlevel 1 (
  echo Starting: python3 -m http.server %PORT%
  echo Open: %URL%
  echo.
  start "" "%URL%"
  python3 -m http.server %PORT%
  goto END
)

echo ERROR: Python not found.
echo Install Python from https://www.python.org/downloads/
echo ^(tick "Add python.exe to PATH"^) then run this again.
echo.
echo Or from this folder in PowerShell:
echo   py -m http.server 8765
echo then open %URL%
echo.
pause
exit /b 1

:END
endlocal
