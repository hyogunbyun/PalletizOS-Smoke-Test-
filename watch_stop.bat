@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 데일리 빌드 감시기 중지 (10초 안에 멈춤)
echo stop> results\watch.stop
echo 감시 중지를 요청했습니다. 10초 안에 멈춥니다. 기록: results\watch.log
echo 이 창은 5초 뒤 닫힙니다.
timeout /t 5 >nul
