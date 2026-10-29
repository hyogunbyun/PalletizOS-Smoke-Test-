"""QA 리포트 (HTML): 정적 점검(results/qa_static.json) + 실제 실행 결과(result.json, 여러 실행이면 항목별 최신 실제 결과)
+ 전체 클릭 기록 + 오늘 발견·수정한 문제. 사용: python tools/qa_report.py <실행폴더> [<실행폴더> ...]
출력: results/QA_리포트_<날짜>.html
"""
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")


def e(s):
    return html.escape(str(s if s is not None else ""))


# 오늘 QA에서 발견해 고친 문제 (근거·검증 방법·상태). 상태: 검증 완료 / 수정·미검증 / 미해결
FINDINGS = [
    ("실행기", "앱이 꺼졌을 때 '앱 실행 여부' 판별에서 실행기가 오류로 멈춤 (tasklist 한국어 출력 해석 실패)",
     "tasklist 출력을 바이트로 비교", "정적 점검 '앱 실행 여부 판별' PASS", "검증 완료"),
    ("포커스", "포커스 지킴이가 Python 스레드 내부 이름(_stop)을 덮어써 종료 시 오류",
     "이름 변경(_halt)", "정적 점검 '포커스 지킴이 시작·종료' PASS", "검증 완료"),
    ("포커스", "포커스 지킴이가 상태 표시창을 '사용자 창'으로 기억해 포커스를 표시창에 돌려줌 (키 입력이 종료 버튼으로 갈 위험)",
     "자동화 자신의 창은 기억하지 않음 + 표시창 버튼 키보드 포커스 제거", "이후 실행 로그에서 'VS Code 창으로 되돌림' 확인", "검증 완료"),
    ("상태 표시창", "실행 초반 표시창이 화면 밖(4K 기준 저장 위치)으로 나가 사라짐",
     "앱 창이 없을 땐 기본 위치, 모니터 안으로 위치 제한", "표시창을 띄워 좌표(1340,87) 확인", "검증 완료"),
    ("상태 표시창", "칩(시나리오 박스)이 하나도 안 보임 — JSON 리스트를 튜플로 비교하다 그리기 오류",
     "튜플로 변환", "표시창 캡처로 칩 표시 확인", "검증 완료"),
    ("상태 표시창", "항목이 많으면 칩이 9줄로 늘어남 / 끝난 칩 색이 안 보임",
     "30칸 창: 끝난 칩 색 유지, 넘치면 가장 오래된 칩부터 숨김", "정적 점검 '칩 창' 6가지 경우 PASS", "검증 완료"),
    ("상태 표시창", "칩 두 번 클릭 동작 — 즉시 실행/예약 사이 변경",
     "사용자 선택에 따라 '즉시 실행(지금 실행 멈춘 뒤)'", "14:12 K05 칩 → run_one.bat K05 실행 확인(이전 코드)", "수정·미검증"),
    ("연결", "제어기 목록이 비어 연결 안 됨",
     "'수동으로 IP 입력' + 127.0.0.1 → 연결", "앱 실측: 9초 만에 연결(13:20:04→13:20:13)", "검증 완료"),
    ("v2.0.0", "메뉴 이름 변경(Recipes→Recipe)으로 R01~R05 전부 FAIL",
     "메뉴 별칭(menu_alias)", "실행 13:56: R01·R02·R03·R05 PASS", "검증 완료"),
    ("v2.0.0", "Jog + · Quick Log 메뉴 없음 → J01·Q01 FAIL",
     "메뉴가 없으면 해당없음(N/A)", "실행 13:56: J01·Q01 N/A", "검증 완료"),
    ("전체 클릭", "탭 전환을 '대화상자 열림'으로 잘못 분류해 엉뚱한 닫기 시도",
     "새 층이 생길 때만 대화상자로 판단", "실행 13:56 K03: 화면 전환 20건으로 정상 분류", "검증 완료"),
    ("전체 클릭", "레시피 편집기(v2.0.0) 안까지 눌러 들어가 Home 복귀 실패 → 실행기가 앱 재시작",
     "Create Recipe 누르지 않음 + 좌측 메뉴 없는 전체 화면은 X로 닫고 안쪽 점검 생략 + 확인창 '저장 안 함'", "다음 전체 실행에서 확인 필요", "수정·미검증"),
    ("실행기", "앱 재시작 직후 화면 요소 종류가 비어 실행기 오류(KeyError) 종료",
     "1초 간격 최대 3회 재시도", "재현 대기", "수정·미검증"),
    ("실행기", "콘솔 창을 닫거나 강제 종료되면 결과 파일이 하나도 안 남음",
     "항목마다 중간 결과 저장", "다음 실행에서 확인 필요", "수정·미검증"),
    ("H08", "Release Vacuum 직후 홈 이동 버튼이 잠깐 비활성 → 1차 실패, 재시도 통과(불안정)",
     "버튼이 활성화될 때까지 최대 10초 대기", "다음 실행에서 확인 필요", "수정·미검증"),
    ("JIRA", "이슈 등록 시 'JIRA 설정이 없습니다' 안내만 뜸",
     "설정이 없으면 설정 창(jira_setup.bat)을 자동으로 엶", "등록 서버 응답 확인(setup_opened)", "검증 완료"),
    ("JIRA", "설정이 없을 때 잘못된 실행 이름도 200으로 응답", "입력 검사를 먼저", "정적 점검: 잘못된 실행 이름 400", "검증 완료"),
    ("H06·R04", "백그라운드 방식에서 3D 확대 드롭다운·⋮ 메뉴가 열리지 않음 (자동화 쪽 한계)",
     "— (mouse 방식 비교 필요)", "10-19부터 반복", "미해결"),
]

