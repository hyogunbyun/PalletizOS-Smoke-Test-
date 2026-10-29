@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 데일리 빌드 감시기를 백그라운드로 시작 (30분마다 GitHub 릴리스 확인)
start "" ".venv\Scripts\pythonw.exe" -m autotest.watcher
echo 데일리 빌드 감시를 시작했습니다. 30분마다 새 빌드를 확인합니다. 기록: results\watch.log
echo 이 창은 5초 뒤 닫힙니다.
timeout /t 5 >nul
