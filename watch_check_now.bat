@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem GitHub 릴리스를 지금 한 번 확인 (새 빌드가 있으면 설치 + 스모크)
echo GitHub에서 새 빌드를 지금 확인합니다. 새 빌드가 있으면 설치 후 스모크를 실행합니다.
".venv\Scripts\python.exe" -m autotest.watcher --once
echo.
echo 아무 키나 누르면 창이 닫힙니다.
pause >nul
