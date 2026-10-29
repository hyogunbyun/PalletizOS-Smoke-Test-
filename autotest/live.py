"""러너 → 오버레이 상태 전달 (JSON 파일). 오버레이는 별도 프로세스로 띄운다."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


class Live:
    def __init__(self, path: Path, enabled=True):
        self.path = Path(path)
        self.state = {"badge": "ING", "flow": "환경 준비", "desc": "", "step": "", "action": "", "chips": [],
                      "foot": "백그라운드 실행 중 · 다른 업무를 해도 됩니다 (앱 창 최소화만 하지 마세요)"}
        self.enabled = enabled
        self.mode = "background"  # mouse면 오버레이가 클릭을 통과시킴(종료 버튼 없음)
        self.proc = None

    def start(self):
        if not self.enabled:
            return
        self._write()
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        self.proc = subprocess.Popen([str(pyw if pyw.exists() else exe), str(Path(__file__).with_name("overlay.py")),
                                      str(self.path), str(os.getpid()), self.mode],
                                     creationflags=subprocess.CREATE_NO_WINDOW)

    def set(self, **kw):
        self.state.update(kw)
        if self.enabled:
            self._write()

    def set_chip(self, tc, status):
        self.state["chips"] = [(t, status if t == tc else s) for t, s in self.state["chips"]]
        self.set()

    def _write(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        for _ in range(10):  # 오버레이가 읽는 순간과 겹치면 잠깐 재시도
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                time.sleep(0.05)

    def hide(self, on=True):
        self.set(hidden=on)
        if self.enabled:
            time.sleep(0.6)  # 오버레이가 다음 주기(0.3초)에 숨을 시간
