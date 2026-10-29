"""실행 시작 팝업: GitHub 신규 PalletizOS 빌드 확인 → 있으면 **자동 설치**, 진행 상황을 팝업에 표시
(2026-10-27 사용자 요청: 확인을 눈에 보이게 / 수동 선택 없이 자동 설치).

- 최신 버전이면: "최신 버전입니다" 3초 → 닫힘 → 평가
- 새 버전이면: "새 버전 발견 → 자동 설치" → 다운로드 → 설치(앱 재시작·연결·Install from File) → "설치 성공" 3초 → 닫힘 → 평가
- 토큰 없음·접속 실패·설치 실패면: 이유를 보여 주고 5초 뒤 닫힘 → 지금 설치된 버전으로 평가
반환: 새로 설치한 버전(기대 버전으로 씀) 또는 None
"""
import threading
import tkinter as tk
from datetime import datetime, timezone

FONT = "Malgun Gothic"
BG, INK, SUB, ACC, GREEN, AMBER, RED = "#121721", "#f3f4f6", "#9aa3b2", "#7cc4ff", "#1f9d55", "#d89614", "#d64545"
TITLE = "PalletizOS 스모크 — 신규 버전 확인"


def _local(iso):
    """'2026-10-26T13:59:04Z' → '10-26 22:59' (이 PC 시간대)."""
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone().strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def check_and_install(log=print):
    from . import github
    from .installer import install_dm, installed_version
    from .watcher import newest_build, vkey

    res = {"done": False, "got": None}
    root = tk.Tk()
    root.title(TITLE)
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.resizable(False, False)
    w, h = 660, 330
    from .done_popup import _center_on_app_monitor
    x, y = _center_on_app_monitor(w, h, root)  # 앱이 있는 모니터 가운데 (주 모니터에 뜨면 못 봄)
    root.geometry(f"{w}x{h}+{x}+{y}")
    tk.Label(root, text="GitHub 신규 버전 확인 · 자동 설치", font=(FONT, 16, "bold"), fg=INK, bg=BG).pack(anchor="w", padx=24, pady=(20, 2))
    tk.Label(root, text=f"GitHub {github.REPO} 릴리스와 지금 설치된 버전을 비교해, 새 빌드가 있으면 자동으로 설치합니다",
             font=(FONT, 9), fg=SUB, bg=BG, wraplength=w - 48, justify="left").pack(anchor="w", padx=24)
    status = tk.Label(root, text="확인 중…", font=(FONT, 13, "bold"), fg=ACC, bg=BG, justify="left", anchor="w")
    status.pack(fill="x", padx=24, pady=(20, 4))
    detail = tk.Label(root, text="", font=(FONT, 10), fg=SUB, bg=BG, justify="left", anchor="w", wraplength=w - 48)
    detail.pack(fill="x", padx=24)
    step = tk.Label(root, text="", font=(FONT, 10), fg=ACC, bg=BG, justify="left", anchor="w", wraplength=w - 48)
    step.pack(fill="x", padx=24, pady=(10, 0))
    foot = tk.Label(root, text="", font=(FONT, 9), fg=SUB, bg=BG, anchor="w")
    foot.pack(side="bottom", fill="x", padx=24, pady=14)

    def ui(fn):
        root.after(0, fn)

    def close_in(sec, text):
        def go():
            if not res["done"]:
                res["done"] = True
                root.destroy()
        ui(lambda: foot.config(text=text))
        root.after(int(sec * 1000), go)

    def set_(s=None, color=None, d=None, st=None):
        def apply():
            if s is not None:
                status.config(text=s, fg=color or ACC)
            if d is not None:
                detail.config(text=d)
            if st is not None:
                step.config(text=st)
        ui(apply)

    def work():
        # 감시기 등 다른 프로세스가 설치 중이면 끝날 때까지 기다린다 — 겹쳐 설치·평가하면 서로 앱을 꺼 버림 (2026-10-29 실측)
        from .installer import install_busy
        import time
        t0 = time.time()
        while (busy := install_busy()) and time.time() - t0 < 900:
            set_("다른 프로그램이 설치 중 — 끝날 때까지 기다립니다", AMBER,
                 f"설치 중인 프로세스 pid {busy} (예: 데일리 감시기) · {int(time.time() - t0)}초 대기 중 · 최대 15분",
                 "Dr.Dart 앱을 조작하지 마세요")
            time.sleep(5)
        try:
            cur = installed_version()
            nb = newest_build()
        except github.GitHubError as e:
            set_("신규 버전을 확인하지 못함 — 지금 설치된 버전으로 평가합니다", AMBER, f"{e}  (토큰 등록: github_setup.bat)")
            close_in(5, "5초 뒤 평가를 시작합니다")
            return
        except Exception as e:  # noqa: BLE001
            set_("신규 버전을 확인하지 못함 — 지금 설치된 버전으로 평가합니다", AMBER, f"{type(e).__name__}: {e}")
            close_in(5, "5초 뒤 평가를 시작합니다")
            return
        if nb is None:
            set_("릴리스에 PalletizOS 설치 파일이 없음 — 지금 버전으로 평가합니다", AMBER, f"설치됨 {cur}")
            close_in(4, "4초 뒤 평가를 시작합니다")
            return
        ver, rel, asset = nb
        pub = _local(rel.get("published"))
        if cur and vkey(ver) <= vkey(cur):
            set_(f"최신 버전입니다  ·  설치 {cur}", GREEN, f"GitHub 최신 릴리스 {ver} ({pub} 공개) — 새 빌드 없음")
            close_in(3, "3초 뒤 평가를 시작합니다")
            return
        set_(f"새 버전 발견  ·  {ver}  →  자동 설치합니다", AMBER,
             f"지금 설치 {cur or '알 수 없음'} · 릴리스 {rel['tag']} ({pub} 공개, {asset['size'] / 1e6:.1f} MB)",
             "① 내려받는 중…")
        ui(lambda: foot.config(text="설치하는 동안 Dr.Dart 앱이 재시작됩니다. 앱을 조작하지 마세요 (약 2분)"))
        try:
            path = github.download(rel, pick=lambda n: n == asset["name"])[0]
            set_(st="② 설치 중 — 앱 재시작 → 제어기 연결 → Settings → Installed Module List → Install from File")

            def ilog(m):
                log(m)
                set_(st=f"② 설치 중 — {m}")
            got = install_dm(path, log=ilog)
        except Exception as e:  # noqa: BLE001
            set_(f"설치 실패 — 지금 설치된 버전({cur})으로 평가합니다", RED, str(e)[:300], "")
            close_in(6, "6초 뒤 평가를 시작합니다 (원인은 results\\events.log)")
            return
        res["got"] = got
        set_(f"설치 성공  ·  PalletizOS {got}", GREEN, f"{cur} → {got}", "③ 이어서 스모크 전체 실행을 시작합니다")
        close_in(3, "3초 뒤 평가를 시작합니다")

    threading.Thread(target=work, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", lambda: None)  # 설치 도중 실수로 닫지 않게 (끝나면 저절로 닫힘)
    root.mainloop()
    return res["got"]
