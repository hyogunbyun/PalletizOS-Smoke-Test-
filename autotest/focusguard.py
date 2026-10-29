"""포커스 지킴이 (background 모드 전용, 2026-10-22 사용자 요청: 항목마다 포커스가 앱으로 넘어가 다른 업무가 끊김).

UIA 명령(Invoke·SetValue 등)을 받은 앱(Electron)이 스스로 창을 앞으로 가져오는 경우가 있다.
0.1초마다 맨 앞 창을 보고, 앱 창이 '사용자 조작 없이' 앞으로 오면 사용자가 쓰던 창으로 즉시 되돌린다.

사용자 조작으로 보는 경우 (되돌리지 않음):
- 최근 1초 안에 입력이 있었고, 그때 마우스가 앱 창(보이는 부분)이나 작업 표시줄 위에 있었음
- Alt / Win 키가 눌려 있음 (Alt+Tab, Win+숫자)
- 시나리오 녹화 중 (results/pause.flag) — 사람이 앱을 직접 누르는 중
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time

from .ui import PAUSE_FILE
from .winutil import give_back_focus

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetAncestor.restype = wt.HWND

APP_TITLE = "Dr.Dart-Platform"
TASKBAR = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")


class _LII(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def _idle_ms():
    lii = _LII(ctypes.sizeof(_LII), 0)
    user32.GetLastInputInfo(ctypes.byref(lii))
    return (kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF


def _text(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    return buf.value


def _cls(h):
    buf = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(h, buf, 128)
    return buf.value


def _is_app(h):
    return bool(h) and _text(h) == APP_TITLE


def _is_ours(h):
    """자동화 자신의 창(앱·상태 표시창) — '사용자가 쓰던 창'으로 기억하면 안 됨.
    2026-10-22 실측: 표시창을 사용자 창으로 기억해 포커스를 표시창에 돌려줌 → 키 입력이 '자동화 종료' 버튼에 들어갈 위험"""
    return _is_app(h) or _text(h) == "PalletizOS Smoke Overlay"


def _user_switched(fg):
    if user32.GetAsyncKeyState(0x12) & 0x8000 or user32.GetAsyncKeyState(0x5B) & 0x8000 \
            or user32.GetAsyncKeyState(0x5C) & 0x8000:  # Alt, 왼쪽/오른쪽 Win
        return True
    if _idle_ms() > 1000:
        return False  # 최근 입력 없음 → 사람이 바꾼 게 아님
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    under = user32.GetAncestor(user32.WindowFromPoint(pt), 2)  # GA_ROOT
    return under == fg or _cls(under) in TASKBAR


class FocusGuard(threading.Thread):
    def __init__(self, log=print):
        super().__init__(daemon=True)
        self.log = log
        self.user_fg = None if _is_ours(user32.GetForegroundWindow()) else user32.GetForegroundWindow()
        self.restored = 0
        self._halt = threading.Event()

    def stop(self):
        self._halt.set()

    def run(self):
        last = user32.GetForegroundWindow()
        while not self._halt.wait(0.1):
            try:
                fg = user32.GetForegroundWindow()
                if fg == last:
                    continue
                if _is_app(fg) and self.user_fg and not PAUSE_FILE.exists() and not _user_switched(fg):
                    give_back_focus(self.user_fg, fg)
                    self.restored += 1
                    if self.restored <= 3 or self.restored % 20 == 0:
                        self.log(f"  포커스 되돌림 #{self.restored} (앱이 앞으로 나옴 → '{_text(self.user_fg)[:30]}')")
                    fg = user32.GetForegroundWindow()
                elif fg and not _is_ours(fg):
                    self.user_fg = fg  # 사용자가 지금 쓰는 창
                last = fg
            except Exception:
                time.sleep(0.5)  # 감시 실패가 실행을 막지 않게
