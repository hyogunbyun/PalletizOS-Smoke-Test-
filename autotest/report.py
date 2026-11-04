"""스모크 결과 HTML 리포트 (단일 파일, 스크린샷은 같은 폴더의 PNG 참조)."""
import html
from pathlib import Path

LABEL = {"pass": ("통과", "ok"), "warn": ("주의·새 로그 에러", "warn"), "flaky": ("불안정·재시도 통과", "warn"),
         "fail": ("실패", "bad"), "na": ("해당없음", "na"), "env": ("환경 오류", "env"),
         "run": ("진행 중", "warn"), "wait": ("대기", "na"), "stopped": ("미실행", "na")}  # 중간 현황 리포트용 (run_smoke._partial_report)
LINK_NAME = {"shot": "스크린샷", "log": "앱 로그", "tree": "UI 트리", "detail": "클릭 기록"}
ISSUE_UI = Path(__file__).with_name("report_issue.html")  # FAIL 행 '이슈 등록' 버튼용 CSS·창·스크립트
VERDICT_CLS = {"통과": "ok", "통과(주의)": "warn", "보류": "bad", "재실행 필요": "env", "중단": "env", "진행 중": "warn"}

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--sub:#5b6475;--line:#e3e6eb;
--ok:#1f9d55;--okbg:#e5f5ec;--warn:#b7791f;--warnbg:#fdf3dc;--bad:#d64545;--badbg:#fbe7e7;
--na:#7a8394;--nabg:#eef0f3;--env:#2f6fd6;--envbg:#e5eefc}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 "Noto Sans KR","Malgun Gothic",system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}
.sub{color:var(--sub);font-size:13px}
.hero{display:flex;gap:18px;align-items:center;background:var(--card);border:1px solid var(--line);
border-radius:14px;padding:20px 22px;margin-top:16px;flex-wrap:wrap}
.badge{font-size:26px;font-weight:700;padding:10px 22px;border-radius:12px}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:6px 22px;flex:1;font-size:14px}
.meta b{display:block;color:var(--sub);font-weight:500;font-size:12px}
.notes{margin:12px 0 0;padding:10px 14px;background:var(--warnbg);border-radius:10px;color:#7a5410;font-size:14px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;font-size:14px}
th{background:#fafbfc;color:var(--sub);font-weight:600;font-size:12.5px}
tr:last-child td{border-bottom:0}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12.5px;font-weight:600;white-space:nowrap}
.ok{color:var(--ok);background:var(--okbg)}.warn{color:var(--warn);background:var(--warnbg)}
.bad{color:var(--bad);background:var(--badbg)}.na{color:var(--na);background:var(--nabg)}
.env{color:var(--env);background:var(--envbg)}
.msg{color:var(--sub);font-size:13px;margin-top:4px}.msg.err{color:var(--bad)}
code,pre{font:12.5px/1.45 Consolas,monospace}pre{white-space:pre-wrap;background:#f3f4f6;padding:8px 10px;border-radius:8px;margin:6px 0 0}
a{color:var(--env)}.tc{font-weight:700;white-space:nowrap}
.dot{display:inline-block;width:14px;height:14px;border-radius:4px;margin-right:3px;vertical-align:middle}
.dot.ok{background:var(--ok)}.dot.warn{background:#e0a21b}.dot.bad{background:var(--bad)}
.dot.na{background:#c5cad3}.dot.env{background:var(--env)}
details summary{cursor:pointer;color:var(--sub);font-size:13px}
.wrap{overflow-x:auto}
.diag{margin:8px 0 4px;border:1px solid var(--line);border-left:4px solid var(--bad);border-radius:8px;padding:8px 12px;background:#fffafa}
.diag.ext{border-left-color:var(--env);background:#f7faff}.diag.tool{border-left-color:var(--na);background:#fafbfc}
.diag h4{margin:0 0 4px;font-size:13.5px}.diag ul{margin:4px 0 4px 18px;padding:0;font-size:13px}
.diag .k{color:var(--sub);font-size:12px}.diag table{border:0;margin-top:4px}.diag td,.diag th{padding:3px 8px;font-size:12.5px}
"""


def _e(s):
    return html.escape(str(s if s is not None else ""))


# 리포트 제목 — TC 자동 평가(tc_run.py)가 바꿔 씀, 스모크는 그대로
TITLE = "PalletizOS Home 스모크 결과"
PAGE_TITLE = "PalletizOS 스모크"


NATURE_CLS = {"앱": "", "외부": "ext", "자동화": "tool"}
METRICS = [("app_procs", "앱 프로세스 수"), ("main_pid", "앱 본체 pid"), ("app_ws_mb", "앱 메모리 합계(MB)"),
           ("sys_load_pct", "PC 메모리 사용률(%)"), ("sys_avail_mb", "PC 남은 메모리(MB)"), ("sys_commit_avail_mb", "남은 커밋(MB)"),
           ("ctrl_docker", "Docker 응답"), ("ctrl_drcf_pid", "제어기 DRCF pid"), ("ctrl_listening", "제어기 포트 12345"),
           ("ctrl_crash_count", "제어기 누적 충돌(rc=139)"), ("pc_locked", "PC 잠김"), ("pc_idle_sec", "마지막 사용자 입력(초 전)"),
           ("pc_foreground", "맨 앞 창")]


def _diag_html(a):
    """시도 1건의 원인 추정 블록 (autotest/diag.py 결과)."""
    d = a.get("diag")
    if not d:
        return ""
    ev = "".join(f"<li><span class='k'>[{_e(x['nature'])}·{_e(x['label'])}]</span> {_e(x['text'])}</li>" for x in d["evidence"])
    b, f = d.get("before", {}), d.get("after", {})
    mt = "".join(f"<tr><td>{_e(n)}</td><td>{_e(b.get(k, ''))}</td><td>{_e(f.get(k, ''))}</td></tr>"
                 for k, n in METRICS if k in b or k in f)
    lg = d.get("log", {})
    groups = "".join(f"<tr><td>{g['count']}</td><td>{'기준 목록' if g['known'] else '<b>새 에러</b>'}</td><td><code>{_e(g['first'])}</code></td></tr>"
                     for g in lg.get("groups", []))
    evs = "".join(f"<li>{_e(e['time'])} · 이벤트 {_e(e['id'])} · {_e(e['msg'])}</li>" for e in d.get("events", []))
    dumps = "".join(f"<li>{_e(x)}</li>" for x in d.get("dumps", []))
    tail = "\n".join(lg.get("tail", []))
    return (f"<div class='diag {NATURE_CLS.get(d['nature'], '')}'><h4>시도 {a['attempt']} 실패 원인 추정: {_e(d['label'])} "
            f"<span class='k'>({_e(d['nature'])} 요인{' · 예외 ' + _e(d['exception']) if d.get('exception') else ''})</span></h4>"
            f"<div>{_e(d['cause'])}</div>"
            + (f"<ul>{ev}</ul>" if ev else "<div class='k'>뚜렷한 외부 이상 징후 없음 (앱·PC·제어기 정상)</div>")
            + f"<div class='k'>앱 로그(이 시도 구간): {lg.get('lines', 0)}줄 · 에러 {lg.get('errors', 0)} · 경고 {lg.get('warns', 0)}"
              f" · 기준 목록에 없는 새 에러 {lg.get('new_groups', 0)}종</div>"
            + "<details><summary>근거 데이터 (시작 vs 실패 시점 · 로그 · 이벤트)</summary>"
            + f"<table><tr><th>항목</th><th>시도 시작</th><th>실패 시점</th></tr>{mt}</table>"
            + (f"<table><tr><th>횟수</th><th>구분</th><th>에러 로그 (같은 종류는 첫 줄)</th></tr>{groups}</table>" if groups else "")
            + (f"<div class='k'>Windows 이벤트</div><ul>{evs}</ul>" if evs else "<div class='k'>Windows 이벤트: 앱 오류·응답 없음·메모리 부족 기록 없음</div>")
            + (f"<div class='k'>새 크래시 덤프</div><ul>{dumps}</ul>" if dumps else "")
            + (f"<div class='k'>실패 직전 앱 로그 마지막 {len(lg.get('tail', []))}줄</div><pre>{_e(tail)}</pre>" if tail else "")
            + (f"<div class='k'>예외 위치</div><pre>{_e(a.get('trace', ''))}</pre>" if a.get("trace") else "")
            + "</details></div>")


def write_report(run, outdir: Path, hist):
    v = run["verdict"]
    rows = []
    for r in run["results"]:
        lab, cls = LABEL.get(r["status"], (r["status"], "na"))
        extra = []
        if r.get("msg"):
            extra.append(f'<div class="msg {"err" if r["status"] in ("fail", "flaky") else ""}">{_e(r["msg"])}</div>')
        for a in r.get("attempts", []):
            links = " · ".join(f'<a href="{_e(a[k])}">{LINK_NAME[k]}</a>'
                               for k in ("shot", "log", "tree", "detail") if a.get(k))
            if links:
                extra.append(f'<div class="msg">시도 {a["attempt"]}: {links}</div>')
            if a.get("restore"):
                extra.append(f'<div class="msg err">{_e(a["restore"])}</div>')
            if r["status"] in ("fail", "flaky", "env") or a.get("status") in ("fail", "env"):
                extra.append(_diag_html(a))
        if r.get("new_errors"):
            items = "".join(f"<pre>{_e(line)}</pre>" for line in r["new_errors"].values())
            extra.append(f"<details><summary>새 로그 에러 {len(r['new_errors'])}종</summary>{items}</details>")
        btn = (f'<button class="jbtn" data-tc="{_e(r["tc"])}" onclick="openIssue(this.dataset.tc)">이슈 등록</button>'
               if r["status"] == "fail" else "")
        rows.append(f'<tr><td class="tc">{_e(r["tc"])}</td><td><b>{_e(r["title"])}</b>'
                    f'<div class="msg">{_e(r["desc"])}</div>{"".join(extra)}{btn}</td>'
                    f'<td><span class="chip {cls}">{lab}</span></td><td>{_e(r["sec"])}s</td></tr>')

    tcs = [r["tc"] for r in run["results"]]
    hrows = []
    for h in reversed(hist[-10:]):
        dots = "".join(f'<span class="dot {LABEL.get(h["flows"].get(t), ("", "na"))[1]}" title="{t}"></span>' for t in tcs)
        hrows.append(f'<tr><td>{_e(h["started"].replace("T", " "))}</td><td><span class="chip {VERDICT_CLS.get(h["verdict"], "na")}">'
                     f'{_e(h["verdict"])}</span></td><td>{_e(h.get("palletizos_version"))} / {_e(h.get("platform_version"))}</td>'
                     f'<td>{dots}</td></tr>')

    counts = {}
    for r in run["results"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = " · ".join(f"{LABEL[k][0].split('·')[0]} {n}" for k, n in counts.items() if k in LABEL)
    notes = "".join(f"<div>{_e(n)}</div>" for n in run.get("notes", []))
    restored = run.get("restored")
    rest = "확인" if restored else ("불일치: " + "; ".join(run.get("restore_diff", [])) if restored is False else "-")
    all_new = {}
    for r in run["results"]:
        all_new.update(r.get("new_errors", {}))
    newsec = ""
    if all_new:
        items = "".join(f"<tr><td><code>{_e(sig)}</code></td></tr>" for sig in all_new)
        newsec = (f"<h2>새 로그 에러 서명 {len(all_new)}종</h2><p class='sub'>정상 소음이면 "
                  f"<code>approve_errors.bat</code>을 실행해 기준 목록에 추가하세요.</p>"
                  f"<div class='wrap'><table><tr><th>서명 (숫자는 #)</th></tr>{items}</table></div>")

    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{PAGE_TITLE}</title>
{'<meta http-equiv="refresh" content="30">' if v == "진행 중" else ""}
<style>{CSS}</style></head><body data-run="{_e(outdir.name)}"><main>
<h1>{TITLE}</h1>
<div class="sub">{_e(run["started"].replace("T", " "))} ~ {_e((run.get("finished") or "진행 중")[11:] or "진행 중")} · 가상 제어기 127.0.0.1 (dev-simulator)</div>
<div class="hero"><span class="badge {VERDICT_CLS.get(v, 'na')}">{_e(v)}</span>
<div class="meta">
<div><b>PalletizOS (화면)</b>{_e(run.get("palletizos_version", "-"))}</div>
<div><b>Dr.Dart-Platform (설치)</b>{_e(run.get("platform_version", "-"))}</div>
<div><b>기대 버전</b>{_e(run.get("expect_version") or "입력 안 함")}</div>
<div><b>결과</b>{_e(summary)}</div>
<div><b>원상복구</b>{_e(rest)}</div>
</div></div>
{f'<div class="notes">{notes}</div>' if notes else ''}
<h2>흐름별 결과</h2>
<div class="wrap"><table><tr><th>TC</th><th>흐름</th><th>판정</th><th>시간</th></tr>{"".join(rows)}</table></div>
{newsec}
<h2>최근 실행 이력</h2>
<div class="wrap"><table><tr><th>시작</th><th>판정</th><th>PalletizOS / Platform</th><th>흐름 ({" ".join(tcs)})</th></tr>{"".join(hrows)}</table></div>
<p class="sub">판정 규칙: 실패 1개 이상 → 보류 / 주의·불안정만 → 통과(주의) / 환경 오류 → 재실행 필요. "Safety zone error"는 지시에 따라 판정에서 제외.</p>
</main>{ISSUE_UI.read_text(encoding="utf-8")}</body></html>"""
    p = outdir / "report.html"
    p.write_text(doc, encoding="utf-8")
    (outdir.parent / "latest.html").write_text(
        f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={outdir.name}/report.html">',
        encoding="utf-8")
    return p
