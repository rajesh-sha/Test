@echo off
REM Double-click this to open the SAP Load Workbench in your browser.
cd /d "%~dp0"
where python >nul 2>nul && (python -m sapload.serve & goto :eof)
where py >nul 2>nul && (py -m sapload.serve & goto :eof)
echo.
echo   Python was not found on this machine.
echo   Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^),
echo   then double-click this file again.
echo.
pause
