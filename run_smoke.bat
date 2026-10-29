@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo PalletizOS 스모크 자동화를 시작합니다. 이 창을 닫으면 자동화가 바로 멈춥니다.
".venv\Scripts\python.exe" run_smoke.py --ask %*
echo.
echo 자동화가 끝났습니다. 결과 리포트를 브라우저로 열었습니다.
echo 이 창은 15초 뒤 자동으로 닫힙니다. (아무 키나 누르면 바로 닫힘)
timeout /t 15 >nul
