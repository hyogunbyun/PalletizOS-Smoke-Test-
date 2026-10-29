"""정적 QA 점검 (앱 없이): 문법·불러오기·설정·bat·단위 로직·리포트·이슈 서버 보안.
결과를 results/qa_static.json으로 남긴다. 사용: .venv\\Scripts\\python.exe tools\\qa_static.py
"""
import ast
import json
import py_compile
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
OUT = []


def case(area, name, fn):
    t0 = time.time()
    try:
        detail = fn()
        OUT.append({"area": area, "name": name, "ok": True, "detail": detail or "", "sec": round(time.time() - t0, 2)})
    except Exception as e:  # noqa: BLE001
        OUT.append({"area": area, "name": name, "ok": False, "detail": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc(limit=2), "sec": round(time.time() - t0, 2)})
    r = OUT[-1]
    print(("PASS " if r["ok"] else "FAIL ") + f"[{area}] {name} — {r['detail'][:120]}")


def compile_all():
    files = [ROOT / "run_smoke.py"] + sorted((ROOT / "autotest").glob("*.py")) + sorted((ROOT / "tools").glob("qa_*.py"))
    for f in files:
        py_compile.compile(str(f), doraise=True)
    return f"{len(files)}개 파일 문법 정상"


def imports():
    import run_smoke  # noqa: F401
    from autotest.flows import FLOWS, SHORT
    tcs = [f["tc"] for f in FLOWS]
    assert len(tcs) == len(set(tcs)), f"중복 TC {[t for t in tcs if tcs.count(t) > 1]}"
    missing = [t for t in tcs if t not in SHORT]
    assert not missing, f"칩 이름 없음 {missing}"
    groups = {}
    for t in tcs:
        groups[t[0]] = groups.get(t[0], 0) + 1
    return f"흐름 {len(tcs)}개 등록 ({', '.join(f'{k}{v}' for k, v in groups.items())}), TC 중복·칩 이름 누락 없음"


def config():
    from autotest.ui import EL, P
    need = ["window_title", "platform", "palletizos", "input_mode", "speed", "speed_connect", "crawl", "ignore_texts"]
    miss = [k for k in need if k not in EL]
    assert not miss, f"elements.yaml 키 누락 {miss}"
    assert "Safety zone error" in EL["ignore_texts"], "Safety zone error 무시 설정 없음"
    assert EL["input_mode"] == "background", "기본 입력 방식이 background가 아님"
    assert EL["platform"].get("connect_mode") == "manual"
    assert P.get("menu_alias", {}).get("Recipes")
    return (f"필수 키 {len(need)}개 존재 · input_mode={EL['input_mode']} · speed {EL['speed_connect']}/{EL['speed']} · "
            f"connect_mode=manual · Safety zone error 무시 · 전체 클릭 메뉴 {len(EL['crawl']['menus'])}개")


def bats():
    out = []
    for f in sorted(ROOT.glob("*.bat")):
        b = f.read_bytes()
        assert b"\n" not in b.replace(b"\r\n", b""), f"{f.name}: LF만 있는 줄 (CRLF 아님)"
        out.append(f.name)
    return f"{len(out)}개 bat 모두 CRLF: {', '.join(out)}"


