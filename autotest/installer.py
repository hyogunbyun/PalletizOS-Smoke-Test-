"""PalletizOS .dm 설치 (Dr.Dart Platform → Settings → Installed Module List → Install from File).

2026-10-26 실측 화면 구조:
- Platform 메인 화면 'settings icon Settings …' 버튼 → 좌측 'Installed Module List' → 우측 위 'Install from File'
- 'Install from File' = Windows 파일 열기 창(#32770): 파일 이름 칸 Edit(ID 1148), 열기 버튼 ID 1
- 성공 판정 = 앱 로그 '[Updater] Successfully updated the PalletizOS' 또는 '[Installer] Successfully installed … PalletizOS'
  실패 = '[InstalledModuleList] Failed to install …' / '[Installer|Updater] Failed …' (10-07 실측: 'caused by 16777217')
명령줄: python -m autotest.installer <.dm 경로>
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import sys
import time
from pathlib import Path

from . import env
from .events import ev
from .logcheck import LogWatcher
from .ui import UI, EnvError

user32 = ctypes.windll.user32
OK_PAT = re.compile(r"\[(Updater|Installer)\] Successfully (updated|installed) the PalletizOS")
FAIL_PAT = re.compile(r"Failed to (install|update) the com\.dart\.module\.palletizos|\[(Updater|Installer)\] Failed.*palletizos", re.I)
CONFIRM = ("Install", "Update", "Confirm", "OK", "Yes", "설치", "업데이트", "확인")  # 설치 확인창이 뜨면 누를 버튼 (있을 때만)


def installed_version():
    """지금 설치된 PalletizOS 버전 (예: '2.0.0-20'). 앱 로그를 시간순으로 읽어 마지막 근거를 쓴다:
    - 화면 로드 기록 "packageName":"com.dart.module.palletizos","version":"X"
    - 설치/업데이트 성공: 직전 'Start update|install the com.dart.module.palletizos_X_signed.dm' + 'Successfully updated|installed the PalletizOS'
    (설치 화면에서는 PalletizOS 화면이 안 열려 화면 로드 기록이 안 남음 → 성공 기록도 봐야 함, 2026-10-26 오판 수정)"""
    screen = re.compile(r'"packageName":"com\.dart\.module\.palletizos","version":"([^"]+)"')
    start = re.compile(r"Start (?:update|install) the com\.dart\.module\.palletizos_(.+?)_signed")
    files = sorted(Path(r"C:\Dr.Dart-Platform\logs").glob("20*.log"))[-5:]
    cur, pending = None, None
    for f in files:
        for line in f.read_bytes().decode("utf-8", "replace").splitlines():
            m = screen.search(line)
            if m:
                cur = m.group(1)
                continue
            m = start.search(line)
            if m:
                pending = m.group(1)
                continue
            if pending and OK_PAT.search(line):
                cur, pending = pending, None
    return cur


def _fill_file_dialog(path, timeout=15):
    from .winutil import native_dialogs
    end = time.time() + timeout
    while time.time() < end:
        d = native_dialogs()
        if d:
            h = d[0][0]
            edit = user32.GetDlgItem(h, 1148)  # ComboBoxEx32 → 그 안의 Edit
            target = user32.FindWindowExW(user32.FindWindowExW(edit, None, "ComboBox", None), None, "Edit", None) or edit
            user32.SendMessageW(target, 0x000C, 0, ctypes.c_wchar_p(str(path)))  # WM_SETTEXT
            time.sleep(0.3)
            user32.SendMessageW(user32.GetDlgItem(h, 1), 0x00F5, 0, 0)  # BM_CLICK '열기'
            return True
        time.sleep(0.3)
    return False


def _to_platform_home(ui, log):
    """앱을 새로 띄워 연결·제어권 회수까지 (PalletizOS는 열지 않음) → Platform 메인 화면."""
    if ui.exists():
        env.kill_app()
    env.ensure_simulator(log)
    env.launch_app()
    if not ui.win.exists(timeout=90) or not ui.wait_window_stable(90):
        raise EnvError("앱 창이 뜨지 않음")
    ui.warm_up()
    ui.ensure_maximized()
    env._connect_if_needed(ui, log)
    env._take_over_if_needed(ui, log)
    env._skip_tour(ui)
    time.sleep(2)
    ui.warm_up()


def _button(ui, pred, timeout=20):
    """이름 조건에 맞는 버튼 또는 목록 항목 (한국어 화면의 '설치된 모듈 리스트'는 ListItem으로만 잡힘, 2026-10-27)."""
    def find():
        for ct in ("Button", "ListItem"):
            x = next((b for b in ui.wrapper().descendants(control_type=ct) if pred((b.window_text() or "").strip())), None)
            if x is not None:
                return x
        return None
    hit = []
    ui.wait_for(lambda: hit.append(find()) or hit[-1] is not None, timeout, 0.5)
    return hit[-1] if hit else None


def _skip_coachmark(ui):
    """'서보 켜기 1 of 9' 같은 안내 투어 창이 화면을 가리면 건너뛰기 (2026-10-27 실측: Settings 위에 뜸)."""
    for name in ("건너뛰기", "Skip"):
        try:
            t = next((x for x in ui.wrapper().descendants(control_type="Button") if (x.window_text() or "").strip() == name), None)
            if t is not None:
                ui.click(t, settle=1.5, label=f"안내 투어 {name}")
                return True
        except Exception:
            pass
    return False


INSTALL_LOCK = Path(__file__).resolve().parent.parent / "results" / "install.lock"


def _pid_alive(pid):
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = wt.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def install_busy():
    """다른 프로세스가 설치 중이면 그 pid, 아니면 None."""
    try:
        pid = int(INSTALL_LOCK.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return pid if pid != os.getpid() and _pid_alive(pid) else None


def install_dm(path, log=print):
    """.dm 설치. 성공하면 설치된 버전 문자열, 실패하면 EnvError.

    한 번에 하나만 (install.lock). 2026-10-29 08:12~08:17 감시기 설치 도중 실행기 5개가 같은 설치를 잇달아 시작 →
    설치마다 앱을 끄고 다시 연결하므로 서로의 앱을 꺼 버려 어느 것도 끝나지 못함."""
    path = Path(path).resolve()
    if not path.exists():
        raise EnvError(f"설치 파일 없음: {path}")
    busy = install_busy()
    if busy:
        ev(f"설치 건너뜀: 다른 프로세스(pid {busy})가 이미 설치 중 — 겹치면 서로 앱을 꺼 버림")
        raise EnvError(f"다른 프로그램(pid {busy})이 이미 설치 중입니다 — 끝난 뒤 다시 실행하세요")
    INSTALL_LOCK.parent.mkdir(exist_ok=True)
    INSTALL_LOCK.write_text(f"{os.getpid()} {path.name}", encoding="utf-8")
    try:
        return _install(path, log)
    finally:
        try:
            if INSTALL_LOCK.read_text().split()[0] == str(os.getpid()):
                INSTALL_LOCK.unlink()
        except (OSError, IndexError):
            pass


def _install(path, log):
    before = installed_version()
    who = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "?"
    ev(f"설치 시작: {path.name} (설치 전 버전 {before}) · 호출 {who} {' '.join(sys.argv[1:])[:80]}")
    ui = UI()
    _to_platform_home(ui, log)
    # 화면 언어는 제어기 설정을 따름 → 영어·한국어 모두 (2026-10-27: 한국어 화면에서 'Installed Module List'를 못 찾아 실패)
    b = _button(ui, lambda t: t.startswith("settings icon"))
    if b is None:
        raise EnvError("Platform 메인 화면의 Settings 버튼을 찾지 못함")
    ui.click(b, settle=4, label="Platform Settings")
    _skip_coachmark(ui)
    b = _button(ui, lambda t: t == "Installed Module List" or "모듈 목록" in t or "모듈 리스트" in t)
    if b is None:
        raise EnvError("'Installed Module List(설치된 모듈 목록)' 메뉴를 찾지 못함 (supervisor 권한 필요할 수 있음)")
    ui.click(b, settle=3, label="Installed Module List")
    _skip_coachmark(ui)
    b = _button(ui, lambda t: t == "Install from File" or ("파일" in t and "설치" in t))
    if b is None:
        raise EnvError("'Install from File(파일에서 설치)' 버튼을 찾지 못함")
    watch = LogWatcher()
    watch.mark()
    ui.click(b, settle=2, label="Install from File")
    if not _fill_file_dialog(path):
        raise EnvError("파일 선택 창이 뜨지 않음")
    log(f"설치 파일 선택: {path.name}")
    # 설치 확인창이 뜨면 누르고, 로그로 성공/실패 판정 (최대 5분)
    end, clicked = time.time() + 300, set()
    while time.time() < end:
        lines = watch.new_lines()
        if any(OK_PAT.search(l) for l in lines):
            time.sleep(5)
            after = installed_version()
            ev(f"설치 성공: {path.name} → PalletizOS {after}")
            log(f"설치 성공 → PalletizOS {after}")
            return after
        bad = next((l for l in lines if FAIL_PAT.search(l)), None)
        if bad:
            ev(f"설치 실패: {path.name} — {bad.strip()[:160]}")
            raise EnvError(f"설치 실패: {bad.strip()[:160]}")
        try:
            for c in CONFIRM:
                t = ui.top_find(c)
                if t is not None and c not in clicked and t.is_enabled():
                    ui.click(t, settle=2, label=f"설치 확인 '{c}'")
                    clicked.add(c)
                    break
        except Exception:
            pass
        time.sleep(2)
    ev(f"설치 시간 초과: {path.name} (5분 안에 성공/실패 기록 없음)")
    raise EnvError("설치가 5분 안에 끝나지 않음 (앱 로그에 성공 기록 없음)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(install_dm(sys.argv[1]))
    except EnvError as e:
        sys.exit(f"설치 실패: {e}")
