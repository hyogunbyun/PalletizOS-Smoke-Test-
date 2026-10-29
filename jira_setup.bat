@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem JIRA issue registration setup: site, email, API token (token stored in Windows Credential Manager only)
".venv\Scripts\python.exe" -m autotest.jira setup
echo.
pause
