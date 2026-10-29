"""실행 완료 창 (2026-10-27 사용자 요청: 모든 칩이 끝나면 '자동화 수행 완료' + 결과 리포트).
러너가 끝날 때 별도 프로세스로 띄운다(러너는 바로 끝나도 창은 남음). 2분 뒤 저절로 닫힘.
사용: pythonw -m autotest.done_popup <상태 JSON 경로>
"""
import json
import sys
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path

EVENTS = Path(__file__).resolve().parent.parent / "results" / "events.log"


def evlog(msg):
    """완료 창이 실제로 떴는지·눌렸는지 기록 (2026-10-27: 창이 안 보였다는 신고 — 근거를 남김)."""
    try:
        with open(EVENTS, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [완료창] {msg}\n")
    except OSError:
        pass

FONT = "Malgun Gothic"
BG, INK, SUB = "#121721", "#f3f4f6", "#9aa3b2"
COLOR = {"통과": "#1f9d55", "통과(주의)": "#d89614", "보류": "#d64545", "재실행 필요": "#2f6fd6", "중단": "#b45309"}
MEAN = {"통과": "모든 항목 정상 → 매뉴얼 테스트 진행", "통과(주의)": "화면은 정상, 새 로그 에러·재시도 통과 있음 → 로그 확인 후 매뉴얼 테스트",
        "보류": "FAIL 항목 있음 → 리포트에서 원인 확인 (결함이면 이슈 등록)", "재실행 필요": "환경 오류로 일부 항목 확인 못 함 → 환경 조치 후 다시 실행",
        "중단": "종료 요청으로 멈춤 → 다시 실행"}


def _center_on_app_monitor(w, h, root):
    """Dr.Dart 앱이 있는 모니터 가운데. 주 모니터 가운데에 띄우면 앱·표시창을 둘째 모니터에 둔 사용자가 못 봄
    (2026-10-27 실측: 창은 주 모니터 456,192 에 떴는데 '완료 창이 안 뜬다'는 신고). 앱 창이 없으면 주 모니터."""
    try:
        import ctypes
        import ctypes.wintypes as wt
        from .winutil import app_hwnd

        class _MI(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]
        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        hwnd = app_hwnd()
        if hwnd:
            mi = _MI(ctypes.sizeof(_MI))
            if user32.GetMonitorInfoW(ctypes.c_void_p(user32.MonitorFromWindow(hwnd, 2)), ctypes.byref(mi)):
                r = mi.rcWork
                return r.left + (r.right - r.left - w) // 2, r.top + (r.bottom - r.top - h) // 3
    except Exception:  # noqa: BLE001
        pass
    return (root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 3


def main(path):
    d = json.loads(open(path, encoding="utf-8").read())
    v = d["verdict"]
    done = v != "중단"
    root = tk.Tk()
    root.title("PalletizOS 스모크 — 자동화 수행 완료" if done else "PalletizOS 스모크 — 자동화 중단")
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.resizable(False, False)
    w, h = 640, 380
    pos = (-4000, 0) if "--offscreen" in sys.argv else _center_on_app_monitor(w, h, root)
    root.geometry(f"{w}x{h}+{pos[0]}+{pos[1]}")  # --offscreen: 화면 밖에 그려 캡처 확인용 (사용자 화면에 안 뜸)
    tk.Label(root, text="자동화 수행 완료" if done else "자동화 중단됨", font=(FONT, 22, "bold"), fg=INK, bg=BG).pack(pady=(26, 6))
    tk.Label(root, text=f"PalletizOS {d.get('version') or ''} · {d.get('started', '')} ~ {d.get('finished', '')} · {d.get('minutes', '?')}분 · 항목 {d.get('total')}개",
             font=(FONT, 10), fg=SUB, bg=BG).pack()
    tk.Label(root, text=f"전체 판정: {v}", font=(FONT, 18, "bold"), fg="white", bg=COLOR.get(v, "#6b7280"), padx=18, pady=6).pack(pady=(18, 6))
    tk.Label(root, text=MEAN.get(v, ""), font=(FONT, 10), fg=INK, bg=BG).pack()
    tk.Label(root, text="  ·  ".join(f"{k} {n}" for k, n in d.get("counts", {}).items()), font=(FONT, 12, "bold"), fg=INK, bg=BG).pack(pady=(12, 0))
    if d.get("fails"):
        tk.Label(root, text="실패: " + ", ".join(d["fails"][:10]), font=(FONT, 9), fg="#ff8a8a", bg=BG, wraplength=w - 48).pack(pady=(6, 0))
    bar = tk.Frame(root, bg=BG)
    bar.pack(side="bottom", pady=18)

    def open_report():
        url = d["report"]
        if "127.0.0.1:8781" in url:
            # 이슈 등록 서버는 3시간 쉬면 스스로 꺼지고 재부팅 후엔 없음 → 열기 전에 다시 띄움, 안 되면 파일로 엶
            # (2026-10-29: 10-27 리포트 주소가 안 열린다는 신고)
            try:
                from .issue_server import ensure_running
                if not ensure_running():
                    raise OSError("server not running")
            except Exception:  # noqa: BLE001
                url = Path(path).with_name("report.html").resolve().as_uri()
        ok = webbrowser.open(url)
        evlog(f"[결과 리포트 열기] 누름 → 브라우저 열기 {'성공' if ok else '실패'}")
    tk.Button(bar, text="결과 리포트 열기", command=open_report, font=(FONT, 11, "bold"), fg="white", bg="#1f6f4a",
              relief="flat", padx=16, pady=6).pack(side="left", padx=6)
    tk.Button(bar, text="닫기", command=lambda: close(), font=(FONT, 11), fg=INK, bg="#3a4252", relief="flat", padx=16, pady=6).pack(side="left", padx=6)
    tk.Label(root, text="리포트는 브라우저로 자동으로 열렸습니다 · 이 창은 2분 뒤 닫힙니다", font=(FONT, 9), fg=SUB, bg=BG).pack(side="bottom")
    def front():
        # 다른 창(Dr.Dart 최대화·브라우저)에 가리지 않게 맨 앞으로 — 몇 번 반복
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()

    for ms in (100, 1000, 3000, 8000):
        root.after(ms, front)
    if "--offscreen" not in sys.argv:
        root.after(500, lambda: evlog(f"표시됨: {'자동화 수행 완료' if done else '자동화 중단됨'} · 판정 {v} · "
                                      f"위치 {root.winfo_rootx()},{root.winfo_rooty()} · 2분 뒤 자동 닫힘"))

    def auto_close():
        evlog("2분 지나 자동으로 닫힘")
        root.destroy()

    def close():
        evlog("[닫기] 누름")
        root.destroy()
    root.after(120000, auto_close)
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main(sys.argv[1])
