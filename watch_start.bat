@echo off
cd /d "%~dp0"
rem Start the daily build watcher in the background (checks GitHub releases every 30 minutes)
start "" ".venv\Scripts\pythonw.exe" -m autotest.watcher
echo Daily build watcher started. Log: results\watch.log
timeout /t 5
