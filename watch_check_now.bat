@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Check GitHub releases once now (install + smoke if a newer build exists)
".venv\Scripts\python.exe" -m autotest.watcher --once
echo.
pause
