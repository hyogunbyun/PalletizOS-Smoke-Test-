"""실패 원인 진단 (2026-11-04 사용자 요청: 리포트의 '실패'가 왜 났는지 로그 근거로, 앱이 메모리 등으로 죽은 건지
외부 요인인지 구분해서 적어 달라).

시도 시작 때 가벼운 스냅숏(앱 프로세스·메모리·PC 상태)을 찍고, 실패하면 같은 항목을 다시 재서 비교한다.
여기에 앱 로그(그 시도 구간), Windows 이벤트 로그(앱 오류·응답 없음·메모리 부족), 앱 크래시 덤프, 가상 제어기(DRCF)
상태를 더해 '원인 추정 분류 + 근거 목록'을 만든다. 추정이지 확정이 아니므로 근거를 같이 남긴다.
"""
import ctypes
import ctypes.wintypes as wt
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import win32api
import win32process

APP_IMAGE = "dr.dart-platform.exe"
APP_LOG_DIR = Path(r"C:\Dr.Dart-Platform\logs")
DUMP_DIRS = [APP_LOG_DIR / "crashDumps"]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

# 분류: (키, 화면 이름, 성격). 성격 = 앱(제품 쪽) / 외부 / 자동화
CATS = {
    "app_crash": ("앱 비정상 종료(크래시)", "앱"),
    "app_memory": ("메모리 부족 의심", "앱"),
    "app_hang": ("앱 응답 없음·응답 지연", "앱"),
    "product": ("기대 결과 불일치 (제품 동작)", "앱"),
    "ui_changed": ("화면 요소를 못 찾음 (화면 변경·로딩 지연)", "앱"),
    "controller": ("가상 제어기(DRCF)·Docker 문제", "외부"),
    "pc_lock": ("PC 잠김·화면 보호기", "외부"),
    "user": ("사용자 조작·다른 창 개입", "외부"),
    "app_closed": ("앱이 외부에서 닫힘", "외부"),
    "tool": ("자동화 도구 오류", "자동화"),
    "uia": ("UI 자동화(UIA) 통신 실패 — 일시적일 수 있음", "자동화"),
}

LOG_PATTERNS = [  # (분류, 정규식, 설명) — error·warn 줄에서만 찾음 (debug 줄의 changeOperationSpeed 가 'hang' 으로 잡힘, 11-04)
    ("app_crash", r"render(er)? process (gone|crashed)|child process gone|GPU process (crashed|exited)|uncaught exception|"
                  r"unhandled (promise )?rejection|\bFATAL\b", "앱 내부 프로세스 종료·처리 안 된 예외"),
    ("app_memory", r"out of memory|\bOOM\b|ENOMEM|allocation failed|heap (out|limit)|JavaScript heap", "메모리 부족 메시지"),
    ("app_hang", r"not responding|\bunresponsive\b|\bhung\b", "응답 없음 메시지"),
    ("controller", r"ECONNREFUSED|ECONNRESET|socket hang up|(robot|controller|DRCF)\w*.{0,40}(disconnect|lost|refused|closed)",
     "제어기 연결 끊김·거부"),
]


