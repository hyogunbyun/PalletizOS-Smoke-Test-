"""PalletizOS Home 스모크 러너.

사용법:
  python run_smoke.py               # 전체 실행
  python run_smoke.py --ask         # 시작 시 기대 버전 입력 (엔터 = 생략)
  python run_smoke.py --expect 1.1.0
  python run_smoke.py --only P04 P05
"""
import argparse
import getpass
import json
import os
import sys
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from autotest import env, secret  # noqa: E402
from autotest.flows import FLOWS, SHORT, NotApplicable  # noqa: E402
import autotest.flows_menus  # noqa: E402,F401  (메뉴 흐름 등록: Recipes·IO·Log·Settings·Jog +·Quick Log·Recovery)
import autotest.flows_crawl  # noqa: E402,F401  (전체 클릭 점검 K01~K08·K99)
import autotest.flows_custom  # noqa: E402,F401  (녹화 시나리오 C01… 등록: scenarios/*.json)
from autotest.live import Live  # noqa: E402
from autotest.logcheck import LogWatcher  # noqa: E402
from autotest.report import write_report  # noqa: E402
from autotest.ui import EL, MODE, P, SPEED, STOP_FILE, UI, EnvError, StopRequested, UserInterference, pause  # noqa: E402

RESULTS = ROOT / "results"
HISTORY = RESULTS / "history.json"
LIVE = Live(RESULTS / "live_status.json")
FLASH = {"pass": "PASS", "warn": "PASS", "flaky": "PASS", "fail": "FAIL", "na": "N/A", "env": "SKIP"}
FLASH_SUB = {"warn": "통과 · 새 로그 에러 있음", "flaky": "통과 · 재시도에서 통과(불안정)", "na": "해당없음",
             "env": "환경 오류"}


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


from autotest.events import EVENTS, ev  # noqa: E402  (사건 기록 — env.py와 같은 함수)


def _watch_console_close():
    """콘솔 창 닫기·Ctrl+C·로그오프로 실행기가 죽을 때도 기록을 남긴다 (그동안 아무 기록 없이 사라졌음)."""
    import ctypes
    names = {0: "Ctrl+C", 1: "Ctrl+Break", 2: "콘솔 창 닫힘", 5: "로그오프", 6: "Windows 종료"}

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
    def handler(kind):
        ev(f"실행기 강제 종료: {names.get(kind, kind)} — 결과는 마지막 항목까지 중간 저장분만 남음")
        return 0  # 기본 처리(종료)는 그대로
    _watch_console_close.ref = handler  # 가비지 수집 방지
    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, 1)


def env_log(msg):
    log(msg)
    LIVE.set(step=msg)


class Ctx:
    def __init__(self, ui, logw, expect):
        self.ui, self.log, self.expect_version = ui, logw, expect
        self.snap0 = None
        self.info = {}
        self.outdir = None
        self.note, self.files = "", {}  # 흐름이 남기는 요약 문구·추가 파일 (전체 클릭 점검의 클릭 기록 등)

    def step(self, text):
        """오버레이에 '지금 확인하는 내용' 한 줄 표시."""
        LIVE.set(step=text, action="")

    # ---------- 복구 ----------
    def _n0(self, side):
        lv, lm = self.snap0[side]["layer"]
        bv, bm = self.snap0[side]["boxes"]
        return (int(lv) - 1) * int(bm) + int(bv)

    def restore_side(self, side):
        ui, want = self.ui, self.snap0[side]
        if ui.snapshot()[side]["on"] != want["on"]:
            ui.click(ui.sides()[side].toggle, settle=2)
        if not want["on"]:
            return
        if ui.sides()[side].recipe.window_text() != want["recipe"]:
            ui.click(ui.sides()[side].recipe, settle=2)
            btn = next((b for n, b, _ in ui.recipe_items() if n == want["recipe"]), None)
            if btn is None:
                raise AssertionError(f"복구: 레시피 {want['recipe']} 없음")
            ui.click(btn, settle=1.5)
            ui.click(ui.win_button("Apply"), settle=2.5)
        ui.set_n(side, self._n0(side))

    def restore_all(self):
        ui = self.ui
        ui.back_to_home()  # 메뉴·패널·대화상자·편집기·Recovery 어디서든 Home으로
        if ui.by_name("Stop") is not None:
            ui.wait_for(lambda: ui.by_name("Stop") is None, 45, 1)
        cur = ui.enable_button_name()
        if cur and cur != self.snap0["enable_button"]:
            ui.click(ui.by_name(cur), settle=2)
            ui.wait_for(lambda: ui.enable_button_name() == self.snap0["enable_button"], 10)
        for side in P["side_labels"]:
            self.restore_side(side)
        diff = _diff(self.snap0, ui.snapshot())
        if diff:
            raise AssertionError(f"복구 후 값이 다름: {diff}")


