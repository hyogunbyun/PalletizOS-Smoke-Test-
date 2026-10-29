"""Win32 보조 함수 (오버레이·러너 공용). 백그라운드 실행: 포커스·마우스를 빼앗지 않는 창 조작."""
import ctypes
import ctypes.wintypes as wt

user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32


def foreground():
    return user32.GetForegroundWindow()


def give_back_focus(fg, app=None):
    """앱 창이 앞으로 튀어나와 포커스를 가져갔으면 사용자가 쓰던 창(fg)을 다시 앞으로.
    다른 프로세스 창은 SetForegroundWindow만으로는 막히는 경우가 있어 입력 큐를 잠시 붙여서 호출한다."""
    if not fg or fg == app or not user32.IsWindow(fg):
        return
    cur = user32.GetForegroundWindow()
    if cur == fg:
        return
    t_cur = user32.GetWindowThreadProcessId(cur, None)
    me = kernel32.GetCurrentThreadId()
    attached = bool(t_cur) and t_cur != me and user32.AttachThreadInput(me, t_cur, True)
    try:
        user32.SetForegroundWindow(fg)
    finally:
        if attached:
            user32.AttachThreadInput(me, t_cur, False)


def _windows(title):
    """제목이 같은 보이는 창들 [(넓이, hwnd, rect, 최소화여부)]."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value == title and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), hwnd, r, bool(user32.IsIconic(hwnd))))
        return True

    user32.EnumWindows(cb, 0)
    return found


def app_hwnd(title="Dr.Dart-Platform"):
    """제목이 같은 창 중 가장 큰 창 (Electron은 같은 제목의 숨은 창이 더 있어 FindWindow가 엉뚱한 창을 줌). 최소화 창 포함."""
    ws = _windows(title)
    if not ws:
        return None
    normal = [w for w in ws if not w[3]]
    return max(normal or ws, key=lambda x: x[0])[1]


def app_rect(title="Dr.Dart-Platform"):
    ws = [w for w in _windows(title) if not w[3]]
    return max(ws, key=lambda x: x[0])[2] if ws else None


def is_minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


def show_no_activate(hwnd):
    """최소화된 창을 포커스를 빼앗지 않고 원래 크기(최대화였으면 최대화)로 되돌린다."""
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE


def maximize_keep_focus(hwnd):
    """최대화하되, 사용자가 쓰던 창으로 포커스를 돌려준다."""
    fg = user32.GetForegroundWindow()
    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE (활성화가 따라옴)
    give_back_focus(fg, hwnd)


def render_widget(hwnd):
    """Chromium이 키 입력을 받는 자식 창 (Chrome_RenderWidgetHostHWND)."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, buf, 64)
        if buf.value == "Chrome_RenderWidgetHostHWND":
            found.append(h)
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return found[0] if found else hwnd


def post_key(hwnd, vk):
    """포커스 없이 키 한 번 (WM_KEYDOWN/UP을 앱 창에 직접 보냄)."""
    target = render_widget(hwnd)
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.PostMessageW(target, 0x0100, vk, 1 | (scan << 16))
    user32.PostMessageW(target, 0x0101, vk, 1 | (scan << 16) | (0xC0 << 24))


def capture(hwnd):
    """창 내용을 PIL 이미지로 (PrintWindow: 다른 창에 가려져 있어도 앱 화면 그대로)."""
    from PIL import Image
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT (Chromium 필요)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1), (r.left, r.top)


# ---------- 앱이 띄운 Windows 기본 대화상자(파일 열기·저장 등) ----------
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]


def _proc_name(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf, n = ctypes.create_unicode_buffer(520), wt.DWORD(520)
        return buf.value.rsplit("\\", 1)[-1] if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        kernel32.CloseHandle(h)


def native_dialogs(exe="Dr.Dart-Platform.exe"):
    """앱 프로세스가 띄운 보이는 Windows 기본 대화상자(#32770: 파일 열기·저장·메시지 상자) [(hwnd, 제목)].
    Chromium 화면이 아니라 UIA 앱 트리에 안 보임 → 전체 클릭이 Import 아이콘을 눌렀을 때 열린 채 남았음 (2026-10-26)"""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value == "#32770" and user32.IsWindowVisible(h):
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if _proc_name(pid.value).lower() == exe.lower():
                t = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(h, t, 256)
                found.append((h, t.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def close_native_dialogs(exe="Dr.Dart-Platform.exe"):
    """앱의 기본 대화상자를 '취소'로 닫는다 (WM_COMMAND IDCANCEL — 파일을 고르지 않음). 닫은 제목 목록."""
    closed = []
    for h, title in native_dialogs(exe):
        user32.PostMessageW(h, 0x0111, 2, 0)  # WM_COMMAND, IDCANCEL
        closed.append(title or "(제목 없음)")
    if closed:
        import time as _t
        _t.sleep(0.8)
    return closed
