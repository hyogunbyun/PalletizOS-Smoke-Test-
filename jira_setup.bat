@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem JIRA 이슈 등록 설정: 주소·이메일·API 토큰 (토큰은 Windows 자격 증명에만 저장)
echo JIRA 연결 정보를 등록합니다. API 토큰은 Windows 자격 증명에만 저장됩니다.
".venv\Scripts\python.exe" -m autotest.jira setup
echo.
echo 아무 키나 누르면 창이 닫힙니다.
pause >nul
