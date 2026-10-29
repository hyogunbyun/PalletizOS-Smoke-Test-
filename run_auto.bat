@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Started by the daily build watcher after installing a new PalletizOS build (%1 = installed version)
".venv\Scripts\python.exe" run_smoke.py --expect %1 --no-update-check
echo.
echo Automation finished. The result report has been opened in the browser.
echo This window closes automatically in 15 seconds.
timeout /t 15
