"""시나리오 녹화기: 사용자가 앱에서 직접 누른 것을 단계로 기록해 scenarios/C##_이름.json으로 저장한다.

동작
- 화면 객체 스냅샷을 계속 갱신(0.3초 간격)하고, 마우스 왼쪽 버튼이 앱 창 안에서 눌리면(15ms마다 버튼 상태만 읽음, 훅 없음)
  '눌리기 직전 스냅샷'에서 그 좌표를 감싸는 가장 작은 조작 객체(버튼·탭·항목…)를 찾아 이름으로 기록한다.
  (Chromium의 ElementFromPoint는 바깥 Document만 돌려줘 쓸 수 없음 — 2026-10-19 실측)
- 이름 없는 버튼은 가장 가까운 이름 있는 요소 기준 상대 위치(anchor)로, 접힌 좌측 메뉴 아이콘은 메뉴 이름으로 기록
- 입력칸에 친 값은 다음 클릭/완료 때 값 변화로 감지해 set_text 단계로 기록 (비밀번호 입력창은 기록하지 않음)
- 녹화 중에는 results/pause.flag를 만들어 진행 중인 자동화 실행을 일시정지시킨다
실행: pythonw -m autotest.recorder   (또는 바탕화면 PalletizOS_record.bat / 실행 중 상태 표시창의 '＋ 추가')
"""
import ctypes
import ctypes.wintypes as wt
import json
import queue
import re
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ctypes.windll.shcore.SetProcessDpiAwareness(2)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCEN_DIR = ROOT / "scenarios"
PAUSE_FILE = ROOT / "results" / "pause.flag"
ACTIONABLE = ("Button", "CheckBox", "RadioButton", "TabItem", "ListItem", "MenuItem", "DataItem", "Edit",
              "Hyperlink", "ComboBox")
user32 = ctypes.windll.user32
FONT = "Malgun Gothic"


# ---------------------------------------------------------------- 클릭 감지 (훅 없이 상태 읽기만)
# 전역 마우스 훅(WH_MOUSE_LL)은 쓰지 않는다: 훅은 마우스가 움직일 때마다 이 프로세스의 응답을 기다리는데,
# UIA 스냅샷이 무거워 응답이 늦으면 PC 전체 마우스가 멈춘다 (2026-10-19 실제 발생).
# 대신 왼쪽 버튼 상태를 15ms마다 읽기만 한다 → 입력을 막을 수 없음. 보통 클릭은 80ms 이상 눌려 있어 놓치지 않음.
class ClickPoller(threading.Thread):
    def __init__(self, out):
        super().__init__(daemon=True)
        self.out, self.alive = out, True

    def run(self):
        was_down = False
        pt = wt.POINT()
        while self.alive:
            down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)  # VK_LBUTTON
            if down and not was_down:
                user32.GetCursorPos(ctypes.byref(pt))
                self.out.put((time.time(), pt.x, pt.y))
            was_down = down
            time.sleep(0.015)

    def stop(self):
        self.alive = False


