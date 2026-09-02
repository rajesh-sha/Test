@echo off
REM Double-click this to open the SAP Load Workbench in your browser.
cd /d "%~dp0"
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" (where py >nul 2>nul && set PY=py)
if "%PY%"=="" (
  echo.
  echo   Python was not found on this machine.
  echo   Install it from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)
%PY% -m sapload.serve
if errorlevel 1 (
  echo.
  echo   The workbench did not start. Running the self check...
  echo.
  %PY% check.py
  pause
)
