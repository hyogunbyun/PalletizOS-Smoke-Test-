"""앞으로 가져와 입력하기 (사용자 허락 2026-11-02 ③: 숫자 입력 시 앱을 잠깐 앞으로).

PalletizOS 숫자 입력칸은 백그라운드 입력(ValuePattern SetValue · WM_CHAR)을 무시한다 → 앱 창을 앞으로 가져와
실제 키보드 입력(SendInput)으로 넣고, 끝나면 원래 쓰던 창을 앞으로 되돌린다. 한 번에 1~2초.
"""
import ctypes
import time

from pywinauto import keyboard

user32 = ctypes.windll.user32
HIDE_OVERLAY = None  # tc_run 이 run_smoke.LIVE.hide 를 넣음 — 상태 표시창이 앱 오른쪽 위 버튼(Color 등)을 가려 실제 클릭이 표시창에 맞음 (11-02)


def _force_foreground(hwnd):
    """다른 창이 앞에 있어도 SetForegroundWindow 가 거부되지 않게 (Alt 키 눌림 트릭)."""
    if user32.GetForegroundWindow() == hwnd:
        return True
    user32.keybd_event(0x12, 0, 0, 0)  # Alt down
    user32.keybd_event(0x12, 0, 2, 0)  # Alt up
    user32.ShowWindow(hwnd, 9 if user32.IsIconic(hwnd) else 5)
    user32.SetForegroundWindow(hwnd)
    for _ in range(20):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.05)
    # 보조: 지금 앞 창의 입력 스레드에 붙어서 넘겨받기 (Windows 포그라운드 잠금 회피)
    fg = user32.GetForegroundWindow()
    kernel32 = ctypes.windll.kernel32
    t_fg = user32.GetWindowThreadProcessId(fg, None)
    t_me = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(t_me, t_fg, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        user32.AttachThreadInput(t_me, t_fg, False)
    for _ in range(20):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.05)
    return False


class Foreground:
    """with Foreground(ui): ... — 블록 안에서만 앱이 앞에 있고, 나오면 원래 창으로."""

    def __init__(self, ui):
        self.ui = ui
        self.prev = None

    def __enter__(self):
        if HIDE_OVERLAY:
            HIDE_OVERLAY(True)
        self.prev = user32.GetForegroundWindow()
        if not _force_foreground(self.ui.hwnd()):
            raise RuntimeError("앱 창을 앞으로 가져오지 못함")
        time.sleep(0.2)
        return self

    def __exit__(self, *exc):
        try:
            if self.prev and self.prev != self.ui.hwnd():
                _force_foreground(self.prev)
        finally:
            if HIDE_OVERLAY:
                HIDE_OVERLAY(False)
        return False


def type_into(ui, edit, text, commit="{TAB}"):
    """입력칸을 클릭해 포커스 → 전체 선택 → 입력 → commit 키(기본 Tab = 포커스 이동으로 확정)."""
    with Foreground(ui):
        r = edit.rectangle()
        edit.click_input(coords=(r.width() - 8, r.height() // 2))  # 단위 글자 앞, 입력칸 안쪽
        time.sleep(0.25)
        keyboard.send_keys("^a{BACKSPACE}", pause=0.03)
        keyboard.send_keys(str(text), pause=0.03, with_spaces=True)
        time.sleep(0.15)
        if commit:
            keyboard.send_keys(commit, pause=0.03)
        time.sleep(0.6)


def real_click(ui, elem, settle=1.0):
    """UIA 누르기로 반응하지 않는 컨트롤(드롭다운 등)을 실제 마우스로 클릭 — 앱을 잠깐 앞으로."""
    with Foreground(ui):
        elem.click_input()
        time.sleep(settle)
