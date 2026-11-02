"""TC·체크리스트 엑셀 가져오기 화면.

[엑셀 가져오기] → 파일 선택 → 행마다 자동 점검 루틴 매칭 결과 미리보기 → [자동 평가 시작] → 새 콘솔에서 tc_run.py 실행.
사용: pythonw -m tc_autotest.import_gui [엑셀 경로]
"""
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tc_autotest.checks import CHECKS, match_check, nt_reason  # noqa: E402
from tc_autotest.workbook import read_rows  # noqa: E402

FONT = "Malgun Gothic"
TITLES = {c["key"]: c["title"] for c in CHECKS}


class App:
    def __init__(self, path=None):
        self.path, self.rows = None, []
        r = self.root = tk.Tk()
        r.title("PalletizOS TC 자동 평가 — 엑셀 가져오기")
        w, h = 1100, 680
        try:
            from autotest.done_popup import _center_on_app_monitor
            x, y = _center_on_app_monitor(w, h, r)
        except Exception:  # noqa: BLE001
            x, y = 100, 80
        r.geometry(f"{w}x{h}+{x}+{max(0, y - 120)}")
        top = tk.Frame(r, padx=16, pady=12)
        top.pack(fill="x")
        tk.Label(top, text="TC · 체크리스트 자동 평가", font=(FONT, 16, "bold")).pack(anchor="w")
        tk.Label(top, text="엑셀을 가져오면 행마다 자동 점검 루틴을 찾아 PalletizOS 앱에서 판정하고, "
                           "원본 옆에 '<이름>_자동판정_<시각>.xlsx' 사본으로 Result·Comment 를 채웁니다. "
                           "자동 점검이 없는 행은 NT(수동)로 남기고 이유를 적습니다.",
                 font=(FONT, 9), fg="#555", wraplength=w - 40, justify="left").pack(anchor="w", pady=(4, 8))
        bar = tk.Frame(top)
        bar.pack(fill="x")
        tk.Button(bar, text="엑셀 가져오기…", font=(FONT, 11, "bold"), command=self.pick, padx=12).pack(side="left")
        self.file = tk.Label(bar, text="(파일을 고르세요 — .xlsx)", font=(FONT, 10), fg="#333")
        self.file.pack(side="left", padx=12)
        self.sumlab = tk.Label(top, text="", font=(FONT, 11, "bold"), fg="#1f6f4a")
        self.sumlab.pack(anchor="w", pady=(8, 0))

        mid = tk.Frame(r, padx=16)
        mid.pack(fill="both", expand=True)
        cols = ("no", "title", "check", "why")
        self.tv = ttk.Treeview(mid, columns=cols, show="headings")
        for c, t, wd in (("no", "No.", 60), ("title", "항목", 470), ("check", "자동 점검", 230), ("why", "수동 사유", 300)):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=wd, anchor="w")
        self.tv.tag_configure("auto", background="#e7f5ec")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        bot = tk.Frame(r, padx=16, pady=12)
        bot.pack(fill="x")
        tk.Label(bot, text="평가 중에는 Dr.Dart 앱을 조작하지 마세요 · 앱 오른쪽 위 ■ 종료로 언제든 멈춤 · 저장·Start·Move To 는 누르지 않음",
                 font=(FONT, 9), fg="#777").pack(side="left")
        tk.Button(bot, text="닫기", font=(FONT, 11), command=r.destroy, padx=12).pack(side="right")
        self.go = tk.Button(bot, text="자동 평가 시작", font=(FONT, 11, "bold"), fg="white", bg="#1f6f4a",
                            state="disabled", command=self.start, padx=14)
        self.go.pack(side="right", padx=8)
        if path:
            self.load(path)

    def pick(self):
        p = filedialog.askopenfilename(title="TC·체크리스트 엑셀 선택", filetypes=[("Excel", "*.xlsx *.xlsm"), ("모든 파일", "*.*")])
        if p:
            self.load(p)

    def load(self, p):
        p = Path(p)
        if p.suffix.lower() not in (".xlsx", ".xlsm"):
            messagebox.showerror("지원하지 않는 형식", ".xlsx / .xlsm 만 읽을 수 있습니다. (.xls 는 엑셀에서 .xlsx 로 다시 저장)")
            return
        try:
            rows = read_rows(p)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("읽기 실패", f"{type(e).__name__}: {e}")
            return
        if not rows:
            messagebox.showwarning("TC 를 찾지 못함", "머리글(Expect Result·기대결과 또는 내용+결과 열)이 있는 시트를 찾지 못했습니다.")
            return
        self.path, self.rows = p, rows
        self.file.config(text=str(p))
        self.tv.delete(*self.tv.get_children())
        n = 0
        for x in rows:
            c = match_check(x.get("title"), x["text"])
            if c:
                n += 1
            self.tv.insert("", "end", values=(x["no"], x["title"][-90:], TITLES[c["key"]] if c else "—",
                                              "" if c else nt_reason(x["text"])), tags=("auto",) if c else ())
        sheets = sorted({x["sheet"] for x in rows})
        self.sumlab.config(text=f"시트 {', '.join(sheets)} · 행 {len(rows)}개 중 자동 판정 {n}개 · 수동(NT) {len(rows) - n}개")
        self.go.config(state="normal" if n else "disabled")

    def start(self):
        bat = ROOT / "tc_run.bat"
        subprocess.Popen(["cmd", "/c", "start", "PalletizOS TC 자동평가", "cmd", "/c", str(bat), str(self.path)], cwd=str(ROOT))
        self.root.destroy()


if __name__ == "__main__":
    App(sys.argv[1] if len(sys.argv) > 1 else None).root.mainloop()