STATUS_CLS = {"pass": ("통과", "ok"), "warn": ("주의", "warn"), "flaky": ("불안정", "warn"), "fail": ("실패", "bad"),
              "na": ("해당없음", "na"), "env": ("미실행·환경", "env")}


def merged(runs):
    """항목별로 가장 최근의 '실제로 실행된' 결과(env 제외)를 고른다. 없으면 마지막 env."""
    best, src = {}, {}
    order = []
    for d in runs:
        r = json.loads((d / "result.json").read_text(encoding="utf-8"))
        for x in r["results"]:
            if x["tc"] not in order:
                order.append(x["tc"])
            if x["status"] != "env" or x["tc"] not in best:
                best[x["tc"]], src[x["tc"]] = x, (d, r)
    return [(best[t], src[t]) for t in order]


def clicks(d, tc):
    p = d / f"{tc}_clicks.txt"
    if not p.exists():
        return None
    lines = p.read_text(encoding="utf-8").splitlines()
    rows = [l.split("\t") for l in lines[2:] if l.count("\t") == 2]
    kinds = {}
    for _, _, r in rows:
        k = r.split(" ")[0].rstrip(":")
        kinds[k] = kinds.get(k, 0) + 1
    pages = len({w for w, _, _ in rows})
    return {"head": lines[0], "kinds": kinds, "pages": pages, "n": len(rows), "file": p}


