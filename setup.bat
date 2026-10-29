@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 처음 한 번: Python 가상환경 + 패키지 + 바탕화면 실행 아이콘
echo [1/3] Python 가상환경(.venv) 만드는 중...
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Python 3.12 을 찾지 못했습니다. python.org 에서 Python 3.12 를 설치한 뒤 다시 실행하세요.
  echo 아무 키나 누르면 창이 닫힙니다.
  pause >nul
  exit /b 1
)
echo [2/3] 필요한 패키지 설치 중... (1~3분)
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo 패키지 설치에 실패했습니다. 인터넷 연결 또는 사내 프록시 설정을 확인하세요.
  echo 아무 키나 누르면 창이 닫힙니다.
  pause >nul
  exit /b 1
)
echo [3/3] 바탕화면에 실행 아이콘 만드는 중...
set "DT=%USERPROFILE%\Desktop"
> "%DT%\PalletizOS_smoke.bat" echo @call "%~dp0run_smoke.bat" %%*
> "%DT%\PalletizOS_record.bat" echo @call "%~dp0record.bat"
> "%DT%\PalletizOS_scenarios.bat" echo @call "%~dp0scenarios.bat"
echo.
echo 설치가 끝났습니다. 다음 순서로 진행하세요 (자세한 내용은 README.md):
echo   1) Admin 비밀번호 한 번 저장:  .venv\Scripts\python.exe -m autotest.secret set
echo   2) 스모크 실행:                 바탕화면 PalletizOS_smoke.bat
echo   3) (선택) JIRA 이슈 등록:      jira_setup.bat
echo   4) (선택) 데일리 빌드 자동:    github_setup.bat  다음  watch_start.bat
echo.
echo 아무 키나 누르면 창이 닫힙니다.
pause >nul
