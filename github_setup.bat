@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 데일리 빌드 감시용 GitHub 토큰 등록 (토큰은 Windows 자격 증명에만 저장)
echo GitHub 토큰을 등록합니다. 토큰은 Windows 자격 증명에만 저장되고 파일에는 남지 않습니다.
".venv\Scripts\python.exe" -m autotest.github setup
echo.
echo 아무 키나 누르면 창이 닫힙니다.
pause >nul