# ---------------------------------------------------------------- 측정
class _MEMEX(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def system_memory():
    m = _MEMEX(ctypes.sizeof(_MEMEX))
    kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {"load_pct": m.dwMemoryLoad, "avail_mb": m.ullAvailPhys // 2**20, "total_mb": m.ullTotalPhys // 2**20,
            "commit_avail_mb": m.ullAvailPageFile // 2**20}


def _image(h):
    buf = ctypes.create_unicode_buffer(1024)
    n = wt.DWORD(1024)
    if kernel32.QueryFullProcessImageNameW(int(h), 0, buf, ctypes.byref(n)):
        return buf.value
    return ""


def app_processes():
    """Dr.Dart-Platform.exe 프로세스들: [{pid, ws_mb, private_mb, started}] (Electron 은 본체+렌더러+GPU 등 여러 개)."""
    out = []
    for pid in win32process.EnumProcesses():
        try:
            h = win32api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        except Exception:  # noqa: BLE001
            continue
        try:
            if not _image(h).lower().endswith(APP_IMAGE):
                continue
            mi = win32process.GetProcessMemoryInfo(h)
            ct = win32process.GetProcessTimes(h)["CreationTime"]
            out.append({"pid": pid, "ws_mb": mi["WorkingSetSize"] // 2**20, "private_mb": mi["PagefileUsage"] // 2**20,
                        "started": ct.strftime("%H:%M:%S") if hasattr(ct, "strftime") else str(ct)})
        except Exception:  # noqa: BLE001
            pass
        finally:
            win32api.CloseHandle(h)
    return sorted(out, key=lambda p: p["started"])


class _LII(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def session_state():
    """맨 앞 창, PC 잠김 여부, 마지막 사용자 입력 뒤 경과(초)."""
    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(fg, buf, 256)
    title = buf.value
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    img = ""
    try:
        h = win32api.OpenProcess(0x1000, False, pid.value)
        img = Path(_image(h)).name
        win32api.CloseHandle(h)
    except Exception:  # noqa: BLE001
        pass
    lii = _LII(ctypes.sizeof(_LII), 0)
    user32.GetLastInputInfo(ctypes.byref(lii))
    idle = ((kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000
    locked = img.lower() == "lockapp.exe" or "잠금 화면" in title or title == "Windows Default Lock Screen"
    return {"foreground": title[:80], "foreground_exe": img, "locked": locked, "idle_sec": round(idle, 1)}


def controller_state():
    """가상 제어기: Docker 응답, DRCF pid, 포트 12345 대기, 누적 충돌(rc=139) 횟수. 실패 시에만 부름 (docker 호출 1~2초)."""
    from . import env
    try:
        out = env._docker("exec", env.SIM, "sh", "-c",
                          "pgrep -x DRCF | head -1; grep -qE ':3039 [0-9A-F:]+ 0A' /proc/net/tcp /proc/net/tcp6 && echo LISTEN; "
                          "echo CRASH=$(grep -c 'rc=139' /home/dra/etc/data/drcf-restart.log 2>/dev/null || echo 0)", timeout=20)
    except Exception as e:  # noqa: BLE001
        return {"docker": False, "error": str(e)[:120]}
    lines = [l.strip() for l in (out or "").splitlines()]
    if not lines:
        return {"docker": False, "error": "docker exec 응답 없음 (Docker 엔진 또는 시뮬레이터 컨테이너가 꺼져 있음)"}
    crash = next((l[6:] for l in lines if l.startswith("CRASH=")), "0")
    return {"docker": True, "drcf_pid": lines[0] if lines[0].isdigit() else "", "listening": "LISTEN" in lines,
            "crash_count": int(crash) if crash.isdigit() else 0}


_last_ctrl = {}  # 마지막으로 잰 제어기 상태 (실행 시작·직전 실패 때) — 충돌 횟수 증가 비교용


def remember_controller():
    _last_ctrl.clear()
    _last_ctrl.update(controller_state())


def snapshot():
    """시도 시작 때: 빠른 항목만 (약 0.05초)."""
    return {"at": time.time(), "procs": app_processes(), "mem": system_memory(), "session": session_state(),
            "ctrl": dict(_last_ctrl)}


def windows_events(since):
    """since 이후 Windows 이벤트: 앱 오류(1000)·WER(1001)·응답 없음(1002)·가상 메모리 부족(2004)."""
    st = datetime.fromtimestamp(since - 5).strftime("%Y-%m-%dT%H:%M:%S")
    ps = (f"$s=[datetime]'{st}';"
          "$a=@(Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000,1001,1002;StartTime=$s} -EA SilentlyContinue);"
          "$b=@(Get-WinEvent -FilterHashtable @{LogName='System';Id=2004;StartTime=$s} -EA SilentlyContinue);"
          "($a+$b) | Where-Object { $_.Id -eq 2004 -or $_.Message -match 'Dr\\.Dart|electron|DRCF|wsl|vmmem|docker' } |"
          " ForEach-Object { '{0:HH:mm:ss}|{1}|{2}' -f $_.TimeCreated,$_.Id,(($_.Message -split \"`n\")[0..2] -join ' ').Trim() }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=25,
                           creationflags=_NO_WINDOW)
        txt = r.stdout.decode("utf-8", "replace") if r.stdout else ""
        if "\ufffd" in txt:
            txt = r.stdout.decode("cp949", "replace")
    except Exception:  # noqa: BLE001
        return []
    out = []
    for line in txt.splitlines():
        p = line.split("|", 2)
        if len(p) == 3:
            out.append({"time": p[0], "id": int(p[1]) if p[1].isdigit() else p[1], "msg": re.sub(r"\s+", " ", p[2])[:260]})
    return out[:10]


def new_dumps(since):
    out = []
    for d in DUMP_DIRS:
        if d.exists():
            out += [f"{p.name} ({datetime.fromtimestamp(p.stat().st_mtime):%H:%M:%S}, {p.stat().st_size // 1024}KB)"
                    for p in d.rglob("*") if p.is_file() and p.stat().st_mtime >= since - 5]
    return out[:10]


def analyze_log(lines, base_sigs=None):
    """시도 구간 앱 로그 → 에러·경고 수, 서명별 묶음, 분류 단서, 마지막 줄들."""
    from .logcheck import load_baseline, signature
    base = load_baseline() if base_sigs is None else base_sigs
    errs, warns, groups = [], 0, {}
    hits = {}
    for l in lines:
        low = l.lower()
        if "][error" in low:
            errs.append(l)
            sig = signature(l)
            g = groups.setdefault(sig, {"count": 0, "first": l.strip()[:260], "known": sig in base})
            g["count"] += 1
        elif "][warn" in low:
            warns += 1
        if "][error" not in low and "][warn" not in low:
            continue
        for cat, rx, what in LOG_PATTERNS:
            if re.search(rx, l, re.I) and not (cat == "controller" and "ModbusTcpMaster" in l):
                hits.setdefault(cat, {"what": what, "count": 0, "sample": l.strip()[:260]})["count"] += 1
    ordered = sorted(groups.values(), key=lambda g: (g["known"], -g["count"]))
    tail = [l.strip()[:240] for l in lines[-30:]]
    return {"lines": len(lines), "errors": len(errs), "warns": warns, "groups": ordered[:15],
            "new_groups": sum(1 for g in groups.values() if not g["known"]), "hits": hits, "tail": tail}


# ---------------------------------------------------------------- 판정
def _main_pid(procs):
    return procs[0]["pid"] if procs else None


def _ws(procs):
    return sum(p["ws_mb"] for p in procs)


def analyze(pre, msg, trace="", log_lines=None, status="fail", app_closed_hint=False):
    """실패 직후 호출. 반환: {category, label, nature, cause, evidence[], before, after, log, events, dumps}."""
    t0 = pre.get("at", time.time() - 60)
    after = {"procs": app_processes(), "mem": system_memory(), "session": session_state(), "ctrl": controller_state()}
    events = windows_events(t0)
    dumps = new_dumps(t0)
    log = analyze_log(log_lines or [])
    ev = []  # (분류, 근거 문장)
    b_procs, a_procs = pre.get("procs", []), after["procs"]
    exc_type = ""
    if trace:
        last = [l for l in trace.strip().splitlines() if l.strip()]
        exc_type = last[-1].split(":")[0].strip() if last else ""

    # 1. 앱 프로세스
    if b_procs and not a_procs:
        crashed = bool(dumps) or any(e["id"] in (1000, 1001) and "dart" in e["msg"].lower() for e in events)
        ev.append(("app_crash" if crashed else "app_closed",
                   f"시도 시작 때 앱 프로세스 {len(b_procs)}개 → 실패 시점 0개 (앱이 꺼짐)"
                   + (" · 크래시 흔적 있음" if crashed else " · 크래시 기록 없음 → 누군가 창을 닫았거나 외부에서 종료")))
    elif b_procs and a_procs and _main_pid(b_procs) != _main_pid(a_procs):
        ev.append(("app_crash", f"앱 본체 프로세스가 바뀜 (pid {_main_pid(b_procs)} → {_main_pid(a_procs)}, 재시작됨)"))
    elif b_procs and a_procs:
        gone = {p["pid"] for p in b_procs} - {p["pid"] for p in a_procs}
        if gone:
            ev.append(("app_crash", f"앱 하위 프로세스 {len(gone)}개가 사라짐 (pid {sorted(gone)}) — Electron 렌더러·GPU 프로세스 재시작 의심"))
    if app_closed_hint and not any(c in ("app_crash", "app_closed") for c, _ in ev):
        ev.append(("app_closed", "실행기가 앱 창을 찾지 못함 (앱 창이 닫혔거나 다시 그려지는 중)"))
    for d in dumps:
        ev.append(("app_crash", f"새 크래시 덤프: {d}"))
    for e in events:
        cat = {1000: "app_crash", 1001: "app_crash", 1002: "app_hang", 2004: "app_memory"}.get(e["id"], "app_crash")
        ev.append((cat, f"Windows 이벤트 {e['id']} ({e['time']}): {e['msg'][:180]}"))

    # 2. 메모리
    m0, m1 = pre.get("mem", {}), after["mem"]
    if m1.get("load_pct", 0) >= 90 or m1.get("avail_mb", 99999) < 800 or m1.get("commit_avail_mb", 99999) < 500:
        ev.append(("app_memory", f"PC 메모리 부족: 사용률 {m1['load_pct']}% · 남은 물리 메모리 {m1['avail_mb']}MB · "
                                 f"남은 커밋 {m1['commit_avail_mb']}MB"))
    ws0, ws1 = _ws(b_procs), _ws(a_procs)
    if a_procs and ws1 >= 2500:
        ev.append(("app_memory", f"앱 메모리 사용량 큼: 합계 {ws1}MB (시작 때 {ws0}MB)"))
    elif a_procs and ws0 and ws1 - ws0 >= 600:
        ev.append(("app_memory", f"이 시도 동안 앱 메모리가 {ws1 - ws0}MB 늘어남 ({ws0} → {ws1}MB)"))

    # 3. 가상 제어기
    c0, c1 = pre.get("ctrl", {}), after["ctrl"]
    if not c1.get("docker"):
        ev.append(("controller", f"Docker/시뮬레이터 응답 없음 ({c1.get('error', '')})"))
    else:
        if c0.get("crash_count") is not None and c1.get("crash_count", 0) > c0.get("crash_count", 0):
            ev.append(("controller", f"가상 제어기 DRCF 충돌(rc=139) {c1['crash_count'] - c0['crash_count']}회 증가 "
                                     f"({c0['crash_count']} → {c1['crash_count']})"))
        if c0.get("drcf_pid") and c1.get("drcf_pid") and c0["drcf_pid"] != c1["drcf_pid"]:
            ev.append(("controller", f"DRCF 프로세스가 재시작됨 (pid {c0['drcf_pid']} → {c1['drcf_pid']})"))
        if not c1.get("drcf_pid") or not c1.get("listening"):
            ev.append(("controller", "DRCF 가 떠 있지 않거나 포트 12345 를 열지 않음 (제어기 연결 불가 상태)"))

    # 4. PC·사용자
    s1 = after["session"]
    if s1.get("locked"):
        ev.append(("pc_lock", f"PC 가 잠겨 있음 (맨 앞: {s1['foreground'] or s1['foreground_exe']})"))
    if "UserInterference" in exc_type or "사용자 개입" in msg:
        ev.append(("user", "실행 중 마우스·키보드 조작 감지"))
    elif s1.get("idle_sec", 99) < 3 and s1.get("foreground_exe", "").lower() == APP_IMAGE:
        # 백그라운드 방식은 사용자가 다른 창에서 일해도 영향 없음 → 앱 창이 맨 앞일 때의 입력만 개입으로 봄
        ev.append(("user", f"실패 직전 앱 창이 맨 앞인 상태에서 사용자 입력 있음 ({s1['idle_sec']}초 전)"))

    # 5. 앱 로그
    for cat, h in log["hits"].items():
        ev.append((cat, f"앱 로그: {h['what']} {h['count']}줄 — {h['sample'][:180]}"))
    if log["new_groups"]:
        ev.append(("product", f"이 시도 동안 앱이 기준 목록에 없는 새 에러 로그 {log['new_groups']}종을 남김"))

    # 6. 예외 종류·메시지
    low = (msg or "").lower()
    if "-2147220991" in msg or "가입자를 불러낼 수 없" in msg or exc_type in ("COMError", "_ctypes.COMError"):
        ev.append(("uia", f"UIA 호출이 앱에 전달되지 않음 ({msg[:80]}) — 앱이 바쁘거나 창이 다시 그려지는 순간"))
    elif "elementnotfound" in low or exc_type.endswith("ElementNotFoundError") or "'top_level_only'" in msg:
        ev.append(("app_closed" if not a_procs else "ui_changed", "앱 창(Dr.Dart-Platform)을 찾지 못함"))
    elif re.search(r"찾지 못함|없음|나타나지 않|열리지 않|누락", msg or ""):
        ev.append(("ui_changed", f"기대한 화면 요소가 나타나지 않음: {msg[:120]}"))
    elif exc_type in ("AssertionError", "") and status == "fail":
        ev.append(("product", f"화면 값이 기대와 다름: {msg[:140]}"))
    elif exc_type and exc_type not in ("AssertionError", "EnvError", "autotest.ui.EnvError"):
        ev.append(("tool", f"자동화 코드 예외 {exc_type}: {msg[:120]}"))

    order = ["app_crash", "app_memory", "app_closed", "controller", "pc_lock", "user", "app_hang", "uia",
             "ui_changed", "tool", "product"]
    cats = [c for c, _ in ev]
    primary = next((c for c in order if c in cats), "product" if status == "fail" else "tool")
    label, nature = CATS[primary]
    cause = {
        "app_crash": "앱(또는 앱의 화면 프로세스)이 비정상 종료돼 동작이 끊김 — 제품 결함 가능성 높음. 크래시 덤프·이벤트 로그 확인",
        "app_memory": "메모리가 부족한 상태에서 실패 — 앱 메모리 누수 또는 PC 자원 부족. 같은 항목을 앱 재시작 직후 다시 실행해 비교",
        "app_closed": "앱이 크래시 기록 없이 꺼짐 — 사용자가 창을 닫았거나 다른 프로그램이 종료시킨 외부 요인 가능성",
        "controller": "가상 제어기(시뮬레이터) 쪽 문제로 앱이 제어기 응답을 못 받음 — 외부 환경 요인. 제품 결함으로 보기 전에 재실행",
        "pc_lock": "PC 가 잠겨 화면 입력이 막힘 — 외부 요인. 잠금 해제 상태에서 재실행",
        "user": "실행 중 사용자 조작·다른 창이 끼어듦 — 외부 요인. 손대지 않은 상태로 재실행",
        "app_hang": "앱이 응답하지 않는 상태 — 앱 처리 지연·멈춤. 같은 조작에서 반복되면 제품 결함",
        "uia": "UI 자동화 통신이 순간적으로 실패 — 자동화 쪽 일시 오류 가능성. 재실행해서 재현되는지 확인",
        "ui_changed": "기대한 버튼·문구가 화면에 없음 — 새 버전에서 화면이 바뀌었거나 로딩이 늦음. 스크린샷으로 확인 후 제품 변경이면 점검 기준 갱신",
        "tool": "자동화 코드 자체의 오류 — 제품 문제 아님. 자동화 담당 확인",
        "product": "앱은 정상 동작 중인데 화면 값·동작이 기대와 다름 — 제품 동작 차이(결함 또는 사양 변경)",
    }[primary]
    if c1.get("docker"):
        _last_ctrl.clear()
        _last_ctrl.update(c1)  # 다음 실패는 이 값과 비교
    seen, evidence = set(), []
    for c, t in ev:
        if t not in seen:
            seen.add(t)
            evidence.append({"cat": c, "label": CATS[c][0], "nature": CATS[c][1], "text": t})
    return {"category": primary, "label": label, "nature": nature, "cause": cause, "exception": exc_type,
            "evidence": evidence,
            "before": {"app_procs": len(b_procs), "app_ws_mb": ws0, "main_pid": _main_pid(b_procs), **{f"sys_{k}": v for k, v in m0.items()},
                       **{f"ctrl_{k}": v for k, v in c0.items()}},
            "after": {"app_procs": len(a_procs), "app_ws_mb": ws1, "main_pid": _main_pid(a_procs), **{f"sys_{k}": v for k, v in m1.items()},
                      **{f"ctrl_{k}": v for k, v in c1.items()}, **{f"pc_{k}": v for k, v in s1.items()}},
            "log": log, "events": events, "dumps": dumps}


def short(d):
    """한 줄 요약 (엑셀·JIRA 제목용)."""
    return f"원인 추정: {d['label']} ({d['nature']} 요인)" if d else ""