# ---------------------------------------------------------------- UIA 작업 스레드 (스냅샷 + 클릭 해석)
class Worker(threading.Thread):
    def __init__(self, clicks, events):
        super().__init__(daemon=True)
        self.clicks, self.events = clicks, events
        self.recording = False
        self.snaps = []          # [(시각, [요소 dict])]
        self.steps = []
        self.first_texts, self.last_texts = set(), set()
        self.pending_edit = None  # (단계 위치, 요소 dict) — 값 변화를 나중에 확인
        self.cmd = queue.Queue()
        self.alive = True
        self.role = None

    def log(self, kind, data):
        self.events.put((kind, data))

    def _snapshot(self):
        out = []
        for e in self.ui.top_all():
            ei = e.element_info
            r = ei.rectangle
            if r.width() <= 0 or r.height() <= 0:
                continue
            ct = ei.control_type
            if ct not in ACTIONABLE and ct != "Text":
                continue
            d = {"type": ct, "name": (ei.name or "").strip(), "rect": (r.left, r.top, r.right, r.bottom),
                 "rid": tuple(ei.runtime_id or ())}
            if ct == "Edit":
                try:
                    d["value"] = e.iface_value.CurrentValue
                except Exception:
                    d["value"] = None
            out.append(d)
        return out

    def run(self):
        # COM 초기화는 comtypes를 import할 때 이 스레드에서 자동으로 된다. 직접 다시 부르면
        # '스레드 모드를 바꿀 수 없음' 오류로 스레드가 죽는다 (2026-10-19 실제 발생 → 녹화 시작이 먹히지 않았음)
        try:
            self._run()
        except BaseException as e:
            self.log("error", f"녹화기 내부 오류: {type(e).__name__}: {e}")

    def _wait_app(self):
        from autotest.winutil import app_hwnd
        warned = False
        while self.alive and not app_hwnd():
            if not warned:
                self.log("error", "Dr.Dart-Platform이 꺼져 있습니다. 앱을 켜고 PalletizOS를 연 뒤 '녹화 시작'을 누르세요.")
                warned = True
            time.sleep(1)
        if warned:
            self.log("status", "앱을 찾았습니다. '녹화 시작'을 누르세요.")

    def _run(self):
        from autotest.ui import UI
        self.ui = UI()
        self._wait_app()
        try:
            self.ui.warm_up()
            self.ui.remember_nav()
        except Exception as e:
            self.log("error", f"앱 화면을 읽지 못함: {e}")
        while self.alive:
            try:
                c = self.cmd.get_nowait()
                self._command(c)
            except queue.Empty:
                pass
            try:
                snap = self._snapshot()
                self.snaps = (self.snaps + [(time.time(), snap)])[-30:]
            except Exception:
                time.sleep(0.3)
                continue
            while not self.clicks.empty():
                t, x, y = self.clicks.get()
                if self.recording:
                    self._on_click(t, x, y)
            time.sleep(0.3)

    # ---- 명령
    def _command(self, c):
        try:
            self._command_inner(c)
        except Exception as e:
            self.log("error", f"'{c}' 처리 중 오류: {type(e).__name__}: {e}")

    def _command_inner(self, c):
        if c == "start":
            try:
                if not self.ui.on_home():
                    self.log("status", "Home 화면으로 이동 중…")
                    self.ui.back_to_home()
            except Exception as e:
                self.log("error", f"Home으로 이동하지 못함: {e}")
                return
            self.role = self.ui.current_role()
            snap = self._snapshot()
            self.snaps = [(time.time(), snap)]
            self.first_texts = {d["name"] for d in snap if d["name"]}
            self.steps, self.pending_edit = [], None
            self.recording = True
            self.log("recording", self.role)
        elif c == "undo":
            if self.steps:
                self.steps.pop()
                self.pending_edit = None
                self.log("steps", list(self.steps))
        elif c == "finish":
            self._flush_edit()
            self.recording = False
            snap = self._snapshot()
            self.last_texts = {d["name"] for d in snap if d["name"] and d["type"] in ("Text", "Button", "TabItem")}
            self.log("finished", sorted(self.last_texts - self.first_texts))
        elif c == "cancel":
            self.recording = False

    # ---- 클릭 해석
    def _app_root(self):
        return self.ui.hwnd()

    def _in_app(self, x, y):
        h = user32.WindowFromPoint(wt.POINT(x, y))
        top = user32.GetAncestor(h, 2) if h else None  # GA_ROOT
        return top == self._app_root()

    def _flush_edit(self):
        """직전에 누른 입력칸의 값이 바뀌었으면 set_text 단계로 바꾼다."""
        if not self.pending_edit:
            return
        idx, d = self.pending_edit
        self.pending_edit = None
        cur = next((x for x in self.snaps[-1][1] if x["rid"] == d["rid"]), None)
        if cur is None or cur.get("value") == d.get("value"):
            return
        if _looks_secret(self.snaps[-1][1], d):
            self.steps[idx] = {**self.steps[idx], "note": "비밀번호 입력은 기록하지 않음"}
            self.log("warn", "비밀번호 입력칸은 값을 기록하지 않았습니다")
        else:
            self.steps[idx] = {**self.steps[idx], "action": "set_text", "value": cur.get("value") or ""}
        self.log("steps", list(self.steps))

    def _on_click(self, t, x, y):
        if not self._in_app(x, y):
            return
        self._flush_edit()
        before = [s for s in self.snaps if s[0] <= t]
        snap = (before[-1] if before else self.snaps[0])[1]
        hit = [d for d in snap if d["rect"][0] <= x < d["rect"][2] and d["rect"][1] <= y < d["rect"][3]]
        acts = sorted([d for d in hit if d["type"] in ACTIONABLE], key=_area)
        target = None
        if acts:
            smallest = acts[0]
            named = next((d for d in acts if d["name"] and _area(d) <= 6 * _area(smallest)), None)
            target = named or smallest
        else:
            texts = sorted([d for d in hit if d["type"] == "Text" and d["name"]], key=_area)
            target = texts[0] if texts else None
        if target is None:
            self.log("warn", f"({x},{y})에서 누를 수 있는 요소를 찾지 못해 건너뜀")
            return
        step = self._locator(target, snap)
        step["action"] = "click"
        self.steps.append(step)
        if target["type"] == "Edit":
            self.pending_edit = (len(self.steps) - 1, target)
        self.log("steps", list(self.steps))

    def _locator(self, d, snap):
        """재생할 때 같은 요소를 다시 찾을 수 있는 설명."""
        wr = self.ui.wrapper().rectangle()
        cx, cy = _center(d)
        # 접힌 좌측 메뉴 아이콘 → 메뉴 이름
        if not d["name"] and d["type"] == "Button" and d["rect"][2] < wr.left + 110:
            rail = sorted([x for x in snap if x["type"] == "Button" and x["rect"][2] < wr.left + 110], key=lambda x: x["rect"][1])
            order = getattr(self.ui, "_nav_order", None) or []
            idx = next((i for i, x in enumerate(rail) if x["rid"] == d["rid"]), None)
            if idx is not None and idx < len(order):
                return {"type": "nav", "name": order[idx], "label": f"메뉴 {order[idx]}"}
        if d["name"]:
            same = sorted([x for x in snap if x["type"] == d["type"] and x["name"] == d["name"]],
                          key=lambda x: (x["rect"][1], x["rect"][0]))
            nth = next((i for i, x in enumerate(same) if x["rid"] == d["rid"]), 0)
            return {"type": d["type"], "name": d["name"], "nth": nth, "label": f"{d['type']} '{d['name']}'"}
        # 이름 없음 → 가장 가까운 이름 있는 요소 기준 상대 위치
        named = [x for x in snap if x["name"] and x["rid"] != d["rid"]]
        anc = min(named, key=lambda x: (_center(x)[0] - cx) ** 2 + (_center(x)[1] - cy) ** 2)
        ax, ay = _center(anc)
        same = sorted([x for x in snap if x["type"] == anc["type"] and x["name"] == anc["name"]],
                      key=lambda x: (x["rect"][1], x["rect"][0]))
        nth = next((i for i, x in enumerate(same) if x["rid"] == anc["rid"]), 0)
        return {"type": d["type"], "name": "", "anchor": {"type": anc["type"], "name": anc["name"], "nth": nth},
                "offset": [cx - ax, cy - ay], "label": f"{d['type']} ('{anc['name']}' 기준 {cx - ax:+d},{cy - ay:+d})"}


