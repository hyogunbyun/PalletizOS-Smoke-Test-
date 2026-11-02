@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem TC·체크리스트 자동 평가 (%1 = 엑셀 경로, 없으면 v2.0.0-21 변경 TC)
echo PalletizOS TC 자동 평가를 시작합니다. 이 창을 닫으면 평가가 바로 멈춥니다.
".venv\Scripts\python.exe" -X utf8 tc_run.py %*
echo.
echo 평가가 끝났습니다. 결과 엑셀(…_자동판정_…xlsx)이 열렸습니다.
echo 아무 키나 누르면 창이 닫힙니다.
pause >nul