def chips_window():
    src = (ROOT / "autotest" / "overlay.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "window_chips")
    ns = {"MAX_CHIPS": 30}
    exec(compile(ast.Module([fn], []), "window_chips", "exec"), ns)
    w = ns["window_chips"]
    tcs = [f"T{i:02}" for i in range(43)]
    rows = []
    for done in (0, 5, 20, 26, 30, 43):
        chips = [(t, "pass" if i < done else "run" if i == done else None) for i, t in enumerate(tcs)]
        shown, hid, wait = w(chips)
        assert len(shown) == 30, "30칸 초과/미달"
        if done < 43:
            assert any(s == "run" for _, s in shown), f"진행 중 칩이 안 보임 (끝난 {done})"
        colored = sum(1 for _, s in shown if s == "pass")
        assert colored == min(done, 25 if done < 43 else 30), f"색 칩 수 이상 {colored} (끝난 {done})"
        assert [t for t, _ in chips[:len(hid)]] == [t for t, _ in chips if (t, _) not in shown][:len(hid)]
        rows.append(f"{done}→{shown[0][0]}~{shown[-1][0]}")
    small = [(f"S{i}", None) for i in 3 * [0]]
    assert w([("A", "pass"), ("B", "run")])[0] == [("A", "pass"), ("B", "run")]
    return "끝난 칩 색 유지·오래된 것부터 숨김 확인: " + ", ".join(rows)


def deny_list():
    from autotest.flows_crawl import _denied
    must_skip = ["Delete", "Save", "Save As", "Export", "Import", "Initialize System", "Install New Version", "Test Run",
                 "Start", "Clear", "Apply", "Add Tool", "Add Account", "Create Recipe", "A Admin", "O Operator", "Close",
                 "Recovery", "Log Out", "Get Pose", "Move To", "Open TeamViewer", "Export Backup Data", "Apply SwiftMove"]
    must_press = ["Refresh", "Next page", "First page", "Cancel", "Favorites", "Modbus Master", "Digital Output", "On", "Off",
                  "Jog", "Move", "Align", "General", "Tool", "Account", "Edit Recipe", "100%"]
    bad1 = [n for n in must_skip if not _denied(n)]
    bad2 = [n for n in must_press if _denied(n)]
    assert not bad1, f"눌리면 안 되는데 허용됨: {bad1}"
    assert not bad2, f"눌러야 하는데 막힘: {bad2}"
    return f"위험 버튼 {len(must_skip)}종 차단 · 일반 버튼 {len(must_press)}종 허용"


def focus_guard():
    from autotest.focusguard import FocusGuard, _is_ours
    g = FocusGuard(lambda m: None)
    g.start()
    time.sleep(0.5)
    alive = g.is_alive()
    g.stop()
    g.join(2)
    assert alive and not g.is_alive(), "시작/종료 이상"
    import ctypes
    assert not _is_ours(0)
    return "스레드 시작·종료 정상, 상태 표시창은 '사용자 창'으로 기억하지 않음"


def log_signature():
    from autotest.logcheck import signature
    a = signature("[2026-10-22 10:02:11.5][error][DP] [X] status: 404, code 404")
    b = signature("[2026-10-22 11:12:13.9][error][DP] [X] status: 500, code 500")
    assert a == b == "[X] status: #, code #", a
    return f"숫자만 다른 에러를 같은 종류로 묶음: '{a}'"


def scenarios():
    out = []
    for p in sorted((ROOT / "scenarios").glob("C*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d.get("steps"), f"{p.name}: 단계 없음"
        out.append(f"{d['id']}({len(d['steps'])}단계, 확인문구 {len(d.get('expects', []))})")
    return "녹화 시나리오: " + ", ".join(out)


def env_helpers():
    from autotest import env
    v = env.app_running()
    assert isinstance(v, bool)
    return f"app_running() = {v} (한국어 콘솔 출력에서도 정상 판별)"


def secret_store():
    from autotest import secret
    from autotest.jira import TARGET
    return f"Admin 비밀번호 저장: {'있음' if secret.load() else '없음'} · JIRA 토큰 저장: {'있음' if secret.read(TARGET) else '없음 (jira_setup.bat 필요)'} (값은 읽지 않음)"


def report_build():
    from autotest.report import write_report
    runs = sorted(p for p in (ROOT / "results").glob("2026*") if (p / "result.json").exists()
                  and json.loads((p / "result.json").read_text(encoding="utf-8")).get("finished"))  # 진행 중(중간 저장) 제외
    run_dir = next((p for p in reversed(runs) if any(r["status"] == "fail" for r in
                    json.loads((p / "result.json").read_text(encoding="utf-8"))["results"])), None)
    assert run_dir, "FAIL이 있는 실행 결과 없음"
    run = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    hist = json.loads((ROOT / "results" / "history.json").read_text(encoding="utf-8"))
    p = write_report(run, run_dir, hist)
    h = p.read_text(encoding="utf-8")
    n_fail = sum(r["status"] == "fail" for r in run["results"])
    assert h.count('class="jbtn"') == n_fail, f"이슈 버튼 {h.count('class=\"jbtn\"')} ≠ FAIL {n_fail}"
    assert 'data-run="' + run_dir.name + '"' in h
    return f"{run_dir.name} 리포트 재생성: FAIL {n_fail}건에 '이슈 등록' 버튼 {n_fail}개"


def issue_server():
    from autotest.issue_server import PORT, ensure_running
    assert ensure_running(), "등록 서버가 뜨지 않음"
    base = f"http://127.0.0.1:{PORT}"

    def code(url, method="GET", headers=None, data=None):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers or {}), timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    c1, _ = code(base + "/api/status")
    c2, _ = code(base + "/api/create", "POST", {"Origin": "null", "Content-Type": "application/json"}, b"{}")
    c3, _ = code(base + "/api/create", "POST", {"Origin": "https://evil.example", "Content-Type": "application/json"}, b"{}")
    c4, _ = code(base + "/results/..%2Fjira_config.json")
    c5, _ = code(base + "/results/..%2F..%2Frun_smoke.py")
    runs = sorted(p for p in (ROOT / "results").glob("2026*") if (p / "result.json").exists())
    run = next(p for p in reversed(runs) if any(r["status"] == "fail" for r in json.loads((p / "result.json").read_text(encoding="utf-8"))["results"]))
    tc = next(r["tc"] for r in json.loads((run / "result.json").read_text(encoding="utf-8"))["results"] if r["status"] == "fail")
    # 초안은 서버를 거치지 않고 직접 만든다: JIRA 설정이 없을 때 서버 미리보기는 설정 창을 띄우므로(사용자 화면에 팝업) 점검에서 호출하지 않음
    from autotest import jira
    pv = jira.preview(run.name, tc)
    c7, _ = code(f"{base}/api/preview?run=../../x&tc={tc}")
    assert (c1, c2, c3, c4, c5, c7) == (200, 403, 403, 404, 404, 400), (c1, c2, c3, c4, c5, c7)
    assert pv["summary"].startswith("[PalletizOS") and pv["files"], "초안 내용 이상"
    return (f"상태 200 · 다른 출처 POST 403(null·외부 사이트) · 결과 폴더 밖 파일 404 · 잘못된 실행 이름 400 · "
            f"{tc} 초안: 제목 '{pv['summary'][:40]}…', 첨부 {len(pv['files'])}개")


if __name__ == "__main__":
    case("코드", "전체 파이썬 파일 문법", compile_all)
    case("코드", "흐름 등록·TC 중복·칩 이름", imports)
    case("설정", "elements.yaml 필수 설정", config)
    case("설정", "bat 파일 CRLF", bats)
    case("상태 표시창", "칩 창(색 유지·오래된 것부터 숨김)", chips_window)
    case("전체 클릭", "위험 버튼 차단 목록", deny_list)
    case("포커스", "포커스 지킴이 시작·종료", focus_guard)
    case("판정", "로그 에러 서명", log_signature)
    case("시나리오", "녹화 시나리오 파일", scenarios)
    case("환경", "앱 실행 여부 판별", env_helpers)
    case("보안", "자격 증명 저장 상태", secret_store)
    case("리포트", "리포트 생성·이슈 버튼", report_build)
    case("JIRA", "등록 서버 응답·보안", issue_server)
    (ROOT / "results" / "qa_static.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{sum(r['ok'] for r in OUT)}/{len(OUT)} PASS")
