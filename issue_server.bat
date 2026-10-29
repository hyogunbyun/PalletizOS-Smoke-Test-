@echo off
cd /d "%~dp0"
rem Start issue registration server (127.0.0.1:8781) and open the latest report through it
start "" ".venv\Scripts\pythonw.exe" -m autotest.issue_server
timeout /t 2 >nul
start "" "http://127.0.0.1:8781/results/latest.html"
