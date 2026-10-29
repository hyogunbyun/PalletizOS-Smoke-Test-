"""녹화 시나리오 관리 창: 목록·이름 변경·사용 여부·단계 삭제/순서/입력값 수정·확인 문구 편집·삭제(휴지통).

실행: pythonw -m autotest.scenario_manager   (또는 바탕화면 PalletizOS_scenarios.bat, 녹화 창의 '시나리오 관리')
삭제는 scenarios/_삭제됨/ 으로 옮기기만 한다 (되살리려면 파일을 scenarios/로 다시 옮김).
"""
import ctypes
import json
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

ctypes.windll.shcore.SetProcessDpiAwareness(2)
ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "scenarios"
TRASH = SCEN_DIR / "_삭제됨"
FONT = "Malgun Gothic"
BG, PANEL, INK, SUB = "#121721", "#1d2330", "#f3f4f6", "#9aa3b2"


def step_text(i, s):
    t = f"{i}. {s.get('label', s.get('name', '?'))}"
    if s.get("action") == "set_text":
        t += f"  ← 입력 '{s.get('value', '')}'"
    if s.get("note"):
        t += f"  ({s['note']})"
    return t


class Manager:
    def __init__(self):
        SCEN_DIR.mkdir(exist_ok=True)
        self.root = tk.Tk()
        self.root.title("PalletizOS 시나리오 관리")
        self.root.configure(bg=BG, padx=12, pady=12)
        self.root.geometry("980x620")
        self.files, self.cur, self.data, self.dirty = [], None, None, False

        btn = dict(font=(FONT, 10, "bold"), relief="flat", fg="white", padx=10, pady=4, cursor="hand2")
        lab = dict(bg=BG, fg=INK, font=(FONT, 10), anchor="w")

        # 왼쪽: 시나리오 목록
        left = tk.Frame(self.root, bg=BG)
        left.pack(side="left", fill="y")
        tk.Label(left, text="시나리오", **lab).pack(fill="x")
        self.lst = tk.Listbox(left, width=34, font=(FONT, 10), bg=PANEL, fg=INK, highlightthickness=0,
                              selectbackground="#2f6fd6", exportselection=False)
        self.lst.pack(fill="y", expand=True, pady=4)
        self.lst.bind("<<ListboxSelect>>", lambda e: self.select())
        row = tk.Frame(left, bg=BG)
        row.pack(fill="x")
        tk.Button(row, text="● 새로 녹화", bg="#d64545", command=self.record, **btn).pack(side="left")
        tk.Button(row, text="새로고침", bg="#3a4252", command=self.reload, **btn).pack(side="left", padx=6)

        # 오른쪽: 상세
        right = tk.Frame(self.root, bg=BG, padx=14)
        right.pack(side="left", fill="both", expand=True)
        top = tk.Frame(right, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text="이름", **lab).pack(side="left")
        self.title = tk.Entry(top, font=(FONT, 11), width=36)
        self.title.pack(side="left", padx=6)
        self.title.bind("<KeyRelease>", lambda e: self.touch())
        self.enabled = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="실행에 포함", variable=self.enabled, command=self.touch, bg=BG, fg=INK,
                       selectcolor=PANEL, activebackground=BG, activeforeground=INK, font=(FONT, 10)).pack(side="left", padx=8)
        self.info = tk.Label(right, text="", bg=BG, fg=SUB, font=(FONT, 9), anchor="w", justify="left")
        self.info.pack(fill="x", pady=(4, 6))

        tk.Label(right, text="단계 (위에서 아래 순서로 실행)", **lab).pack(fill="x")
        mid = tk.Frame(right, bg=BG)
        mid.pack(fill="both", expand=True, pady=4)
        self.steps = tk.Listbox(mid, font=(FONT, 10), bg=PANEL, fg=INK, highlightthickness=0,
                                selectbackground="#2f6fd6", exportselection=False)
        self.steps.pack(side="left", fill="both", expand=True)
        sb = tk.Frame(mid, bg=BG, padx=6)
        sb.pack(side="left", fill="y")
        for text, cmd in (("▲ 위로", lambda: self.move(-1)), ("▼ 아래로", lambda: self.move(1)),
                          ("입력값 수정", self.edit_value), ("단계 삭제", self.del_step)):
            tk.Button(sb, text=text, bg="#3a4252", command=cmd, width=10, **btn).pack(fill="x", pady=2)

        tk.Label(right, text="끝났을 때 보여야 할 문구 (모두 보여야 PASS · '새 에러 문구 없음'은 항상 확인)", **lab).pack(fill="x", pady=(8, 0))
        bot = tk.Frame(right, bg=BG)
        bot.pack(fill="x", pady=4)
        self.exp = tk.Listbox(bot, height=5, font=(FONT, 10), bg=PANEL, fg=INK, highlightthickness=0,
                              selectbackground="#1f9d55", exportselection=False)
        self.exp.pack(side="left", fill="x", expand=True)
        eb = tk.Frame(bot, bg=BG, padx=6)
        eb.pack(side="left", fill="y")
        tk.Button(eb, text="문구 추가", bg="#3a4252", command=self.add_exp, width=10, **btn).pack(fill="x", pady=2)
        tk.Button(eb, text="문구 삭제", bg="#3a4252", command=self.del_exp, width=10, **btn).pack(fill="x", pady=2)

        act = tk.Frame(right, bg=BG)
        act.pack(fill="x", pady=(10, 0))
        tk.Button(act, text="시나리오 삭제", bg="#7f1d1d", command=self.delete, **btn).pack(side="left")
        tk.Button(act, text="▶ 이 시나리오만 실행", bg="#2f6fd6", command=self.run_one, **btn).pack(side="left", padx=6)
        self.b_save = tk.Button(act, text="저장", bg="#1f9d55", command=self.save, state="disabled", **btn)
        self.b_save.pack(side="right")
        tk.Button(act, text="되돌리기", bg="#3a4252", command=self.select, **btn).pack(side="right", padx=6)

        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.reload()

    # ---------- 목록
    def reload(self):
        if self.dirty and not messagebox.askyesno("저장 안 함", "저장하지 않은 변경이 있습니다. 버리고 새로고칠까요?"):
            return
        self.files = sorted(SCEN_DIR.glob("C*.json"))
        self.lst.delete(0, "end")
        for p in self.files:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                d = {"id": p.stem, "title": "(읽을 수 없음)"}
            off = "" if d.get("enabled", True) else "  [사용 안 함]"
            adm = " · Admin" if d.get("admin") else ""
            self.lst.insert("end", f"{d.get('id', '?')}  {d.get('title', '')}{adm}{off}")
        self.cur, self.data, self.dirty = None, None, False
        self.clear()
        if not self.files:
            self.info.config(text="녹화한 시나리오가 없습니다. '● 새로 녹화'로 만드세요.")

    def clear(self):
        self.title.delete(0, "end")
        self.steps.delete(0, "end")
        self.exp.delete(0, "end")
        self.b_save.config(state="disabled")

    def select(self):
        sel = self.lst.curselection()
        if not sel:
            return
        if self.dirty and self.cur is not None and sel[0] != self.cur \
                and not messagebox.askyesno("저장 안 함", "저장하지 않은 변경이 있습니다. 버리고 이동할까요?"):
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(self.cur)
            return
        self.cur = sel[0]
        self.data = json.loads(self.files[self.cur].read_text(encoding="utf-8"))
        self.clear()
        self.title.insert(0, self.data.get("title", ""))
        self.enabled.set(self.data.get("enabled", True))
        self.info.config(text=f"{self.data.get('id')} · 녹화 {self.data.get('recorded_at', '-')} · 계정 "
                              f"{self.data.get('recorded_role') or '-'}{' (Admin 필요)' if self.data.get('admin') else ''}"
                              f" · 파일 {self.files[self.cur].name}")
        self.draw()
        self.dirty = False
        self.b_save.config(state="disabled")

    def draw(self, keep=None):
        self.steps.delete(0, "end")
        for i, s in enumerate(self.data["steps"], 1):
            self.steps.insert("end", step_text(i, s))
        self.exp.delete(0, "end")
        for t in self.data.get("expects", []):
            self.exp.insert("end", t)
        if keep is not None and self.data["steps"]:
            k = max(0, min(keep, len(self.data["steps"]) - 1))
            self.steps.selection_set(k)
            self.steps.see(k)

    def touch(self):
        if self.data is not None:
            self.dirty = True
            self.b_save.config(state="normal")

    # ---------- 단계
    def _sel_step(self):
        s = self.steps.curselection()
        if not s:
            messagebox.showinfo("단계", "단계를 먼저 고르세요.")
            return None
        return s[0]

    def move(self, d):
        i = self._sel_step()
        if i is None or not (0 <= i + d < len(self.data["steps"])):
            return
        st = self.data["steps"]
        st[i], st[i + d] = st[i + d], st[i]
        self.draw(keep=i + d)
        self.touch()

    def del_step(self):
        i = self._sel_step()
        if i is None:
            return
        if len(self.data["steps"]) == 1:
            messagebox.showinfo("단계", "마지막 남은 단계입니다. 시나리오 전체를 지우려면 '시나리오 삭제'를 쓰세요.")
            return
        del self.data["steps"][i]
        self.draw(keep=i)
        self.touch()

    def edit_value(self):
        i = self._sel_step()
        if i is None:
            return
        s = self.data["steps"][i]
        if s.get("action") != "set_text":
            messagebox.showinfo("입력값", "입력칸에 값을 넣는 단계만 수정할 수 있습니다.")
            return
        v = simpledialog.askstring("입력값 수정", f"{s.get('label')}에 넣을 값", initialvalue=s.get("value", ""), parent=self.root)
        if v is None:
            return
        s["value"] = v
        self.draw(keep=i)
        self.touch()

    # ---------- 확인 문구
    def add_exp(self):
        if self.data is None:
            return
        v = simpledialog.askstring("문구 추가", "끝났을 때 화면에 보여야 할 문구 (정확히 같은 글자)", parent=self.root)
        if v and v.strip():
            self.data.setdefault("expects", []).append(v.strip())
            self.draw()
            self.touch()

    def del_exp(self):
        s = self.exp.curselection()
        if not s or self.data is None:
            return
        del self.data["expects"][s[0]]
        self.draw()
        self.touch()

    # ---------- 저장 / 삭제
    def save(self):
        if self.data is None:
            return
        self.data["title"] = self.title.get().strip() or self.data.get("title", "시나리오")
        self.data["enabled"] = bool(self.enabled.get())
        n_exp = len(self.data.get("expects", []))
        self.data["desc"] = f"녹화 시나리오 · {len(self.data['steps'])}단계" + (f" · 확인 문구 {n_exp}개" if n_exp else "")
        p = self.files[self.cur]
        p.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        self.dirty = False
        keep = self.cur
        self.reload()
        self.lst.selection_set(keep)
        self.select()
        self.info.config(text=self.info.cget("text") + "  ✔ 저장됨 (다음 실행부터 반영)")

    def delete(self):
        if self.data is None:
            return
        p = self.files[self.cur]
        if not messagebox.askyesno("시나리오 삭제", f"{self.data.get('id')} '{self.data.get('title')}'을(를) 삭제할까요?\n"
                                                  f"(scenarios\\_삭제됨 폴더로 옮겨지며, 다시 옮기면 되살릴 수 있습니다)"):
            return
        TRASH.mkdir(exist_ok=True)
        shutil.move(str(p), str(TRASH / p.name))
        self.dirty = False
        self.reload()

    def run_one(self):
        """선택한 시나리오만 스모크로 실행 → 끝나면 리포트가 열려 PASS/FAIL 확인 (새 콘솔 창)."""
        if self.data is None:
            messagebox.showinfo("실행", "시나리오를 먼저 고르세요.")
            return
        if self.dirty:
            messagebox.showinfo("실행", "저장하지 않은 변경이 있습니다. 먼저 저장하세요.")
            return
        if not self.data.get("enabled", True):
            messagebox.showinfo("실행", "'실행에 포함'이 꺼져 있습니다. 켜고 저장한 뒤 실행하세요.")
            return
        sid = self.data["id"]
        subprocess.Popen(["cmd", "/c", "start", f"PalletizOS 스모크 {sid}", "cmd", "/c",
                          str(ROOT / "run_smoke.bat"), "--only", sid], cwd=str(ROOT))

    def record(self):
        subprocess.Popen([sys.executable, "-m", "autotest.recorder"], cwd=str(ROOT))

    def quit(self):
        if self.dirty and not messagebox.askyesno("저장 안 함", "저장하지 않은 변경이 있습니다. 버리고 닫을까요?"):
            return
        self.root.destroy()


if __name__ == "__main__":
    Manager().root.mainloop()