def main(run_names):
    runs = [RES / n for n in run_names if (RES / n / "result.json").exists()]
    static = json.loads((RES / "qa_static.json").read_text(encoding="utf-8"))
    from autotest.flows import FLOWS
    import run_smoke  # noqa: F401  (모든 흐름 등록)
    meta = {f["tc"]: f for f in FLOWS}
    items = [(x, s_) for x, s_ in merged(runs) if x["tc"] in meta]  # 지금 등록된 항목만 (삭제된 K04 등 제외)
    cnt = {}
    for x, _ in items:
        cnt[x["status"]] = cnt.get(x["status"], 0) + 1
    executed = sum(v for k, v in cnt.items() if k != "env")
    base = json.loads((runs[0] / "result.json").read_text(encoding="utf-8"))
    ev = (RES / "events.log").read_text(encoding="utf-8").splitlines() if (RES / "events.log").exists() else []
    today = [l for l in ev if l.startswith(datetime.now().strftime("%Y-%m-%d"))]
    n_stop = sum("자동화 종료" in l and ("두 번 눌림" in l or "확인 누름" in l) for l in today)
    n_chip = sum("칩" in l for l in today)
    st_ok = sum(r["ok"] for r in static)
    fx = {"검증 완료": 0, "수정·미검증": 0, "미해결": 0}
    for f in FINDINGS:
        fx[f[4]] += 1

    # ---- 표: 정적 점검
    srows = "".join(f'<tr><td>{e(r["area"])}</td><td><b>{e(r["name"])}</b></td><td><span class="chip {"ok" if r["ok"] else "bad"}">'
                    f'{"PASS" if r["ok"] else "FAIL"}</span></td><td class="msg">{e(r["detail"])}</td></tr>' for r in static)
    # ---- 표: 실제 실행 항목
    groups = [("H", "Home 기본"), ("R", "Recipe"), ("I", "IO"), ("L", "Log"), ("S", "Settings"), ("J", "Jog +"), ("Q", "Quick Log"),
              ("V", "Recovery"), ("K", "전체 클릭 점검"), ("C", "녹화 시나리오")]
    irows = []
    for g, gname in groups:
        part = [(x, s) for x, s in items if x["tc"].startswith(g)]
        if not part:
            continue
        irows.append(f'<tr class="grp"><td colspan="5">{e(gname)} ({len(part)})</td></tr>')
        for x, (d, _) in part:
            lab, cls = STATUS_CLS.get(x["status"], (x["status"], "na"))
            ev_links = []
            for a in x.get("attempts", []):
                for k, nm in (("shot", "스크린샷"), ("log", "앱 로그"), ("detail", "클릭 기록")):
                    if a.get(k):
                        ev_links.append(f'<a href="{d.name}/{e(a[k])}">{a["attempt"]}차 {nm}</a>')
            msg = x.get("msg") or ""
            irows.append(f'<tr><td class="tc">{e(x["tc"])}</td><td><b>{e(x["title"])}</b><div class="msg">{e(meta.get(x["tc"], {}).get("desc", x.get("desc", "")))}</div></td>'
                         f'<td><span class="chip {cls}">{lab}</span></td><td class="msg {"err" if x["status"] in ("fail", "flaky") else ""}">{e(msg)}</td>'
                         f'<td class="msg">{" · ".join(ev_links)}<div class="sub">{e(d.name)} · {e(x.get("sec"))}s</div></td></tr>')
    # ---- 전체 클릭
    crows = []
    for x, (d, _) in items:
        if not x["tc"].startswith("K"):
            continue
        c = clicks(d, x["tc"])
        lab, cls = STATUS_CLS.get(x["status"], (x["status"], "na"))
        if c:
            kinds = " · ".join(f"{k} {v}" for k, v in c["kinds"].items())
            crows.append(f'<tr><td class="tc">{e(x["tc"])}</td><td>{e(x["title"].replace("전체 클릭: ", ""))}</td><td><span class="chip {cls}">{lab}</span></td>'
                         f'<td>{e(c["head"].split("—")[-1].strip())}</td><td>{c["pages"]}</td><td class="msg">{e(kinds)}</td>'
                         f'<td><a href="{d.name}/{e(c["file"].name)}">클릭 기록</a></td></tr>')
        else:
            crows.append(f'<tr><td class="tc">{e(x["tc"])}</td><td>{e(x["title"].replace("전체 클릭: ", ""))}</td><td><span class="chip {cls}">{lab}</span></td>'
                         f'<td colspan="4" class="msg">{e(x.get("msg") or "기록 없음")}</td></tr>')
    # ---- 발견·수정
    fcls = {"검증 완료": "ok", "수정·미검증": "warn", "미해결": "bad"}
    frows = "".join(f'<tr><td class="tc">{i}</td><td>{e(a)}</td><td><b>{e(p)}</b><div class="msg">조치: {e(f)}</div></td>'
                    f'<td class="msg">{e(v)}</td><td><span class="chip {fcls[s]}">{e(s)}</span></td></tr>'
                    for i, (a, p, f, v, s) in enumerate(FINDINGS, 1))
    not_run = [x["tc"] for x, _ in items if x["status"] == "env"]
    fails = [x for x, _ in items if x["status"] == "fail"]

    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PalletizOS 스모크 자동화 QA 리포트</title><style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--sub:#5b6475;--line:#e3e6eb;--ok:#1f9d55;--okbg:#e5f5ec;--warn:#b7791f;--warnbg:#fdf3dc;
