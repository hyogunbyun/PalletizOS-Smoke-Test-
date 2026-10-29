@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 시나리오 관리 창
start "" ".venv\Scripts\pythonw.exe" -m autotest.scenario_manager
