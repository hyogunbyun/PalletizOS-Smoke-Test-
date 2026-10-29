"""사건 기록 (results/events.log): 실행 시작·끝, 종료 요청, 앱 재시작·정리, 실행기 오류, 콘솔 닫힘, 표시창 버튼.
'왜 멈췄나 / 왜 앱이 꺼졌나'를 시각·원인으로 한 줄씩 남긴다 (2026-10-22 도입)."""
import os
from datetime import datetime
from pathlib import Path

EVENTS = Path(__file__).resolve().parent.parent / "results" / "events.log"


def ev(msg):
    try:
        with open(EVENTS, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [실행기 {os.getpid()}] {msg}\n")
    except OSError:
        pass
