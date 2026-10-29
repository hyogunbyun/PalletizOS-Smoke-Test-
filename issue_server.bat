@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 이슈 등록 서버(127.0.0.1:8781)를 켜고 최근 리포트를 그 주소로 연다
echo 이슈 등록 서버를 켜고 최근 결과 리포트를 엽니다...
start "" ".venv\Scripts\pythonw.exe" -m autotest.issue_server
timeout /t 2 >nul
start "" "http://127.0.0.1:8781/results/latest.html"
