"""실행 상태 오버레이 (별도 프로세스). 러너가 쓰는 상태 JSON을 읽어 앱 창 우측 상단에 표시한다.

- 클릭 통과(WS_EX_TRANSPARENT)·포커스 안 가져감(WS_EX_NOACTIVATE) → 자동화 클릭을 방해하지 않음
- 상태에 hidden=true면 잠시 숨김 (실패 스크린샷에 오버레이가 찍히지 않게)
- 러너 프로세스가 끝나면 최종 결과를 linger초 보여준 뒤 스스로 닫힘
사용: pythonw overlay.py <status.json> <runner_pid>
"""
import ctypes
import ctypes.wintypes as wt
import json
import sys
import time
import tkinter as tk
from pathlib import Path

from winutil import app_rect  # 같은 폴더 (overlay.py는 스크립트로 실행됨)

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

PATH, PID = sys.argv[1], int(sys.argv[2])
MODE = sys.argv[3] if len(sys.argv) > 3 else "background"
STOP = Path(PATH).with_name("stop.flag")
EVLOG = Path(PATH).with_name("events.log")  # 실행기 사건 기록과 같은 파일 (시간순으로 함께 보이게)


def evlog(msg):
    """종료 요청 등 표시창에서 일어난 일을 기록 (원인 추적용, 2026-10-22: 이유 모를 '종료 요청' 2회)."""
    try:
        with open(EVLOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "[표시창] " + msg + chr(10))
    except OSError:
        pass
APP_TITLE = "Dr.Dart-Platform"
BADGE = {"ING": "#2f6fd6", "PASS": "#1f9d55", "FAIL": "#d64545", "WARN": "#d89614", "N/A": "#6b7280", "SKIP": "#6b7280", "WAIT": "#6b7280", "STOP": "#b45309"}
CHIP = {"pass": "#1f9d55", "warn": "#d89614", "flaky": "#d89614", "fail": "#d64545",
        "na": "#4b5563", "env": "#2f6fd6", "run": "#e5e7eb", None: "#2a3140"}
BG, INK, SUB, ACC = "#121721", "#f3f4f6", "#9aa3b2", "#7cc4ff"
FONT = "Malgun Gothic"


def runner_alive():
    h = kernel32.OpenProcess(0x00100000, False, PID)  # SYNCHRONIZE
    if not h:
        return False
    alive = kernel32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT
    kernel32.CloseHandle(h)
    return alive


root = tk.Tk()
root.title("PalletizOS Smoke Overlay")
root.overrideredirect(True)
root.attributes("-topmost", True)
try:  # 투명도: elements.yaml의 overlay_alpha (0.3~1.0, 낮을수록 투명)
    import yaml
    from pathlib import Path
    _cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "elements.yaml").read_text(encoding="utf-8"))
    ALPHA = min(1.0, max(0.3, float(_cfg.get("overlay_alpha", 0.72))))
except Exception:
    ALPHA = 0.72
root.attributes("-alpha", ALPHA)
root.configure(bg=BG)
scale = root.winfo_fpixels("1i") / 96.0
W = int(440 * scale)

