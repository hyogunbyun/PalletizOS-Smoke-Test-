"""데일리 빌드 감시기 (2026-10-26 사용자 요청): GitHub 릴리스에 새 PalletizOS .dm이 올라오면 받아서 설치하고 스모크 전체 실행.

- 30분마다 dsg-robotics/palletizingsolution 릴리스 확인 (elements.yaml watch.interval_min)
- 첨부 파일 com.dart.module.palletizos_<버전>_signed.dm 중 가장 높은 버전이 '지금 설치된 버전'보다 높으면
  → 다른 스모크 실행이 끝날 때까지 대기 → 다운로드(releases/<태그>/) → 설치(Install from File) → 스모크 전체 실행(run_auto.bat)
- 같은 버전은 앱이 설치를 거부함(ERROR_INVALID_VERSION, 10-26 실측) → 높은 버전만
- 같은 버전 설치 실패는 2번까지만 다시 시도 (results/watch_state.json)
- 기록: results/events.log ([감시기]) + results/watch.log
실행: pythonw -m autotest.watcher (로그온 시 시작프로그램) / --once (한 번만 확인) / 멈춤: results/watch.stop 파일
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from autotest import github  # noqa: E402
from autotest.ui import EL  # noqa: E402

RES = ROOT / "results"
STATE = RES / "watch_state.json"
LOCK = RES / "watch.lock"
STOPF = RES / "watch.stop"
WLOG = RES / "watch.log"
ASSET = re.compile(r"^com\.dart\.module\.palletizos_(.+)_signed\.dm$")
CFG = EL.get("watch", {})
INTERVAL = int(CFG.get("interval_min", 30)) * 60
MAX_TRIES = 2
VALID = ("통과", "통과(주의)", "보류")  # 항목이 실제로 돈 판정. '재실행 필요'(환경 오류)·'중단'은 평가 안 된 것으로 봄


def wlog(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} [감시기 {os.getpid()}] {msg}"
    for p in (WLOG, RES / "events.log"):
        try:
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
    if sys.stdout:  # pythonw(창 없음)로 돌 때는 출력 대상이 없음
        print(line, flush=True)


def vkey(v):
    """'2.0.0-17' → (2, 0, 0, 17). 숫자 아닌 조각은 0."""
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-_+]", v or ""))


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tries": {}, "done": {}}


def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def smoke_running():
    """다른 스모크 실행(run_smoke.py)이 돌고 있는지."""
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'run_smoke' } | Measure-Object).Count"],
                       capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        return int((r.stdout or "0").strip() or 0) > 0
    except ValueError:
        return False


def newest_build():
    """(버전, 릴리스, 첨부) — 릴리스들의 palletizos .dm 중 가장 높은 버전."""
    best = None
    for rel in github.releases(15):
        for a in rel["assets"]:
            m = ASSET.match(a["name"])
            if m and (best is None or vkey(m.group(1)) > vkey(best[0])):
                best = (m.group(1), rel, a)
    return best


def _adopt_manual_run(ver, st):
    """설치 뒤에 (바탕화면 등으로) 돈 유효한 실행이 있으면 그 결과를 이 버전의 평가로 기록. 있으면 True."""
    since = st.get("installed_at", {}).get(ver)
    if not since:
        return False
    for d in sorted(RES.glob("2026*"), reverse=True):
        try:
            r = json.loads((d / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r.get("started", "") >= since and r.get("verdict") in VALID:
            st["done"][ver] = {"at": datetime.now().isoformat(timespec="seconds"), "result": d.name,
                               "verdict": r["verdict"], "valid": True, "adopted": True}
            save_state(st)
            wlog(f"{ver}: 설치 후 실행된 결과 {d.name}({r['verdict']})를 평가로 인정 → 다시 돌리지 않음")
            return True
    return False


def check_once():
    from autotest.installer import install_dm, installed_version
    st = load_state()
    try:
        nb = newest_build()
    except github.GitHubError as e:
        wlog(f"릴리스 확인 실패: {e}")
        return
    if nb is None:
        wlog("릴리스에 palletizos .dm 첨부가 없음")
        return
    ver, rel, asset = nb
    cur = installed_version()
    if cur and vkey(ver) <= vkey(cur):
        if ver == cur and not st["done"].get(ver, {}).get("valid"):
            # 설치는 됐는데 유효한 평가가 없음 → 돌고 있는 실행이 끝나길 기다렸다가, 그 결과가 유효하면 인정, 아니면 스모크만 다시
            while smoke_running():
                wlog("다른 스모크 실행이 진행 중 → 끝날 때까지 대기")
                time.sleep(120)
            if _adopt_manual_run(ver, st):
                return
            wlog(f"{ver}: 설치돼 있지만 유효한 평가 결과 없음 → 스모크만 실행")
            run_smoke_for(ver, st)
            return
        wlog(f"새 버전 없음 (릴리스 최고 {ver} · 설치됨 {cur})")
        return
    tries = st["tries"].get(ver, 0)
    if tries >= MAX_TRIES:
        wlog(f"{ver}: 설치 {tries}회 실패 → 더 시도하지 않음 (수동 확인 필요)")
        return
    wlog(f"새 버전 발견: {ver} (설치됨 {cur}, 릴리스 {rel['tag']}) → 설치·평가 시작")
    while smoke_running():  # 사람이 돌리는 실행과 겹치지 않게
        wlog("다른 스모크 실행이 진행 중 → 끝날 때까지 대기")
        time.sleep(120)
    from autotest.env import wait_docker
    if not wait_docker(wlog):  # 엔진이 안 켜졌으면 시도 횟수를 쓰지 않고 다음 확인 때 다시
        wlog("Docker 엔진이 켜지지 않아 이번 확인은 건너뜀 (설치 시도 횟수에 안 셈)")
        return
    st["tries"][ver] = tries + 1
    save_state(st)
    try:
        path = github.download(rel, pick=lambda n: n == asset["name"])[0]
        wlog(f"다운로드 완료: {path}")
        got = install_dm(path, log=wlog)
    except Exception as e:  # noqa: BLE001
        wlog(f"설치 실패: {type(e).__name__}: {e}")
        return
    st.setdefault("installed_at", {})[got or ver] = datetime.now().isoformat(timespec="seconds")
    save_state(st)
    run_smoke_for(got or ver, st)


def run_smoke_for(ver, st):
    """설치된 버전으로 스모크 전체 실행 (새 콘솔 창, 끝날 때까지 대기) → 결과 기록.
    2026-10-26: 'cmd /c start /wait …'는 창 없는 감시기에서 바로 끝나 실행이 안 됐음 → 실행기를 직접 새 콘솔로 띄움"""
    wlog(f"{ver} 스모크 전체 실행 시작")
    t0 = time.time()
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}
    subprocess.run([str(py), "-X", "utf8", "run_smoke.py", "--expect", ver, "--no-update-check"], cwd=str(ROOT), env=env,
                   creationflags=subprocess.CREATE_NEW_CONSOLE)
    new = [d for d in RES.glob("2026*") if d.is_dir() and d.stat().st_ctime >= t0 - 5 and (d / "result.json").exists()]
    last = max(new, key=lambda d: d.name) if new else None
    verdict = ""
    if last:
        try:
            verdict = json.loads((last / "result.json").read_text(encoding="utf-8")).get("verdict", "")
        except Exception:
            pass
    st["done"][ver] = {"at": datetime.now().isoformat(timespec="seconds"), "result": last.name if last else None,
                       "verdict": verdict, "valid": verdict in VALID}
    save_state(st)
    wlog(f"{ver} 평가 끝: {verdict or '결과 없음'} (결과 {last.name if last else '-'})")


def main():
    once = "--once" in sys.argv
    if not once:
        if LOCK.exists():  # 이미 다른 감시기가 돌고 있으면 종료
            try:
                pid = int(LOCK.read_text())
                import ctypes
                h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
                    return
            except (OSError, ValueError):
                pass
        LOCK.write_text(str(os.getpid()))
        STOPF.unlink(missing_ok=True)
        wlog(f"감시 시작: {github.REPO} · {INTERVAL // 60}분마다")
    try:
        while True:
            try:
                check_once()
            except Exception as e:  # noqa: BLE001  감시기는 죽지 않게
                wlog(f"확인 중 오류: {type(e).__name__}: {e}")
            if once:
                return
            for _ in range(INTERVAL // 10):
                if STOPF.exists():
                    wlog("감시 중지 (watch.stop)")
                    return
                time.sleep(10)
    finally:
        if not once:
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except BaseException as e:  # noqa: BLE001  창 없이 돌 때 죽은 이유가 남게 (SystemExit·KeyboardInterrupt 포함)
        wlog(f"감시기 오류로 종료: {type(e).__name__}: {e}")
        raise
