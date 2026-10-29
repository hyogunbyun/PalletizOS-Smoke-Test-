@echo off
cd /d "%~dp0"
rem Stop the daily build watcher (it stops within 10 seconds)
echo stop> results\watch.stop
echo Stop requested. Log: results\watch.log
timeout /t 5