pad = int(14 * scale)
box = tk.Frame(root, bg=BG, padx=pad, pady=int(12 * scale))
box.pack(fill="both", expand=True)
top = tk.Frame(box, bg=BG)
top.pack(fill="x")
badge = tk.Label(top, text="ING", font=(FONT, 22, "bold"), fg="white", bg=BADGE["ING"], padx=int(14 * scale))
badge.pack(side="left")
head = tk.Frame(top, bg=BG, padx=int(12 * scale))
head.pack(side="left", fill="x", expand=True)
title = tk.Label(head, text="PalletizOS 스모크", font=(FONT, 10), fg=SUB, bg=BG, anchor="w")
title.pack(fill="x")
stop_btn = None
if MODE != "mouse":  # 백그라운드 방식은 자동화가 마우스를 안 쓰므로 이 창을 눌러도 됨
    _arm = {"t": 0}

    def _cursor():
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def on_stop():
        now = time.time()
        gap = now - _arm["t"]
        if gap > 3:  # 실수 방지: 첫 번째 누름 = 확인 대기
            _arm["t"] = now
            evlog(f"■ 자동화 종료 첫 번째 누름 (마우스 {_cursor()}) → 확인 대기")
            stop_btn.config(text="한번 더", bg="#b45309")
            root.after(3000, lambda: stop_btn.config(text="■ 종료", bg="#3a4252") if stop_btn["text"] != "종료 중" else None)
            return
        if gap < 0.6:
            # 빠른 더블클릭은 종료로 치지 않음 — 표시창을 옮기려고 위쪽을 두 번 누른 경우 등 (2026-10-22 '안 눌렀는데 종료됨')
            evlog(f"■ 자동화 종료 빠른 더블클릭({gap:.2f}초) 무시 — 0.6~3초 사이에 다시 눌러야 종료")
            return
        evlog(f"■ 자동화 종료 확인 누름 ({gap:.1f}초 뒤, 마우스 {_cursor()}) → stop.flag")
        STOP.write_text("stop", encoding="utf-8")
        stop_btn.config(text="종료 중", state="disabled", bg="#6b7280")

    stop_btn = tk.Button(top, text="■ 종료", command=on_stop,  # 짧게: "■ 자동화 종료"는 진행 줄이 길면 잘렸음 (2026-10-27) font=(FONT, 9, "bold"), fg="white", bg="#3a4252",
                         activebackground="#b45309", activeforeground="white", relief="flat", bd=0, takefocus=0,
                         padx=int(8 * scale), pady=int(4 * scale), cursor="hand2")
    stop_btn.pack(side="right", anchor="n")
flow = tk.Label(head, text="", font=(FONT, 13, "bold"), fg=INK, bg=BG, anchor="w", justify="left")
flow.pack(fill="x")
desc = tk.Label(box, text="", font=(FONT, 10), fg=SUB, bg=BG, anchor="w", justify="left", wraplength=W - 2 * pad)
desc.pack(fill="x", pady=(int(8 * scale), 0))
step = tk.Label(box, text="", font=(FONT, 11, "bold"), fg=ACC, bg=BG, anchor="w", justify="left", wraplength=W - 2 * pad)
step.pack(fill="x", pady=(int(6 * scale), 0))
action = tk.Label(box, text="", font=(FONT, 9), fg=SUB, bg=BG, anchor="w", justify="left", wraplength=W - 2 * pad)
action.pack(fill="x")
last = tk.Label(box, text="", font=(FONT, 9), fg="#c9ced8", bg=BG, anchor="w", justify="left", wraplength=W - 2 * pad)
last.pack(fill="x", pady=(int(4 * scale), 0))
chips = tk.Frame(box, bg=BG)
chips.pack(fill="x", pady=(int(10 * scale), 0))
MAX_CHIPS = 30  # 6줄 × 5


def window_chips(allc, limit=None, lookahead=4):
    """칩이 limit(6줄=30)보다 많을 때 보일 30칸 창.
    - 끝난 칩은 결과 색 그대로 계속 보인다 (2026-10-22 사용자 요청: 수행한 칩 색 유지)
    - 창 끝은 '진행 중 + 다음 대기 lookahead개'까지 → 칸이 모자라면 가장 오래된(앞쪽) 칩부터 사라진다
    - 그 뒤 대기 칩은 아직 안 보임 ("대기 n개 더 있음")
    반환: (보일 칩, 숨긴 끝난 항목 상태 목록, 안 보이는 대기 수)"""
    limit = limit or MAX_CHIPS
    if len(allc) <= limit:
        return list(allc), [], 0
    cur = next((i for i, (_, st) in enumerate(allc) if st in (None, "run")), len(allc))  # 진행 중(또는 첫 대기) 위치
    end = min(len(allc), max(limit, cur + 1 + lookahead))
    start = end - limit
    shown = allc[start:end]
    hidden = [st for _, st in allc[:start]]
    waiting = sum(1 for _, st in allc[end:] if st is None)
    return shown, hidden, waiting
