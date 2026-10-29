@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 시나리오 녹화기
start "" ".venv\Scripts\pythonw.exe" -m autotest.recorder