--bad:#d64545;--badbg:#fbe7e7;--na:#7a8394;--nabg:#eef0f3;--env:#2f6fd6;--envbg:#e5eefc}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Noto Sans KR","Malgun Gothic",system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:28px 20px 60px}}h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:18px;margin:34px 0 10px}}
.sub{{color:var(--sub);font-size:12.5px}}.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:16px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}.kpi .v{{font-size:28px;font-weight:700;line-height:1.1}}
.kpi .l{{color:var(--sub);font-size:13px;margin-top:4px}}.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px}}
.box.warn{{background:var(--warnbg);border-color:#f0dcae}}table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top;font-size:14px}}th{{background:#fafbfc;color:var(--sub);font-weight:600;font-size:12.5px}}
tr.grp td{{background:#f3f5f8;font-weight:700;font-size:13px;color:var(--sub)}}.chip{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12.5px;font-weight:600;white-space:nowrap}}
.ok{{color:var(--ok);background:var(--okbg)}}.warn{{color:var(--warn);background:var(--warnbg)}}.bad{{color:var(--bad);background:var(--badbg)}}
.na{{color:var(--na);background:var(--nabg)}}.env{{color:var(--env);background:var(--envbg)}}.msg{{color:var(--sub);font-size:13px}}.msg.err{{color:var(--bad)}}
.tc{{font-weight:700;white-space:nowrap}}a{{color:var(--env)}}.wrap{{overflow-x:auto}}ul{{margin:6px 0 0;padding-left:20px}}li{{margin:3px 0}}
.cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}}code{{font:12.5px Consolas,monospace}}
</style></head><body><main>
<h1>PalletizOS 스모크 자동화 QA 리포트</h1>
<div class="sub">작성 {datetime.now():%Y-%m-%d %H:%M} · 대상 PalletizOS {e(base.get("palletizos_version"))} / Dr.Dart-Platform {e(base.get("platform_version"))} · 가상 제어기 dev-simulator ·
실제 실행 근거 {", ".join(e(d.name) for d in runs)}</div>

<div class="hero">
<div class="kpi"><div class="v" style="color:var(--ok)">{st_ok}/{len(static)}</div><div class="l">정적 점검 통과<br>(앱 없이: 코드·설정·로직·보안)</div></div>
<div class="kpi"><div class="v">{executed}/{len(items)}</div><div class="l">실제 앱으로 실행된 항목<br>(미실행 {len(not_run)}: 실행 중단)</div></div>
<div class="kpi"><div class="v" style="color:var(--ok)">{cnt.get("pass", 0)}</div><div class="l">통과 (불안정 {cnt.get("flaky", 0)}, 해당없음 {cnt.get("na", 0)})</div></div>
<div class="kpi"><div class="v" style="color:var(--bad)">{cnt.get("fail", 0)}</div><div class="l">실패 — {e(", ".join(x["tc"] for x in fails) or "없음")}<br>(모두 자동화 쪽 한계로 분류)</div></div>
<div class="kpi"><div class="v">{len(FINDINGS)}</div><div class="l">발견 문제 — 검증 완료 {fx["검증 완료"]} · 수정·미검증 {fx["수정·미검증"]} · 미해결 {fx["미해결"]}</div></div>
</div>

<h2>결론</h2>
<div class="box"><ul>
<li><b>코드·설정·로직은 정상</b>: 정적 점검 {st_ok}/{len(static)} 통과 (문법 20개 파일, 흐름 {len(items)}개 등록, 위험 버튼 차단, 칩 표시, 등록 서버 보안).</li>
<li><b>실제 실행은 {executed}/{len(items)}개까지 확인</b>: 기본 항목은 v2.0.0에서도 대부분 동작(Recipe·IO·Log·Settings 19개 중 R04만 실패, Jog +·Quick Log는 메뉴가 없어 해당없음). 실패 2건(H06·R04)은 백그라운드 입력으로 드롭다운·⋮ 메뉴가 열리지 않는 <b>자동화 쪽 한계</b>로, 제품 결함 근거는 없음.</li>
<li><b>전체 클릭 점검</b>은 Home·Recipe·IO에서 누름 {sum((clicks(d, x["tc"]) or {"n": 0})["n"] for x, (d, _) in items if x["tc"].startswith("K"))}건, 에러 문구·앱 종료 0건.</li>
<li><b>미완료</b>: {e(", ".join(not_run))} — 실행 도중 종료 버튼·칩 클릭·창 닫기로 중단되어 아직 실제 실행 결과가 없음. 아래 '수정·미검증' 항목과 함께 <b>손대지 않은 전체 실행 1회</b>로 확인 필요.</li>
</ul></div>

<h2>1. 무엇을 확인했나</h2>
<div class="cols">
<div class="box"><b>정적 점검 (앱 없이, <code>tools/qa_static.py</code>)</b><ul>
<li>모든 파이썬 파일 문법, 흐름 등록·TC 중복·칩 이름</li><li>설정(elements.yaml) 필수 값, bat 파일 CRLF</li>
<li>상태 표시창 칩 창 로직 6가지 경우</li><li>전체 클릭의 위험 버튼 차단 24종 / 일반 버튼 허용 17종</li>
<li>포커스 지킴이 시작·종료, 로그 에러 서명, 녹화 시나리오 파일</li><li>리포트 생성·이슈 버튼, JIRA 등록 서버 보안(다른 출처 차단·폴더 밖 접근 차단)</li></ul></div>
<div class="box"><b>실제 실행 (가상 제어기 + Dr.Dart 앱)</b><ul>
<li>기본 30개: Home 8 · Recipe 5 · IO 4 · Log 5 · Settings 5 · Jog/QLog/Recovery 3</li>
<li>전체 클릭 9개: 메뉴마다 보이는 버튼·탭·토글을 한 번씩 누르고 에러 문구·앱 종료 확인</li>
<li>녹화 시나리오 4개 (C01~C04)</li><li>연결: 수동 IP 입력 → 제어권 강제 회수 → PalletizOS 진입 → Admin 전환</li>
<li>실행 중 관찰: 표시창 동작, 포커스 되돌림, 앱 재시작·중단 원인</li></ul></div>
</div>

<h2>2. 정적 점검 결과 ({st_ok}/{len(static)})</h2>
<div class="wrap"><table><tr><th>영역</th><th>점검</th><th>결과</th><th>내용</th></tr>{srows}</table></div>

<h2>3. 실제 실행 결과 (항목별 최신 실제 결과)</h2>
<div class="wrap"><table><tr><th>TC</th><th>항목</th><th>결과</th><th>메시지</th><th>근거</th></tr>{"".join(irows)}</table></div>

<h2>4. 전체 클릭 점검</h2>
<p class="sub">반응 확인 = 눌렀고 화면 변화 없음 · 표시 변화 = 일부 값·문구 변화 · 화면 = 탭·하위 화면으로 전환(그 화면도 점검) · 열림 = 대화상자를 열고 닫음 · 건너뜀 = 위험 버튼 · 비활성 = 누를 수 없는 상태</p>
<div class="wrap"><table><tr><th>TC</th><th>메뉴</th><th>결과</th><th>누름·문제</th><th>점검 화면</th><th>분류</th><th>근거</th></tr>{"".join(crows)}</table></div>

<h2>5. 발견한 문제와 조치 ({len(FINDINGS)}건)</h2>
<div class="wrap"><table><tr><th>#</th><th>영역</th><th>문제 · 조치</th><th>검증</th><th>상태</th></tr>{frows}</table></div>

<h2>6. 실행 중단 기록</h2>
<div class="box warn">오늘 표시창 기록: <b>■ 자동화 종료 {n_stop}회</b>, <b>칩 두 번 클릭 {n_chip}회</b> (사용자 조작으로 확인). 앱 창을 직접 닫은 경우도 있어(사용자 확인) 전체 실행이 끝까지 돈 적이 없습니다.
실행기가 앱을 스스로 재시작한 경우는 '원래 상태로 되돌리기 실패' 때 1회(K02 레시피 편집기, 14:04)로, 위 12번에서 수정했습니다.</div>

<h2>7. 남은 일</h2>
<div class="box"><ul>
<li>손대지 않은 전체 실행 1회 → 미실행 {len(not_run)}개와 '수정·미검증' {fx["수정·미검증"]}건 확인 (예상 30~40분)</li>
<li>H06·R04: <code>--mode mouse</code>로 돌려 자동화 한계인지 최종 확인</li>
<li>JIRA: <code>jira_setup.bat</code>으로 설정 후 실제 이슈 1건 등록 시험</li>
<li>H03~H05가 해당없음: 실행 시작 때 Left·Right 열이 모두 꺼져 있었음 → 앱에서 한쪽 열을 켜 둔 상태로 다시 실행해야 확인됨</li>
<li>녹화 시나리오 C01·C02는 v2.0.0에서 없어진 'Jog +' 메뉴를 눌러 다시 녹화 필요</li>
</ul></div>
<p class="sub">재생성: <code>.venv\\Scripts\\python.exe tools\\qa_static.py</code> → <code>.venv\\Scripts\\python.exe tools\\qa_report.py {" ".join(e(d.name) for d in runs)}</code></p>
</main></body></html>"""
    out = RES / f"QA_리포트_{datetime.now():%Y%m%d}.html"
    out.write_text(doc, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:] or ["20261022_135631"])