more = tk.Label(box, text="", font=(FONT, 8), fg=SUB, bg=BG, anchor="w")
legend = tk.Frame(box, bg=BG)
legend.pack(fill="x", pady=(int(4 * scale), 0))
# 범례 = 칩 색과 1:1 (2026-10-27 점검: 환경 오류(파랑) 범례 없음, '대기·해당없음'을 한 색으로 묶어 해당없음 칩 색과 달랐음)
for _name, _st in (("통과", "pass"), ("실패", "fail"), ("주의·불안정", "warn"), ("환경 오류", "env"), ("해당없음", "na"),
                   ("진행", "run"), ("대기", None)):
    tk.Label(legend, text="■", font=(FONT, 9), fg=CHIP[_st], bg=BG).pack(side="left")
    tk.Label(legend, text=_name + " ", font=(FONT, 8), fg=SUB, bg=BG).pack(side="left")
if MODE != "mouse":
    tk.Label(box, text="칩을 두 번 누르면 그 항목만 바로 다시 실행 (진행 중이면 멈춘 뒤 실행)", font=(FONT, 8),
             fg=SUB, bg=BG, anchor="w").pack(fill="x", pady=(int(2 * scale), 0))
bottom = tk.Frame(box, bg=BG)
bottom.pack(fill="x", pady=(int(8 * scale), 0))
foot = tk.Label(bottom, text="", font=(FONT, 9), fg=SUB, bg=BG, anchor="w", justify="left", wraplength=W - int(110 * scale))
foot.pack(side="left", fill="x", expand=True)
PAUSE = Path(PATH).with_name("pause.flag")
if MODE != "mouse":
    def on_add():
        """시나리오 녹화 창 열기 (녹화하는 동안 자동화는 일시정지, 저장한 시나리오는 다음 실행부터 포함)."""
        import subprocess
        root_dir = Path(__file__).resolve().parent.parent
        subprocess.Popen([sys.executable, "-m", "autotest.recorder"], cwd=str(root_dir))

    add_btn = tk.Button(bottom, text="＋ 추가", command=on_add, font=(FONT, 9, "bold"), fg="white", bg="#1f6f4a",
                        activebackground="#1f9d55", activeforeground="white", relief="flat", bd=0, takefocus=0,
                        padx=int(8 * scale), pady=int(3 * scale), cursor="hand2")
    add_btn.pack(side="right", anchor="s")
chip_widgets = {}
chip_of, chip_text = {}, {}


_own = {"hwnd": None, "owner": None}


def make_passthrough():
    root.update_idletasks()
    if _own["hwnd"] is None:  # 소유 창을 붙인 뒤에는 GetParent가 앱 창을 돌려주므로 처음 값만 쓴다
        _own["hwnd"] = user32.GetParent(root.winfo_id()) or root.winfo_id()
    hwnd = _own["hwnd"]
    GWL_EXSTYLE = -20
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    # LAYERED | TOOLWINDOW(작업표시줄 제외) | NOACTIVATE(눌러도 포커스 안 가져감) | TOPMOST
    # mouse 모드만 TRANSPARENT(클릭 통과): 실제 마우스 클릭이 이 창에 막히지 않게
    style = ex | 0x80000 | 0x80 | 0x08000000 | 0x8 | (0x20 if MODE == "mouse" else 0)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    return hwnd


# 위치: 앱 창 오른쪽 위 모서리 기준 상대 위치(dx, dy). 드래그로 옮기면 저장 → 앱 창이 움직여도 따라가고 다음 실행에도 유지
POS_FILE = Path(PATH).with_name("overlay_pos.json")


def _load_pos():
    try:
        d = json.loads(POS_FILE.read_text(encoding="utf-8"))
        return int(d["dx"]), int(d["dy"])
    except Exception:
        return None


_pos = {"off": _load_pos(), "drag": None}


def _anchor():
    r = app_rect(APP_TITLE)
    if r is not None:
        return r.right, r.top
    return user32.GetSystemMetrics(0), 0  # 앱 창이 없으면 주 모니터 우측 상단


user32.MonitorFromWindow.restype = ctypes.c_void_p  # HMONITOR는 포인터 크기 — 기본(int)이면 64비트에서 잘릴 수 있음
user32.MonitorFromPoint.restype = ctypes.c_void_p
user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]


