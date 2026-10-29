@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 항목 하나만 실행 (표시창 칩 두 번 누르기). 버전 질문 없음, Admin 비밀번호는 자격 증명에서
echo 선택한 항목만 실행합니다: %*
".venv\Scripts\python.exe" run_smoke.py --only %*
echo.
echo 자동화가 끝났습니다. 결과 리포트를 브라우저로 열었습니다.
echo 이 창은 15초 뒤 자동으로 닫힙니다. (아무 키나 누르면 바로 닫힘)
timeout /t 15 >nul
