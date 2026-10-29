@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Run one item only (used by overlay chips). No version prompt; Admin password from Credential Manager.
".venv\Scripts\python.exe" run_smoke.py --only %*
echo.
echo Automation finished. The result report has been opened in the browser.
echo This window closes automatically in 15 seconds (press any key to close now).
timeout /t 15
