"""PalletizOS TC·체크리스트 자동 평가 실행기.

TC/체크리스트 엑셀 → 행마다 맞는 자동 점검 루틴을 찾음 → 기존 스모크 엔진(run_smoke)으로 실행 → 같은 엑셀 사본에 판정 기록.
기존 PalletizOS_smoke 는 그대로 두고, run_smoke 를 모듈로 불러와 점검 목록만 바꿔 쓴다
(환경 준비·상태 표시창·■ 종료·원상복구·리포트·완료 창은 스모크와 같음).

사용:
  python tc_run.py <엑셀 경로>          자동 평가 + 결과 사본(<이름>_자동판정_<시각>.xlsx)
  python tc_run.py <엑셀 경로> --dry    매칭 결과만 보기 (앱 조작 없음)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

from tc_autotest.checks import CHECKS, match_check, nt_reason  # noqa: E402
from tc_autotest.workbook import read_rows, write_results  # noqa: E402

DEFAULT_WB = ROOT.parent / "tc" / "PalletizOS TC" / "PalletizOS_v2.0.0-21_Change_TC_V1.0.xlsx"
SHORT = {"CFG_DEFAULT": "툴설정 기본", "CFG_ADDZONE": "Add Zone", "CFG_NODEL": "존 삭제", "IO_LIFT_OFF": "Lift 이름",
         "SLIP_LABELS": "슬립 문구", "SLIP_HELP_SEEK": "Seek 도움말", "SLIP_HELP_RETRACT": "Retract 도움말",
         "MODEL_POPUP": "3D 팝업", "SMOKE_MONITOR": "스모크 H04·05", "SMOKE_TOOLLIST": "스모크 S04", "SMOKE_ALL": "스모크 전체",
         "SD024_01": "024 기본", "SD024_02": "024 저장", "SD024_03": "024 Type", "SD024_04": "024 경계",
         "SD024_05": "024 이탈", "SD024_06": "024 단위",
         "TIO_04": "빈 주소", "TIO_05": "Reducer 빈", "TIO_06": "Blow off", "TIO_07": "주소 중복", "TIO_08": "Double", "TIO_09": "신호 타입",
         "CEIL_19": "천장 기본", "CEIL_20": "천장 mm", "CEIL_21": "천장 in", "CEIL_22": "여유<0", "CEIL_23": "여유 0", "CEIL_24": "베이스", "CEIL_25": "리프트", "CEIL_29": "Admin 배너", "CEIL_32": "오프셋"}


def plan(path):
    rows = read_rows(path)
    for x in rows:
        c = match_check(x.get("title"), x["text"])
        x["check"] = c["key"] if c else None
    return rows


def _busy():
    """스모크 실행 중이거나 설치 중이면 그 이유."""
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'run_smoke' } | Measure-Object).Count"],
                       capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if (r.stdout or "0").strip() not in ("", "0"):
        return "PalletizOS_smoke 가 실행 중입니다 — 끝난 뒤 다시 실행하세요"
    from autotest.installer import install_busy
    if install_busy():
        return "새 버전 설치가 진행 중입니다 — 끝난 뒤 다시 실행하세요"
    return None


def _to_home_if_open():
    """PalletizOS 가 다른 화면(IO·Settings 등)에 열려 있으면 Home 으로. 환경 점검이 Home 문구로 언어를 확인하므로
    다른 화면이면 'UI 언어가 English 가 아님'으로 전부 환경 오류가 됨 (2026-11-02 10:02 첫 실행)."""
    try:
        from autotest import env
        from autotest.ui import UI
        if not env.app_running():
            return
        ui = UI()
        w = ui.wrapper()
        names = lambda: {e.window_text() for e in w.descendants() if e.element_info.rectangle.width() > 0}  # noqa: E731
        # 열린 계정 메뉴·팝업 닫기 (11-02 10:54: 계정 메뉴가 열린 채 Settings 전체화면 → 환경 준비가 PalletizOS 를 못 찾음)
        if "Change Account" in names():
            acct = next((b for b in w.descendants(control_type="Button") if len(b.window_text() or "") == 1
                         and b.rectangle().top < w.rectangle().top + 150), None)
            if acct is not None:
                ui.click(acct, settle=1.5, label="계정 메뉴 닫기")
        if "Unsaved Changes" in names():
            ui.click(next(b for b in w.descendants(control_type="Button") if b.window_text() == "Discard & Exit"), settle=2.5)
        try:
            on_home = ui.on_home()
        except Exception:  # noqa: BLE001  Settings 전체화면이면 root() 가 없음
            on_home = False
        if not on_home:
            left = w.rectangle().left
            rail = sorted([b for b in w.descendants(control_type="Button")
                           if not b.window_text() and b.rectangle().left - left < 40 and b.rectangle().width() > 0
                           and b.rectangle().top < w.rectangle().top + 650], key=lambda b: b.rectangle().top)
            if rail:  # 왼쪽 메뉴 맨 위(계정 버튼 다음) = Home
                ui.click(rail[0], settle=2.5, label="Home")
                if "Unsaved Changes" in names():
                    ui.click(next(b for b in w.descendants(control_type="Button") if b.window_text() == "Discard & Exit"), settle=2.5)
            print("PalletizOS 를 Home 화면으로 돌림")
    except Exception as e:  # noqa: BLE001  못 돌려도 실행기의 환경 준비가 다시 시도함
        print(f"Home 으로 돌리지 못함 ({type(e).__name__}) — 환경 준비에서 다시 시도")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook", nargs="?", default=str(DEFAULT_WB))
    ap.add_argument("--dry", action="store_true", help="매칭 결과만 출력")
    ap.add_argument("--no-open", action="store_true", help="끝나고 결과 엑셀을 열지 않음")
    ap.add_argument("--keys", help="이 루틴만 실행 (쉼표로 구분, 예: TIO_04,TIO_07) — 나머지 행은 NT")
    a = ap.parse_args()
    wb = Path(a.workbook).resolve()
    if not wb.exists():
        sys.exit(f"엑셀 파일이 없음: {wb}")
    rows = plan(wb)
    if a.keys:
        keep = set(a.keys.split(","))
        for x in rows:
            if x["check"] and x["check"] not in keep:
                x["check"] = None
    used = [c for c in CHECKS if any(x["check"] == c["key"] for x in rows)]
    print("=" * 60)
    print(f" TC 자동 평가 · {wb.name}")
    print(f" 행 {len(rows)}개 중 자동 판정 {sum(1 for x in rows if x['check'])}개 · 점검 루틴 {len(used)}개")
    print("=" * 60)
    for x in rows:
        print(f"  {str(x['no']):>4}  {(x['check'] or '— 수동'):<18} {x['title'][-60:]}")
    if a.dry:
        return 0
    if not used:
        sys.exit("자동으로 판정할 수 있는 행이 없습니다.")
    why = _busy()
    if why:
        sys.exit(why)

    _to_home_if_open()
    import run_smoke as rs  # 기존 스모크 엔진 (파일은 그대로, 점검 목록만 바꿔 씀)
    flows, key2tc = [], {}
    for i, c in enumerate(used, 1):
        tc = f"T{i:02d}"
        key2tc[c["key"]] = tc
        flows.append({"tc": tc, "title": c["title"], "desc": c["desc"], "fn": c["fn"], "admin": c["admin"]})
        rs.SHORT[tc] = SHORT.get(c["key"], c["title"][:8])
    import autotest.report as report
    report.TITLE, report.PAGE_TITLE = "PalletizOS Test Case 실행 결과", "PalletizOS Test Case"
    rs.FLOWS = flows
    import tc_autotest.fginput as fginput
    fginput.HIDE_OVERLAY = rs.LIVE.hide
    os.environ["SMOKE_NO_FOCUS_GUARD"] = "1"  # 숫자 입력·드롭다운은 앱을 잠깐 앞으로 가져옴 (fginput.Foreground 가 되돌림)
    rs.RESULTS = ROOT / "results" / "tc"
    rs.HISTORY = rs.RESULTS / "history.json"
    rs.RESULTS.mkdir(parents=True, exist_ok=True)

    # ■ 종료해도 데일리 감시기의 '사용자 종료 버전' 기록은 바꾸지 않는다 (TC 평가 종료 ≠ 스모크 종료)
    us = ROOT / "results" / "user_stop.json"
    us_before = us.read_text(encoding="utf-8") if us.exists() else None
    before = {d.name for d in rs.RESULTS.glob("20*")}
    sys.argv = ["tc_run.py", "--no-update-check", "--no-open"]
    try:
        rs.main()
    finally:
        if us_before is None:
            us.unlink(missing_ok=True)
        else:
            us.write_text(us_before, encoding="utf-8")

    new = sorted(d for d in rs.RESULTS.glob("20*") if d.name not in before and (d / "result.json").exists())
    if not new:
        sys.exit("결과 폴더를 찾지 못함 — 실행이 시작 전에 멈췄을 수 있습니다 (results\\events.log 확인)")
    outdir = new[-1]
    run = json.loads((outdir / "result.json").read_text(encoding="utf-8"))
    res = {r["tc"]: r for r in run.get("results", [])}
    for x in rows:
        if x["check"]:
            r = res.get(key2tc[x["check"]], {})
            x["status"] = r.get("status", "env")
            msg = r.get("msg") or {"pass": "통과", "fail": "실패"}.get(x["status"], "판정 못 함")
            if x["status"] in ("pass", "warn", "flaky") and msg.startswith("[부분]"):
                # 자동으로 확인한 단계는 모두 통과, 눈으로 볼 기대(3D 색·질감 등)만 남음 → Result 는 NT, 근거에 명시
                x["status"], msg = "partial", "자동 부분 통과 — " + msg[len("[부분]"):].strip()
            d = next((t.get("diag") for t in reversed(r.get("attempts", [])) if t.get("diag")), None)
            x["msg"] = msg + (f" · 원인 추정: {d['label']} ({d['nature']} 요인)" if d and x["status"] in ("fail", "env") else "") \
                + f" · 루틴 {x['check']}"
        else:
            x["status"], x["msg"] = "na", nt_reason(x["text"])
    dest = write_results(wb, rows, dest_dir=wb.parent)
    try:
        import shutil
        shutil.copy2(dest, outdir / dest.name)
    except OSError:
        pass
    cnt = {}
    for x in rows:
        k = {"pass": "Pass", "warn": "Pass", "flaky": "Pass", "fail": "Fail", "partial": "부분(NT)"}.get(x["status"], "NT")
        cnt[k] = cnt.get(k, 0) + 1
    summary = {"workbook": str(wb), "result_workbook": str(dest), "result_dir": outdir.name, "counts": cnt,
               "rows": [{k: x.get(k) for k in ("sheet", "row", "no", "title", "check", "status", "msg")} for x in rows]}
    (outdir / "tc_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    print(f"판정 기록 완료: Pass {cnt.get('Pass', 0)} · Fail {cnt.get('Fail', 0)} · 부분 자동(NT) {cnt.get('부분(NT)', 0)} · NT {cnt.get('NT', 0)}")
    print(f"결과 엑셀: {dest}")
    if not a.no_open:
        try:
            os.startfile(dest)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