class _MI(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def _work_area(x, y):
    """(x, y)가 속한 모니터의 작업 영역 (없으면 가장 가까운 모니터)."""
    mon = user32.MonitorFromPoint(wt.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
    mi = _MI(ctypes.sizeof(_MI))
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    return mi.rcWork


def _app_work_area():
    """앱 창이 가장 많이 걸친 모니터의 작업 영역 (MonitorFromWindow). 앱 창이 없으면 None."""
    from winutil import app_hwnd
    h = app_hwnd(APP_TITLE)
    if not h:
        return None
    mon = user32.MonitorFromWindow(h, 2)  # MONITOR_DEFAULTTONEAREST
    mi = _MI(ctypes.sizeof(_MI))
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    return mi.rcWork


def place():
    if _pos["drag"] is not None:
        return  # 끄는 중에는 자동 배치 안 함
    right, topy = _anchor()
    root.update_idletasks()
    h = root.winfo_reqheight()
    default = (-W - int(24 * scale), int(70 * scale))
    # 저장한 위치는 앱 창 기준이므로 앱 창이 있을 때만 쓴다. 앱이 아직 없을 때(시뮬레이터·앱 시작 중) 저장 위치를 주 모니터에
    # 적용하면 화면 밖으로 나가 표시창이 '사라짐' (2026-10-22 실측: 4K 모니터 기준 dy=1077 → 1080 주 모니터 아래로 벗어남)
    dx, dy = (_pos["off"] if _pos["off"] and app_rect(APP_TITLE) is not None else default)
    x, y = right + dx, topy + dy
    # 앱 창이 있는 모니터 안으로 제한. 모서리 점(right-1, top+1)으로 고르면 최대화 창은 가장자리가 화면 밖으로 8px 넓어져
    # 오른쪽 옆 모니터가 골라짐 → 표시창이 옆 모니터로 가서 '사라짐' (2026-10-27 실측: 최대화 rect −8~1928, 모니터 경계 1920)
    wa = _app_work_area() or _work_area(right - 40, topy + 40)
    x = max(wa.left, min(x, wa.right - W))
    y = max(wa.top, min(y, wa.bottom - h))
    root.geometry(f"{W}x{h}+{x}+{y}")


def _drag_start(e):
    _pos["drag"] = (e.x_root - root.winfo_x(), e.y_root - root.winfo_y())
    _pos["press"] = (e.x_root, e.y_root)


def _drag_move(e):
    if _pos["drag"] is None:
        return
    ox, oy = _pos["drag"]
    root.geometry(f"+{e.x_root - ox}+{e.y_root - oy}")


def _drag_end(e):
    if _pos["drag"] is None:
        return
    _pos["drag"] = None
    px, py = _pos.get("press") or (e.x_root, e.y_root)
    if abs(e.x_root - px) <= 4 and abs(e.y_root - py) <= 4:  # 끌지 않고 누르기만 함 = 클릭
        tc = chip_of.get(e.widget)
        if tc:
            on_chip(tc)
        return
    right, topy = _anchor()
    _pos["off"] = (root.winfo_x() - right, root.winfo_y() - topy)
    try:
        POS_FILE.write_text(json.dumps({"dx": _pos["off"][0], "dy": _pos["off"][1]}), encoding="utf-8")
    except OSError:
        pass


def enable_drag(widget):
    """버튼이 아닌 곳(배경·글자)을 끌어서 창 이동. 자식까지 재귀 적용."""
    if isinstance(widget, tk.Button):
        return
    widget.bind("<ButtonPress-1>", _drag_start)
    widget.bind("<B1-Motion>", _drag_move)
    widget.bind("<ButtonRelease-1>", _drag_end)
    for c in widget.winfo_children():
        enable_drag(c)


def render(s):
    b = s.get("badge", "ING")
    badge.config(text=b, bg=BADGE.get(b, BADGE["ING"]))
    idx, total = s.get("index"), s.get("total")
    # 진행 중엔 'PalletizOS 스모크'를 빼고 진행·집계만 → 제목 줄이 길어져 종료 버튼이 눌리지 않게
    title.config(text=(f"{idx}/{total}" + (f"  ·  {s['tally']}" if s.get("tally") else "")) if idx else "PalletizOS 스모크")
    flow.config(text=s.get("flow", ""))
    desc.config(text=s.get("desc", ""))
    step.config(text=("▶ " + s["step"]) if s.get("step") else "")
    action.config(text=s.get("action", ""))
    last.config(text=s.get("last", ""))
    if stop_btn is not None and s.get("done"):
        stop_btn.pack_forget()
    foot.config(text=s.get("foot", "자동화 실행 중 · 마우스/키보드를 만지지 마세요" if MODE == "mouse"
                           else "백그라운드 실행 중 · 다른 업무를 해도 됩니다 (앱 창 최소화만 하지 마세요)"))
    labels = s.get("chip_labels", {})
    allc = [tuple(c) for c in s.get("chips", [])]  # JSON에서는 리스트 → 비교·삭제가 되게 튜플로
    shown, hidden_done, waiting_cut = window_chips(allc)
    for w in chip_widgets.values():
        w.grid_forget()
    for i, (tc, st) in enumerate(shown):
        w = chip_widgets.get(tc)
        if w is None:  # 번호 + 짧은 이름, 한 줄에 5개씩
            # 5칸 같은 폭(uniform), 글자 8pt — 이름을 붙인 칩이 표시창 폭을 넘어 잘리지 않게 (2026-10-19 영상 캡처 때 발견)
            w = tk.Label(chips, text=labels.get(tc, tc), font=(FONT, 8, "bold"), padx=int(2 * scale), pady=int(2 * scale),
                         width=1, anchor="center")
            if MODE != "mouse":
                enable_drag(w)
                w.config(cursor="hand2")
                chip_of[w] = tc
            chip_widgets[tc] = w
            chip_text[tc] = labels.get(tc, tc)
        w.grid(row=i // 5, column=i % 5, padx=(0, int(3 * scale)), pady=(0, int(3 * scale)), sticky="we")
        chips.grid_columnconfigure(i % 5, weight=1, uniform="chip")
        w.config(bg=CHIP.get(st, CHIP[None]), fg="#111827" if st == "run" else "white")
    if hidden_done or waiting_cut:
        n_ok = sum(st in ("pass", "na", "env") for st in hidden_done)
        n_bad = len(hidden_done) - n_ok
        parts = []
        if hidden_done:
            parts.append(f"끝난 항목 {len(hidden_done)}개 숨김 (통과·해당없음 {n_ok}" + (f" · 실패·주의 {n_bad}" if n_bad else "") + ")")
        if waiting_cut:
            parts.append(f"대기 {waiting_cut}개 더 있음")
        more.config(text=" · ".join(parts))
        more.pack(fill="x", after=chips, pady=(0, int(2 * scale)))
    else:
        more.pack_forget()


# ---------- 칩 클릭 = 그 항목만 실행 (2026-10-22 사용자 요청) ----------
# 실수 방지: 3초 안에 두 번 눌러야 실행. 진행 중이면 지금 실행을 멈추게 하고(stop.flag),
# 러너가 원상복구까지 끝내고 종료한 뒤에 새 실행을 띄운다 (두 러너가 같은 앱을 동시에 조작하지 않게)
ROOT_DIR = Path(__file__).resolve().parent.parent
_chip = {"armed": None, "t": 0, "pending": None}
_final = {}  # 실행이 끝났을 때의 최종 배지 (STOP이면 사용자가 멈춘 것)


def _launch(tc):
    import subprocess
    subprocess.Popen(["cmd", "/c", "start", f"PalletizOS 스모크 {tc}", "cmd", "/c",
                      str(ROOT_DIR / "run_one.bat"), tc], cwd=str(ROOT_DIR))


def on_chip(tc):
    if _chip["pending"]:
        return
    if done_at is not None or _final:
        # 실행이 이미 끝남 → 새로 실행하지 않음 (다시 돌리려면 바탕화면 아이콘)
        foot.config(text="실행이 끝났습니다. 다시 실행하려면 바탕화면 PalletizOS_smoke.bat", fg="#ffd27a")
        return
    now = time.time()
    if _chip["armed"] == tc and now - _chip["t"] < 0.6:
        return  # 빠른 더블클릭은 무시 (끌어서 옮기려다 누른 경우) — 0.6~3초 사이 두 번째 누름만 실행
    if _chip["armed"] != tc or now - _chip["t"] > 3:
        if _chip["armed"] in chip_widgets:
            chip_widgets[_chip["armed"]].config(text=chip_text[_chip["armed"]])
        _chip.update(armed=tc, t=now)
        chip_widgets[tc].config(text="▶ 한 번 더")
        root.after(3000, lambda: chip_widgets[tc].config(text=chip_text[tc]) if _chip["armed"] == tc and not _chip["pending"] else None)
        return
    _chip.update(armed=None, pending=tc)
    chip_widgets[tc].config(text="▶ 대기")
    if runner_alive() and done_at is None:
        # 즉시 실행: 지금 실행을 멈추게 하고(원상복구 후 종료) 러너가 끝나면 바로 이 항목만 실행 (2026-10-22 사용자 선택)
        evlog(f"칩 {tc} 두 번 눌림 → 지금 실행 멈추고 {tc}만 실행 (stop.flag)")
        STOP.write_text("stop", encoding="utf-8")
        foot.config(text=f"{tc}만 실행하려고 지금 실행을 멈추는 중 (원래 상태로 되돌린 뒤 10~20초 안에 시작)", fg="#ffd27a")
    else:
        foot.config(text=f"{tc}만 실행 시작", fg="#ffd27a")


last_raw, hidden, done_at, linger = None, False, None, 20
make_passthrough()
if MODE != "mouse":  # mouse 모드는 클릭이 통과하는 창이라 끌 수 없음
    enable_drag(root)
    root.config(cursor="fleur")


_top = {"t": 0.0}


def keep_on_top():
    """1초마다 맨 위로 다시 올림 (포커스는 안 가져감). Dr.Dart 앱이 전체 화면이 되면 앱도 맨 위 계층이 되어
    나중에 앞으로 나온 앱이 표시창을 덮음 → 시나리오 박스가 사라져 보였음 (2026-10-27 사용자 요청)."""
    now = time.time()
    if now - _top["t"] < 1.0:
        return
    _top["t"] = now
    h = _own.get("hwnd") or user32.GetParent(root.winfo_id()) or root.winfo_id()
    # HWND_TOPMOST, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    user32.SetWindowPos(h, -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010 | 0x0200)


def tick():
    global last_raw, hidden, done_at, linger
    if PAUSE.exists():  # 시나리오 녹화 중 → 자동화 일시정지 표시
        foot.config(text="● 시나리오 녹화 중 — 자동화 일시정지", fg="#ff8a8a")
    elif foot.cget("fg") == "#ff8a8a":
        foot.config(fg=SUB)
        last_raw = None  # 원래 문구로 다시 그리기
    try:
        with open(PATH, encoding="utf-8") as f:
            raw = f.read()
        if raw != last_raw:
            last_raw = raw
            s = json.loads(raw)
            linger = s.get("linger", linger)
            render(s)
            if s.get("hidden") and not hidden:
                root.withdraw()
                hidden = True
            elif not s.get("hidden") and hidden:
                root.deiconify()
                make_passthrough()
                hidden = False
            if s.get("done") and done_at is None:
                done_at = time.time()
            if s.get("done"):
                _final["badge"] = s.get("badge")
    except (OSError, ValueError):
        pass  # 러너가 쓰는 중 — 다음 주기에 다시 읽음
    if not hidden:
        place()
        keep_on_top()
    if done_at is None and not runner_alive():
        done_at = time.time()
    if _chip["pending"] and not runner_alive():
        # 칩으로 '지금 실행 멈추고 이 항목만'을 요청해 멈춘 경우에만 이어서 실행.
        # 실행이 끝까지 정상 완료됐으면 더 진행하지 않음 (2026-10-26 사용자 요청: 완료되면 리포트만 내고 종료)
        if _final.get("badge") == "STOP":
            _launch(_chip["pending"])
        else:
            evlog(f"실행이 끝까지 완료돼 예약된 칩 {_chip['pending']} 실행은 취소")
        root.destroy()
        return
    if done_at is not None and time.time() - done_at > linger:
        root.destroy()
        return
    root.after(300, tick)


tick()
root.mainloop()
