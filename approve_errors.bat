@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 새 에러 로그를 기준 목록(baseline_errors.txt)에 승인
".venv\Scripts\python.exe" approve_errors.py
echo.
echo 아무 키나 누르면 창이 닫힙니다.
pause >nul
