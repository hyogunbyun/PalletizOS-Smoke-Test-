"""설명 영상용 자료 캡처: 실제 상태 표시창(overlay.py)을 상태별로 띄워 PrintWindow로 찍고, 녹화·관리 창도 찍는다.

표시창 상태는 러너가 쓰는 것과 같은 상태 JSON을 직접 써서 만든다(실제 실행 로그의 문구를 그대로 사용).
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ctypes.windll.shcore.SetProcessDpiAwareness(2)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from autotest.winutil import capture  # noqa: E402

OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)
user32 = ctypes.windll.user32

TCS = ["H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08", "R01", "R02", "R03", "R04", "R05",
       "I01", "I02", "I03", "I04", "L01", "L02", "L03", "L04", "L05", "S01", "S02", "S03", "S04", "S05",
       "J01", "Q01", "V01", "C01"]
from autotest.flows import SHORT  # noqa: E402
LABELS = {t: f"{t} {SHORT.get(t, '111' if t == 'C01' else '')}" for t in TCS}


def chips(done, run=None, fail=(), na=()):
    out = []
    for i, t in enumerate(TCS):
        if t in fail:
            st = "fail"
        elif t in na:
            st = "na"
        elif i < done:
            st = "pass"
        elif t == run:
            st = "run"
        else:
            st = None
        out.append([t, st])
    return out


BASE = {"chip_labels": LABELS, "total": len(TCS), "hidden": False, "done": False}
STATES = {
    "s1_prepare": {"badge": "ING", "flow": "환경 준비", "desc": "시뮬레이터 → 앱 → 제어기 연결 → PalletizOS 진입 확인",
                   "step": "가상 제어기 연결", "action": "클릭: 연결", "last": "", "index": None, "chips": chips(0),
                   "foot": "백그라운드 실행 중 · 앱 창을 최소화하지 마세요"},
    "s2_wait": {"badge": "WAIT", "flow": "Admin 비밀번호 입력 대기",
                "desc": "검은 콘솔 창(PalletizOS_smoke)에 Admin 비밀번호를 입력하고 엔터 (글자는 안 보임, 엔터만 = 건너뜀). 한 번 성공하면 저장되어 다음부터는 묻지 않음",
                "step": "콘솔 창에서 입력을 기다리는 중", "action": "", "last": "", "index": None, "chips": chips(0),
                "foot": "백그라운드 실행 중 · 앱 창을 최소화하지 마세요"},
    "s3_running": {"badge": "ING", "flow": "R03 · 레시피 검색", "index": 11,
                   "desc": "부분 일치 검색 → 해당 행만, 없는 단어 → 0개·'No matching results.', 지우면 전체 복귀",
                   "step": "'1006' 검색 → 2개 기대", "action": "클릭: 검색 '1006'",
                   "last": "직전: R02 레시피 선택 → 정보 패널 → PASS",
                   "chips": chips(10, run="R03", na=("H06",)), "foot": "백그라운드 실행 중 · 앱 창을 최소화하지 마세요"},
    "s3b_fail": {"badge": "ING", "flow": "R05 · Create Recipe 편집기", "index": 13,
                 "desc": "Create Recipe → 편집기(이름 기본값·Box 단계) 열림 → X로 닫으면 레시피 수 그대로",
                 "step": "Create Recipe → 편집기 열림 확인", "action": "클릭: Create Recipe",
                 "last": "직전: R04 레시피 ⋮ 메뉴 → FAIL — ⋮ 메뉴 항목 누락: ['Delete']",
                 "chips": chips(12, run="R05", fail=("R04",), na=("H06",)), "foot": "백그라운드 실행 중 · 앱 창을 최소화하지 마세요"},
    "s4_record": {"badge": "ING", "flow": "L02 · 로그 검색", "index": 19,
                  "desc": "메시지 단어로 검색 → 모든 행에 그 단어 포함, 지우면 원래 행 수",
                  "step": "'Account' 검색 → 모든 행에 'Account' 포함 기대", "action": "클릭: 로그 검색 'Account'",
                  "last": "직전: L01 Palletizing Log = 앱 로그 → PASS",
                  "chips": chips(18, run="L02", fail=("R04",), na=("H06",)), "foot": "백그라운드 실행 중 · 앱 창을 최소화하지 마세요"},
    "s5_stop": {"badge": "STOP", "flow": "종료 요청됨", "desc": "진행 중이던 항목을 멈추고 화면 값을 원래대로 되돌리는 중",
                "step": "원상복구 중", "action": "", "last": "", "index": None,
                "chips": chips(18, fail=("R04",), na=("H06",)), "foot": "백그라운드 실행 중 · 앱 창을 최소화하지 마세요"},
    "s6_pass": {"badge": "PASS", "flow": "전체 판정: 통과", "desc": "리포트를 브라우저로 엽니다", "step": "PASS 30 · N/A 1",
                "action": "", "last": "직전: C01 111 → PASS", "index": None, "done": True,
                "chips": chips(31, na=("H06",)), "foot": "자동화 종료 · 이 표시는 20초 뒤 사라집니다"},
    "s7_fail": {"badge": "FAIL", "flow": "전체 판정: 보류", "desc": "리포트를 브라우저로 엽니다", "step": "PASS 29 · FAIL 1 · N/A 1",
                "action": "", "last": "직전: C01 111 → PASS", "index": None, "done": True,
                "chips": chips(31, fail=("R04",), na=("H06",)), "foot": "자동화 종료 · 이 표시는 20초 뒤 사라집니다"},
}


def find_overlay(timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        h = user32.FindWindowW(None, "PalletizOS Smoke Overlay")
        if h:
            return h
        time.sleep(0.2)
    raise SystemExit("표시창을 찾지 못함")


def capture_overlay():
    status = OUT / "live_status.json"
    pause = OUT / "pause.flag"  # overlay는 상태 파일과 같은 폴더의 pause.flag를 녹화 중 표시로 읽는다
    pause.unlink(missing_ok=True)
    status.write_text(json.dumps({**BASE, **STATES["s1_prepare"]}, ensure_ascii=False), encoding="utf-8")
    exe = Path(sys.executable).with_name("pythonw.exe")
    p = subprocess.Popen([str(exe), str(ROOT / "autotest" / "overlay.py"), str(status), str(os.getpid()), "background"])
    try:
        h = find_overlay()
        time.sleep(1.5)
        for name, st in STATES.items():
            if name == "s4_record":
                pause.write_text("rec", encoding="utf-8")
            status.write_text(json.dumps({**BASE, **st, "linger": 600}, ensure_ascii=False), encoding="utf-8")
            time.sleep(1.2)
            capture(h)[0].save(OUT / f"ov_{name}.png")
            pause.unlink(missing_ok=True)
            print("captured", name)
    finally:
        p.kill()
        status.unlink(missing_ok=True)


def capture_tk(module, setup, name):
    """Tk 창(녹화·관리)을 같은 프로세스에서 띄워 PrintWindow로 찍는다."""
    import importlib
    m = importlib.import_module(module)
    obj = setup(m)
    root = obj.root
    root.update()
    time.sleep(0.8)
    root.update()
    h = user32.GetParent(root.winfo_id()) or root.winfo_id()
    capture(h)[0].save(OUT / f"{name}.png")
    print("captured", name)
    return obj


def main():
    capture_overlay()

    def mgr(m):
        o = m.Manager()
        o.root.geometry("980x620+80+80")
        names = [p.name for p in o.files]
        if names:
            o.lst.selection_set(0)
            o.select()
            o.steps.selection_set(2)
        return o
    o = capture_tk("autotest.scenario_manager", mgr, "win_manager")
    o.root.destroy()

    def rec(m):
        o = m.App()
        o.worker.alive = False  # 화면 캡처만 (앱 조작 안 함)
        o.root.geometry("+120+120")
        o.name.delete(0, "end")
        o.name.insert(0, "111")
        data = json.loads(next((ROOT / "scenarios").glob("C01_*.json")).read_text(encoding="utf-8"))
        o.status.config(text="● 녹화 중 (Operator) — 앱에서 직접 눌러 보세요. 끝나면 '완료'. 진행 중이던 자동화 실행은 일시정지됩니다.",
                        fg="#ff8a8a")
        for i, s in enumerate(data["steps"], 1):
            o.listbox.insert("end", f"{i}. {s['label']}")
        o.b_start.config(state="disabled")
        o.b_undo.config(state="normal")
        o.b_done.config(state="normal")
        return o
    import queue as _q

    def rec2(m):
        o = rec(m)
        o.events = _q.Queue()  # 녹화기 작업 스레드가 보낸 '앱이 꺼져 있음' 같은 실제 상태 문구가 예시 화면을 덮지 않게
        o.root.update()
        o.status.config(text="● 녹화 중 (Operator) — 앱에서 직접 눌러 보세요. 끝나면 '완료'. 진행 중이던 자동화 실행은 일시정지됩니다.",
                        fg="#ff8a8a")
        return o
    o = capture_tk("autotest.recorder", rec2, "win_recorder")
    o.hook.stop()
    o.root.destroy()
    (ROOT / "results" / "pause.flag").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
