@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" run_smoke.py --ask %*
echo.
echo Automation finished. The result report has been opened in the browser.
echo This window closes automatically in 15 seconds (press any key to close now).
timeout /t 15