def _area(d):
    r = d["rect"]
    return (r[2] - r[0]) * (r[3] - r[1])


def _center(d):
    r = d["rect"]
    return (r[0] + r[2]) // 2, (r[1] + r[3]) // 2


def _looks_secret(snap, d):
    if "password" in (d["name"] or "").lower():
        return True
    return any("password" in (x["name"] or "").lower() for x in snap if x["type"] == "Text")


def next_id():
    SCEN_DIR.mkdir(exist_ok=True)
    nums = [int(m.group(1)) for p in SCEN_DIR.glob("C*.json") if (m := re.match(r"C(\d+)_", p.name))]
    return f"C{(max(nums) + 1) if nums else 1:02d}"


# ---------------------------------------------------------------- 녹화 창
class App:
    def __init__(self):
        self.clicks, self.events = queue.Queue(), queue.Queue()
        self.hook = ClickPoller(self.clicks)
        self.worker = Worker(self.clicks, self.events)
        self.root = tk.Tk()
        self.root.title("PalletizOS 시나리오 녹화")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#121721", padx=14, pady=12)
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        lab = dict(bg="#121721", fg="#f3f4f6", font=(FONT, 10), anchor="w")
        tk.Label(self.root, text="시나리오 이름", **lab).pack(fill="x")
        self.name = tk.Entry(self.root, font=(FONT, 11), width=40)
        self.name.pack(fill="x", pady=(2, 8))
        self.name.insert(0, "새 시나리오")
        self.status = tk.Label(self.root, text="이름을 적고 '녹화 시작'을 누르세요. Home 화면에서 시작합니다.",
                               wraplength=420, justify="left", **{**lab, "fg": "#7cc4ff"})
        self.status.pack(fill="x")
        self.listbox = tk.Listbox(self.root, height=10, font=(FONT, 10), bg="#1d2330", fg="#f3f4f6",
                                  highlightthickness=0, selectbackground="#2f6fd6")
        self.listbox.pack(fill="both", expand=True, pady=8)
        row = tk.Frame(self.root, bg="#121721")
        row.pack(fill="x")
        btn = dict(font=(FONT, 10, "bold"), relief="flat", fg="white", padx=10, pady=4, cursor="hand2")
        self.b_start = tk.Button(row, text="● 녹화 시작", bg="#d64545", command=self.start, **btn)
        self.b_start.pack(side="left")
        self.b_undo = tk.Button(row, text="마지막 단계 삭제", bg="#3a4252", command=lambda: self.worker.cmd.put("undo"),
                                state="disabled", **btn)
        self.b_undo.pack(side="left", padx=6)
        self.b_done = tk.Button(row, text="완료", bg="#1f9d55", command=self.finish, state="disabled", **btn)
        self.b_done.pack(side="right")
        tk.Button(row, text="취소", bg="#3a4252", command=self.cancel, **btn).pack(side="right", padx=6)
        tk.Button(self.root, text="시나리오 관리 (편집·삭제)", bg="#3a4252", **btn,
                  command=lambda: __import__("subprocess").Popen([sys.executable, "-m", "autotest.scenario_manager"],
                                                                 cwd=str(ROOT))).pack(fill="x", pady=(8, 0))
        self.steps = []
        self.hook.start()
        self.worker.start()
        self.root.after(200, self.poll)

    def start(self):
        PAUSE_FILE.parent.mkdir(exist_ok=True)
        PAUSE_FILE.write_text("recording", encoding="utf-8")  # 진행 중인 자동화 실행 일시정지
        self.b_start.config(state="disabled")
        self.status.config(text="준비 중…")
        self.worker.cmd.put("start")

    def finish(self):
        self.b_done.config(state="disabled")
        self.status.config(text="마무리 중…")
        self.worker.cmd.put("finish")

    def cancel(self):
        if self.worker.recording and self.steps and not messagebox.askyesno("녹화 취소", "기록한 단계를 버리고 닫을까요?"):
            return
        self.close()

    def close(self):
        self.worker.cmd.put("cancel")
        self.worker.alive = False
        self.hook.stop()
        PAUSE_FILE.unlink(missing_ok=True)
        self.root.destroy()

    def poll(self):
        while not self.events.empty():
            kind, data = self.events.get()
            if kind == "recording":
                self.status.config(text=f"● 녹화 중 ({data or '계정 미확인'}) — 앱에서 직접 눌러 보세요. 끝나면 '완료'. "
                                        "진행 중이던 자동화 실행은 일시정지됩니다.", fg="#ff8a8a")
                self.b_undo.config(state="normal")
                self.b_done.config(state="normal")
            elif kind == "steps":
                self.steps = data
                self.listbox.delete(0, "end")
                for i, s in enumerate(data, 1):
                    txt = s["label"] + (f" ← 입력 '{s['value']}'" if s.get("action") == "set_text" else "")
                    self.listbox.insert("end", f"{i}. {txt}")
                self.listbox.see("end")
            elif kind in ("warn", "status"):
                self.status.config(text=data)
            elif kind == "error":
                self.status.config(text=data, fg="#ff8a8a")
                self.b_start.config(state="normal")
            elif kind == "finished":
                self.choose_expects(data)
        self.root.after(200, self.poll)

    def choose_expects(self, new_texts):
        if not self.steps:
            messagebox.showinfo("녹화", "기록된 단계가 없습니다.")
            self.close()
            return
        top = tk.Toplevel(self.root, bg="#121721", padx=14, pady=12)
        top.title("끝났을 때 보여야 할 문구")
        top.attributes("-topmost", True)
        tk.Label(top, text="재생이 끝났을 때 화면에 보여야 할 문구를 고르세요 (녹화 중 새로 나타난 문구).\n"
                           "'새 에러 문구 없음'은 항상 확인합니다.", bg="#121721", fg="#f3f4f6", font=(FONT, 10),
                 justify="left").pack(anchor="w")
        lb = tk.Listbox(top, selectmode="multiple", height=14, width=60, font=(FONT, 10), bg="#1d2330", fg="#f3f4f6",
                        selectbackground="#1f9d55", exportselection=False)
        texts = [t for t in new_texts if len(t) <= 80 and not re.fullmatch(r"[\d\s.:,%/·-]*", t)]
        for t in texts:
            lb.insert("end", t)
        lb.pack(fill="both", expand=True, pady=8)

        def save():
            expects = [texts[i] for i in lb.curselection()]
            sid = next_id()
            name = self.name.get().strip() or "새 시나리오"
            data = {"id": sid, "title": name, "desc": f"녹화 시나리오 · {len(self.steps)}단계"
                    + (f" · 확인 문구 {len(expects)}개" if expects else ""),
                    "admin": self.worker.role == "Admin", "recorded_role": self.worker.role,
                    "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": self.steps, "expects": expects}
            safe = re.sub(r"[^\w가-힣-]+", "_", name)[:30]
            path = SCEN_DIR / f"{sid}_{safe}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            messagebox.showinfo("저장됨", f"{sid} '{name}' 저장\n{path}\n\n다음 실행부터 포함됩니다.")
            top.destroy()
            self.close()

        tk.Button(top, text="저장", bg="#1f9d55", fg="white", font=(FONT, 10, "bold"), relief="flat", padx=14,
                  command=save).pack(side="right")

    def mainloop(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().mainloop()
