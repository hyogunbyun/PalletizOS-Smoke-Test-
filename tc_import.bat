@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem TC·체크리스트 엑셀 가져오기 화면
start "" ".venv\Scripts\pythonw.exe" -m tc_autotest.import_gui %*
