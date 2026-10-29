@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem GitHub token setup for daily build watcher (token stored in Windows Credential Manager only)
".venv\Scripts\python.exe" -m autotest.github setup
echo.
pause