def _home_visible(ui):
    try:
        return ui.on_home()
    except Exception:
        return False


def _diff(a, b):
    out = []
    for k in a:
        if a[k] != b.get(k):
            out.append(f"{k}: {a[k]} → {b.get(k)}")
    return out


def capture(ui, outdir, tag):
    files = {}
    if ui.mode == "mouse":
        LIVE.hide(True)  # 화면 캡처 방식일 때만: 오버레이가 증거 화면을 가리지 않게
    try:
        im = ui.image()
        im.thumbnail((1920, 1080))
        p = outdir / f"{tag}.png"
        im.save(p)
        files["shot"] = p.name
    except Exception:
        pass
    try:
        p = outdir / f"{tag}_tree.txt"
        ui.dump_tree(p)
        files["tree"] = p.name
    except Exception:
        pass
    if ui.mode == "mouse":
        LIVE.hide(False)
    return files


RESULT_BADGE = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "flaky": "WARN", "na": "N/A", "env": "SKIP"}


def run_flow(f, ctx, outdir):
    ui = ctx.ui
    attempts = []
    if not env.app_running():
        ev(f"{f['tc']} 시작 전: 앱이 실행 중이 아님 (외부에서 닫힘 의심) → 다시 실행·연결")
        log("  앱이 꺼져 있음 → 다시 실행·연결")
        env.ensure_ready(ui, env_log)
        if getattr(ctx, "admin_ok", False) and ui.current_role() != "Admin":
            ui.login_as("Admin", secret.load())
    for attempt in (1, 2):
        LIVE.set(badge="ING", step="", action="", foot=("자동화 실행 중 · 마우스/키보드를 만지지 마세요" if ctx.ui.mode == "mouse"
                                                        else "백그라운드 실행 중 · 다른 업무를 해도 됩니다 (앱 창 최소화만 하지 마세요)")
                 + (" · 재시도 2/2" if attempt == 2 else ""))
        ctx.log.mark()
        t0 = time.time()
        rec = {"attempt": attempt, "status": "pass", "msg": ""}
        ctx.note, ctx.files = "", {}
        try:
            f["fn"](ctx)
            rec["msg"] = ctx.note
        except NotApplicable as e:
            rec.update(status="na", msg=str(e))
        except UserInterference:
            raise
        except EnvError as e:
            rec.update(status="env", msg=str(e))
        except Exception as e:  # AssertionError 포함
            rec.update(status="fail", msg=str(e) or type(e).__name__,
                       trace=traceback.format_exc(limit=3))
            rec.update(capture(ui, outdir, f"{f['tc']}_try{attempt}"))
            try:  # 이 시도 동안 앱 로그에 새로 찍힌 줄 → JIRA 이슈 첨부용 (2026-10-22)
                lines = ctx.log.new_lines()
                if lines:
                    lp = outdir / f"{f['tc']}_try{attempt}_applog.txt"
                    lp.write_text("\n".join(lines), encoding="utf-8")
                    rec["log"] = lp.name
            except Exception:
                pass
        rec.update(ctx.files)
        rec["sec"] = round(time.time() - t0, 1)
        rec["new_errors"] = ctx.log.new_errors()
        LIVE.set(step="원상복구 중 (출발 상태로 되돌리기)", action="")
        try:
            ctx.restore_all()
        except UserInterference:
            raise
        except Exception as e:
            gone = not env.app_running()
            if not gone:  # 앱을 끄기 전에 한 번 더: ESC 두 번 → Home 복귀 → 원상복구
                try:
                    ui.esc()
                    ui.esc()
                    ctx.restore_all()
                    ev(f"{f['tc']} 시도{attempt}: 원상복구 1차 실패({str(e)[:80]}) → ESC 후 재시도로 복구됨 (앱 재시작 안 함)")
                    attempts.append(rec)
                    log(f"  {f['tc']} 시도{attempt}: {rec['status']} {rec['msg'][:120]}")
                    if rec["status"] != "fail":
                        break
                    continue
                except UserInterference:
                    raise
                except Exception as e_retry:
                    e = e_retry
            why = "앱 프로세스가 종료돼 있었음 (창을 닫았거나 앱이 꺼짐)" if gone else str(e)
            if not gone:  # 왜 못 돌아왔는지 남기기: 앱을 끄기 전 화면·구조 (2026-10-22: 원인 추적용 캡처가 없었음)
                try:
                    rec.update({f"restore_{k}": v for k, v in capture(ui, outdir, f"{f['tc']}_try{attempt}_restorefail").items()})
                except Exception:
                    pass
            log(f"  복구 실패 → 앱 재시작: {why}")
            rec["restore"] = f"복구 실패 → 앱 재시작 ({why})"
            ev(f"{f['tc']} 시도{attempt}: " + ("앱이 이미 꺼져 있었음(외부에서 닫힘 의심)" if gone else
                                              f"원상복구 실패 → 실행기가 앱 강제 종료·재시작 (원인: {why[:120]})"))
            env.kill_app()
            env.ensure_ready(ui, env_log)
            if getattr(ctx, "admin_ok", False) and ui.current_role() != "Admin":
                try:  # 재시작하면 기본 계정(Operator)으로 로그인됨 → Admin 메뉴 항목이 계속 실패하지 않게 다시 전환
                    ui.login_as("Admin", secret.load())
                except Exception as e2:
                    rec["restore"] += f" / Admin 재로그인 실패 ({e2})"
            try:
                ctx.restore_all()
            except Exception as e2:
                rec["restore"] += f" / 재시작 후에도 복구 실패 ({e2})"
        attempts.append(rec)
        log(f"  {f['tc']} 시도{attempt}: {rec['status']} {rec['msg'][:120]}")
        if rec["status"] != "fail":
            break

    last = attempts[-1]
    status = last["status"]
    if len(attempts) == 2 and status == "pass":
        status = "flaky"
    errs = {}
    for a in attempts:
        errs.update(a["new_errors"])
    if status == "pass" and errs:
        status = "warn"
    return {"tc": f["tc"], "title": f["title"], "desc": f["desc"], "status": status,
            "msg": attempts[0]["msg"] if status in ("fail", "flaky") else last["msg"],
            "attempts": attempts, "new_errors": errs,
            "sec": round(sum(a["sec"] for a in attempts), 1)}


def _count(results):
    out = {}
    for r in results:
        key = r["status"] if r["status"] in ("fail", "na", "env") else "pass"
        out[key] = out.get(key, 0) + 1
    return out


def verdict(results, stopped=False):
    st = [r["status"] for r in results]
    if stopped:
        return "중단"
    if "fail" in st:
        return "보류"
    if "env" in st:
        return "재실행 필요"
    if any(s in ("warn", "flaky") for s in st):
        return "통과(주의)"
    return "통과"


def _show_done_popup(run, outdir, url, started):
    """모든 칩이 끝나면 화면 가운데 '자동화 수행 완료' 창 (별도 프로세스 — 러너가 끝나도 남음, 2분 뒤 닫힘). 2026-10-27 사용자 요청"""
    try:
        c = _count(run["results"])
        names = {"pass": "통과", "fail": "실패", "na": "해당없음", "env": "환경 오류"}
        info = {"verdict": run["verdict"], "report": url, "total": len(run["results"]),
                "version": run.get("expect_version") or run.get("palletizos_version"),
                "started": started.strftime("%H:%M"), "finished": datetime.now().strftime("%H:%M"),
                "minutes": round((datetime.now() - started).total_seconds() / 60),
                "counts": {names.get(k, k): n for k, n in c.items()},
                "fails": [r["tc"] for r in run["results"] if r["status"] == "fail"]}
        import subprocess
        f = outdir / "done_popup.json"
        f.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        pr = subprocess.Popen([str(pyw if pyw.exists() else exe), "-m", "autotest.done_popup", str(f)], cwd=str(Path(__file__).resolve().parent),
                              creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        ev(f"완료 창 띄움 (pid {pr.pid}) — 화면에 뜨면 [완료창] 표시됨 줄이 이어서 남음")
    except Exception as e:  # noqa: BLE001
        log(f"완료 창을 띄우지 못함: {e}")


def _update_check():
    """시작 팝업: GitHub 신규 빌드 확인 → 있으면 자동 설치(진행 상황 표시). 설치했으면 그 버전(기대 버전으로 씀), 아니면 None.
    (2026-10-27 사용자 요청: 처음 실행할 때 확인을 눈에 보이게, 새 버전은 묻지 않고 자동 설치)"""
    try:
        from autotest.update_popup import check_and_install
        got = check_and_install(log)
    except Exception as e:  # noqa: BLE001  팝업이 안 돼도 평가는 진행
        log(f"신규 버전 확인 팝업 실패: {e}")
        return None
    if got:
        try:  # 감시기 기록에도 남겨 같은 버전을 다시 설치·평가하지 않게
            from autotest.watcher import load_state, save_state
            st = load_state()
            st.setdefault("installed_at", {})[got] = datetime.now().isoformat(timespec="seconds")
            save_state(st)
        except Exception:
            pass
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect")
    ap.add_argument("--ask", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--no-overlay", action="store_true")
    ap.add_argument("--mode", choices=["background", "mouse"], help="입력 방식 (기본: elements.yaml input_mode)")
    ap.add_argument("--no-update-check", action="store_true", help="시작 팝업(GitHub 신규 버전 확인) 생략 — 감시기가 설치 직후 띄울 때")
    a = ap.parse_args()
    expect = a.expect
    if not a.no_update_check and not a.only:
        expect = _update_check() or expect
    if a.ask and not expect:
        expect = input("이번에 설치한 PalletizOS 버전 (예: 1.1.0, 엔터 = 생략): ").strip() or None

    started = datetime.now()
    outdir = RESULTS / started.strftime("%Y%m%d_%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    if (a.mode or MODE) == "mouse":
        print(" PalletizOS 스모크 실행 중 (실제 마우스) — 끝날 때까지 마우스·키보드를 만지지 마세요")
    else:
        print(" PalletizOS 스모크 실행 중 (백그라운드) — 앱 창을 최소화하지만 않으면 다른 업무를 해도 됩니다")
    print("=" * 60)

    ui = UI()
    if a.mode:
        ui.mode = a.mode
    ui.on_click = lambda name: LIVE.set(action=f"클릭: {name}")
    ctx = Ctx(ui, LogWatcher(), expect)
    ctx.outdir = outdir
    flows = [f for f in FLOWS if not a.only or f["tc"] in a.only]
    LIVE.enabled = not a.no_overlay
    LIVE.mode = ui.mode
    STOP_FILE.unlink(missing_ok=True)  # 지난 실행의 종료 요청이 남아 있지 않게
    LIVE.set(badge="ING", flow="환경 준비", desc="시뮬레이터 → 앱 → 제어기 연결 → PalletizOS 진입 확인",
             chips=[(f["tc"], None) for f in flows], chip_labels={f["tc"]: f"{f['tc']} {SHORT.get(f['tc'], '')}" for f in flows},
             index=None, total=len(flows), done=False, hidden=False)
    LIVE.start()
    ev(f"실행 시작: 결과 폴더 {outdir.name}, 항목 {len(flows)}개" + (f" (--only {' '.join(a.only)})" if a.only else "") +
       f", 입력 방식 {ui.mode}")
    _watch_console_close()
    guard = None
    if ui.mode == "background" and EL.get("focus_guard", True) and os.environ.get("SMOKE_NO_FOCUS_GUARD") != "1":  # 앱이 스스로 앞으로 나와 포커스를 가져가면 쓰던 창으로 되돌림
        from autotest.focusguard import FocusGuard
        guard = FocusGuard(log)
        guard.start()
    run = {"started": started.isoformat(timespec="seconds"), "expect_version": expect,
           "platform_version": env.platform_version(), "results": [], "notes": []}
    try:
        env.ensure_ready(ui, env_log)
        ui.remember_nav()
        start_role = ui.wait_role()
        run["start_role"] = start_role
        ctx.admin_ok, admin_err = start_role == "Admin", None
        if not ctx.admin_ok and any(f["admin"] for f in flows):
            # 비밀번호 출처: 환경변수 → Windows 자격 증명(저장분) → 직접 입력(.bat 실행 시만). 파일에는 남기지 않음
            pw = os.environ.pop("PALLETIZOS_ADMIN_PW", None) or secret.load()
            typed = False
            if not pw and a.ask:
                LIVE.set(badge="WAIT", flow="Admin 비밀번호 입력 대기",
                         desc="검은 콘솔 창(PalletizOS_smoke)에 Admin 비밀번호를 입력하고 엔터 (글자는 안 보임, 엔터만 = 건너뜀). "
                              "한 번 성공하면 저장되어 다음부터는 묻지 않음",
                         step="콘솔 창에서 입력을 기다리는 중", action="")
                pw = getpass.getpass("Recipes·Log·Settings 확인용 Admin 비밀번호 (화면에 표시 안 됨, 엔터 = 건너뜀): ") or None
                typed = bool(pw)
            env_log("Admin으로 계정 전환" if pw else "Admin 비밀번호 없음 → Admin 전용 흐름은 건너뜀")
            if pw:
                try:
                    ui.login_as("Admin", pw)
                    ctx.admin_ok = True
                    if typed:
                        secret.save(pw)  # 성공한 비밀번호만 저장 → 다음 실행부터 자동
                        log("Admin 비밀번호를 Windows 자격 증명에 저장함 (다음부터 묻지 않음)")
                except EnvError as e:
                    admin_err = str(e)
                    if not typed and "로그인 실패" in admin_err:
                        admin_err += " — 저장된 비밀번호가 틀림: python -m autotest.secret set 으로 다시 저장"
            pw = None
        if not ctx.admin_ok and any(f["admin"] for f in flows):
            admin_err = admin_err or "Admin 비밀번호를 입력하지 않음"
            run["notes"].append(f"Admin 전용 흐름 건너뜀: {admin_err}")
        LIVE.set(step="출발 상태 기록 (끝나면 이 값으로 되돌림)")
        ctx.snap0 = ui.snapshot()
        run["snap0"] = ctx.snap0
        log(f"출발 상태: {json.dumps(ctx.snap0, ensure_ascii=False)}")
        for i, f in enumerate(flows):
            log(f"{f['tc']} {f['title']}")
            LIVE.set(badge="ING", index=i + 1, flow=f"{f['tc']} · {f['title']}", desc=f["desc"])
            LIVE.set_chip(f["tc"], "run")
            try:
                if f["admin"] and not ctx.admin_ok:
                    res = {"tc": f["tc"], "title": f["title"], "desc": f["desc"], "status": "env",
                           "msg": f"Admin 계정이 필요함 ({admin_err})", "attempts": [], "new_errors": {}, "sec": 0}
                else:
                    res = run_flow(f, ctx, outdir)
                run["results"].append(res)
                try:  # 항목마다 중간 결과 저장: 콘솔 창을 닫거나 실행이 강제로 끝나도 여기까지의 결과가 남게 (2026-10-22: 결과 파일 없이 끝난 실행 여러 건)
                    (outdir / "result.json").write_text(json.dumps({**run, "verdict": "진행 중(중간 저장)"}, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
                except Exception:
                    pass
                LIVE.set_chip(f["tc"], res["status"])
                sub = FLASH_SUB.get(res["status"], "")
                # 항목이 끝난 순간에만 큰 배지에 그 항목 결과(PASS/FAIL…)를 1초 표시 — 제목이 아직 이 항목이라 섞이지 않음.
                # 다음 항목이 시작되면 다시 ING. 누적 집계는 상단 줄에 계속 (2026-10-21 사용자 요청: 중간에 PASS/FAIL이 안 보임)
                c = {}
                for r_ in run["results"]:
                    k = {"flaky": "warn", "env": "na"}.get(r_["status"], r_["status"])
                    c[k] = c.get(k, 0) + 1
                LIVE.set(badge=RESULT_BADGE.get(res["status"], "N/A"), step="", action="",
                         tally=" · ".join(f"{n} {c[k]}" for k, n in (("pass", "통과"), ("fail", "실패"), ("warn", "주의"), ("na", "제외")) if c.get(k)))
                time.sleep(1.0)
                LIVE.set(last=f"직전: {f['tc']} {f['title']} → {FLASH[res['status']]}" + (f" ({sub})" if sub else "")
                         + (f" — {res['msg'][:80]}" if res["status"] in ("fail", "flaky") and res["msg"] else ""))
            except UserInterference as e:
                run["notes"].append(f"중단: {e}")
                for g in flows[i:]:
                    run["results"].append({"tc": g["tc"], "title": g["title"], "desc": g["desc"],
                                           "status": "env", "msg": str(e), "attempts": [], "new_errors": {}, "sec": 0})
                break
        if ctx.snap0:
            final = _diff(ctx.snap0, ui.snapshot()) if _home_visible(ui) else ["Home 화면이 아님"]
            if start_role and ui.current_role() != start_role:
                LIVE.set(step=f"시작 계정({start_role})으로 되돌리기", action="")
                try:
                    ui.login_as(start_role)
                except Exception as e:
                    final.append(f"계정 원복 실패 ({start_role}): {e}")
            run["restored"] = not final
            run["restore_diff"] = final
    except EnvError as e:
        run["notes"].append(f"환경 준비 실패: {e}")
        capture(ui, outdir, "env_error")
    except StopRequested:
        src = STOP_FILE.read_text(encoding="utf-8").strip() if STOP_FILE.exists() else ""
        ev("종료 요청 받음 → 원상복구 후 중단" + (f" (요청 내용: {src})" if src and src != "stop" else " (요청한 곳은 같은 파일의 바로 앞 줄 참고)"))
        STOP_FILE.unlink(missing_ok=True)  # 복구하는 동안 다시 멈추지 않게
        run["stopped"] = True
        run["notes"].insert(0, "사용자가 자동화를 종료함")
        log("종료 요청 → 원래 상태로 되돌리는 중")
        LIVE.set(badge="STOP", flow="종료 요청됨", desc="진행 중이던 항목을 멈추고 화면 값을 원래대로 되돌리는 중",
                 step="원상복구 중", action="", last="")
        if ctx.snap0:
            try:
                ctx.restore_all()
                if run.get("start_role") and ui.current_role() != run["start_role"]:
                    ui.login_as(run["start_role"])
                run["restored"], run["restore_diff"] = True, []
            except BaseException as e:
                run["restored"], run["restore_diff"] = False, [f"종료 후 복구 실패: {e}"]
    except Exception as e:  # 실행기에서 처리 못 한 오류: 그동안은 콘솔에만 찍히고 결과 파일 없이 끝났음
        tb = traceback.format_exc()
        (outdir / "runner_crash.txt").write_text(tb, encoding="utf-8")
        run["notes"].insert(0, f"실행기 오류로 중단: {type(e).__name__}: {e}")
        ev(f"실행기 오류로 중단: {type(e).__name__}: {str(e)[:150]} (상세 {outdir.name}/runner_crash.txt)")
        log(f"실행기 오류: {type(e).__name__}: {e}")
        try:
            capture(ui, outdir, "runner_crash")
        except Exception:
            pass
    # 끝까지 못 간 항목은 '환경 오류'로 채운다 → 일부만 돌고 '통과'로 판정되는 일이 없게
    done_tcs = {r["tc"] for r in run["results"]}
    missing = [f for f in flows if f["tc"] not in done_tcs]
    if missing:
        why = run["notes"][0] if run["notes"] else "실행이 중간에 끝남"
        for f in missing:
            run["results"].append({"tc": f["tc"], "title": f["title"], "desc": f["desc"], "status": "env",
                                   "msg": f"실행되지 않음 — {why}", "attempts": [], "new_errors": {}, "sec": 0})
        run["notes"].append(f"{len(missing)}개 항목이 실행되지 않음 → 재실행 필요")
    run.update(ctx.info)
    if guard is not None:
        guard.stop()
        run["focus_restored"] = guard.restored
        if guard.restored:
            log(f"실행 중 앱이 포커스를 가져간 횟수: {guard.restored} (모두 쓰던 창으로 되돌림)")
    run["finished"] = datetime.now().isoformat(timespec="seconds")
    run["verdict"] = verdict(run["results"], run.get("stopped"))

    hist = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    prev = next((h for h in reversed(hist) if h.get("palletizos_version")), None)
    if prev and prev.get("palletizos_version") == run.get("palletizos_version") \
            and prev.get("platform_version") == run.get("platform_version"):
        run["notes"].append(f"버전 변경 없음: 지난 실행({prev['started']})과 같은 버전 "
                            f"(PalletizOS {run.get('palletizos_version')}, Platform {run.get('platform_version')})")
    (outdir / "result.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    hist.append({"started": run["started"], "dir": outdir.name, "verdict": run["verdict"],
                 "palletizos_version": run.get("palletizos_version"), "platform_version": run.get("platform_version"),
                 "flows": {r["tc"]: r["status"] for r in run["results"]}})
    HISTORY.write_text(json.dumps(hist[-50:], ensure_ascii=False, indent=1), encoding="utf-8")

    report = write_report(run, outdir, hist)
    final_badge = {"통과": "PASS", "통과(주의)": "PASS", "보류": "FAIL", "재실행 필요": "FAIL", "중단": "STOP"}[run["verdict"]]
    done_txt = "자동화 수행 완료" if run["verdict"] != "중단" else "자동화 중단됨"
    LIVE.set(badge=final_badge, index=None, flow=f"{done_txt} · 전체 판정: {run['verdict']}",
             desc="결과 리포트를 브라우저로 엽니다" if not a.no_open else str(report),
             step=" · ".join(f"{ {'pass': 'PASS', 'fail': 'FAIL', 'na': 'N/A', 'env': '환경 오류'}[k]} {n}"
                             for k, n in _count(run["results"]).items()),
             action="재실행 필요 = 환경 오류(제품 결함 아님)" if run["verdict"] == "재실행 필요" else "",
             foot=f"{done_txt} · 이 표시는 60초 뒤 사라집니다", done=True, linger=60)
    log(f"판정: {run['verdict']}  리포트: {report}")
    ev(f"실행 끝: 판정 {run['verdict']} · " + " · ".join(f"{k} {n}" for k, n in _count(run["results"]).items()) +
       (f" · 앱 재시작 {sum(1 for r in run['results'] for x in r.get('attempts', []) if x.get('restore'))}회"))
    url_for_popup = report.as_uri()
    if not a.no_open:
        # FAIL 행의 '이슈 등록' 버튼은 등록 서버(127.0.0.1:8781) 주소로 연 리포트에서만 동작
        from autotest.issue_server import PORT, ensure_running
        url = report.as_uri()
        try:
            if ensure_running():
                url = f"http://127.0.0.1:{PORT}/results/{outdir.name}/report.html"
        except Exception as e:
            log(f"이슈 등록 서버를 띄우지 못함 → 파일로 엶 ({e})")
        ok = webbrowser.open(url)
        ev(f"결과 리포트 브라우저로 열기 {'요청됨' if ok else '실패'}: {url}")
        url_for_popup = url
    _show_done_popup(run, outdir, url_for_popup, started)
    return 1 if run["verdict"] == "보류" else 0


if __name__ == "__main__":
    sys.exit(main())
