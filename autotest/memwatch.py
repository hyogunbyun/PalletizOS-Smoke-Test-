"""앱 메모리 판정 — '의심'(본인 재실행 판단용)과 '확정'(개발팀 결함 근거)을 나눈다 (2026-11-05 grill-me 합의안).

- 누수 판정 지표는 전용 커밋(Private Bytes): 디스크로 밀려나도 줄지 않음. 작업 집합(WS)은 PC 부족 때 앱 점유율 표시에만.
- 기준값은 처음엔 임시값. 정상 전체 실행 3회가 모이면 정상 최대치 × 1.5 로 '제안'을 만들고, 사람이 accept 해야 반영.
  반영 전에는 '확정'을 붙이지 않는다.
- 정상 실행: 41개 전체 · 앱 재시작 0 · 크래시/앱 메모리/제어기 판정 없음 · PC 사용률 < 85% · 같은 앱 버전 (제품 실패는 허용).
- 재현(--fresh [--repeat N]): 앱 재시작 직후 그 항목만. 시작 전 PC ≥ 85% 면 거부(--force 로 강제 가능),
  도중에 85% 넘으면 '판정 불가', 강제 실행이면 '확정' 안 붙임.

명령: python -m autotest.memwatch status | accept
"""
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_FILE = ROOT / "results" / "memory_baseline.json"
PC_LIMIT = 85  # PC 메모리 사용률(%) — 이 이상이면 정상 실행·재현 판정에 못 씀
NEED_SAMPLES = 3
DEFAULT = {"item_jump_mb": 600, "run_growth_mb": 1500, "app_total_mb": 3000, "repeat_slope_mb": 50}
NAMES = {"item_jump_mb": "한 항목 동안 증가", "run_growth_mb": "실행 전체 누적 증가", "app_total_mb": "앱 합계",
         "repeat_slope_mb": "반복 회당 평균 증가"}


# ---------------------------------------------------------------- 기준값
def _load():
    try:
        return json.loads(BASE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"active": None, "samples": [], "proposed": None}


def _save(d):
    BASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def thresholds():
    """(기준값 dict, 상태 문구, 확정 가능 여부)."""
    d = _load()
    if d.get("active"):
        return {**DEFAULT, **d["active"]}, f"정상 실행 기준 ({d.get('active_at', '')[:10]} 반영, 앱 {d.get('active_version', '?')})", True
    wait = " · 제안 반영 대기: python -m autotest.memwatch accept" if d.get("proposed") else ""
    return dict(DEFAULT), f"임시 (정상 데이터 {min(len(d.get('samples', [])), NEED_SAMPLES)}/{NEED_SAMPLES}회{wait})", False


# ---------------------------------------------------------------- 측정
def point():
    """지금 앱 메모리: {t, pid, pb(전용 커밋 합 MB), ws(작업 집합 합 MB), load(PC 사용률 %)}."""
    from . import diag
    try:
        procs = diag.app_processes()
        m = diag.system_memory()
    except Exception:  # noqa: BLE001
        return {}
    return {"t": time.strftime("%H:%M:%S"), "pid": procs[0]["pid"] if procs else None,
            "pb": sum(p["private_mb"] for p in procs), "ws": sum(p["ws_mb"] for p in procs), "load": m.get("load_pct")}


def _growth(a):
    m0, m1 = a.get("mem0") or {}, a.get("mem1") or {}
    if m0.get("pid") and m0.get("pid") == m1.get("pid"):
        return m1["pb"] - m0["pb"], m1["ws"] - m0["ws"]
    return None, None


def item_rows(run):
    """항목별 앱 메모리 증가 [(tc, 시도, pb0, pb1, dpb, ws0, ws1, dws)] — 같은 앱 프로세스일 때만."""
    out = []
    for r in run.get("results", []):
        for a in r.get("attempts", []):
            dpb, dws = _growth(a)
            if dpb is None:
                continue
            out.append((r["tc"], a.get("attempt"), a["mem0"]["pb"], a["mem1"]["pb"], dpb, a["mem0"]["ws"], a["mem1"]["ws"], dws))
    return out


def pc_max(run):
    vals = [m.get("load") for r in run.get("results", []) for a in r.get("attempts", [])
            for m in (a.get("mem0") or {}, a.get("mem1") or {}) if m.get("load") is not None]
    vals += [run.get(k, {}).get("load") for k in ("mem_start", "mem_end") if (run.get(k) or {}).get("load") is not None]
    return max(vals) if vals else None


# ---------------------------------------------------------------- 정상 실행 → 기준값 제안
def _version(run):
    return run.get("palletizos_build") or run.get("palletizos_version") or "?"


def normal_reasons(run, full):
    """정상 실행이 아닌 이유 목록 (빈 목록 = 정상)."""
    why = []
    if not full:
        why.append("41개 전체 실행이 아님")
    if any(a.get("restore") for r in run.get("results", []) for a in r.get("attempts", [])):
        why.append("실행 중 앱 재시작")
    bad = {a.get("diag", {}).get("category") for r in run.get("results", []) for a in r.get("attempts", [])}
    for c, n in (("app_crash", "앱 크래시"), ("app_memory", "앱 메모리 의심"), ("controller", "제어기 문제")):
        if c in bad:
            why.append(n)
    if any(r["status"] == "env" for r in run.get("results", [])):
        why.append("실행되지 않은(환경 오류) 항목 있음")
    pm = pc_max(run)
    if pm is None or pm >= PC_LIMIT:
        why.append(f"PC 메모리 사용률 최대 {pm}% (기준 {PC_LIMIT}% 미만)")
    if run.get("stopped"):
        why.append("사용자가 중단")
    return why


def add_sample(run, outdir_name, full):
    """정상 실행이면 기준 데이터에 추가. 리포트·사건 로그용 한 줄 반환."""
    why = normal_reasons(run, full)
    if why:
        return f"메모리 기준 데이터로 안 씀: {', '.join(why)}"
    d = _load()
    ver = _version(run)
    if d.get("samples") and d["samples"][-1].get("version") != ver:
        d["samples"], d["proposed"] = [], None  # 앱 버전이 바뀌면 0부터
    rows = item_rows(run)
    s0, s1 = run.get("mem_start") or {}, run.get("mem_end") or {}
    d.setdefault("samples", []).append({
        "version": ver, "at": datetime.now().isoformat(timespec="seconds"), "dir": outdir_name,
        "item_max_mb": max((x[4] for x in rows), default=0),
        "run_growth_mb": (s1["pb"] - s0["pb"]) if s0.get("pid") and s0.get("pid") == s1.get("pid") else None,
        "app_max_mb": max([x[3] for x in rows] + [s0.get("pb", 0), s1.get("pb", 0)]),
        "items": len(run.get("results", [])),
    })
    n = len(d["samples"])
    msg = f"메모리 기준 데이터 추가 ({n}/{NEED_SAMPLES}회, 앱 {ver})"
    if n >= NEED_SAMPLES and not d.get("proposed"):
        ss = d["samples"][-NEED_SAMPLES:]
        rg = [s["run_growth_mb"] for s in ss if s["run_growth_mb"] is not None]
        per = max((s["run_growth_mb"] or 0) / max(1, s["items"]) for s in ss)
        d["proposed"] = {
            "item_jump_mb": max(100, math.ceil(1.5 * max(s["item_max_mb"] for s in ss))),
            "run_growth_mb": max(300, math.ceil(1.5 * max(rg))) if rg else DEFAULT["run_growth_mb"],
            "app_total_mb": max(1000, math.ceil(1.5 * max(s["app_max_mb"] for s in ss))),
            "repeat_slope_mb": max(20, math.ceil(1.5 * per)),
            "version": ver, "from": [s["dir"] for s in ss], "at": datetime.now().isoformat(timespec="seconds"),
        }
        msg += (" → 기준값 제안 준비됨: " + ", ".join(f"{NAMES[k]} {d['proposed'][k]}MB" for k in DEFAULT)
                + " — 반영하려면 python -m autotest.memwatch accept")
    _save(d)
    return msg


def accept():
    d = _load()
    p = d.get("proposed")
    if not p:
        return "반영할 기준값 제안이 없음 (정상 전체 실행 3회가 아직 안 모임)"
    d["active"] = {k: p[k] for k in DEFAULT}
    d["active_at"], d["active_version"] = datetime.now().isoformat(timespec="seconds"), p.get("version")
    _save(d)
    return "기준값 반영: " + ", ".join(f"{NAMES[k]} {p[k]}MB" for k in DEFAULT)


# ---------------------------------------------------------------- 재현 (--fresh [--repeat N])
def precheck(force):
    """재현 시작 전 PC 메모리. (시작해도 되는지, 안내 문구)."""
    from . import diag
    m = diag.system_memory()
    if m["load_pct"] < PC_LIMIT:
        return True, f"PC 메모리 {m['load_pct']}% (기준 {PC_LIMIT}% 미만)"
    try:
        top = ", ".join(f"{n.removesuffix('.exe')} {mb:,}MB" for n, mb, _ in diag.top_memory(5))
    except Exception:  # noqa: BLE001
        top = "?"
    txt = f"PC 메모리 부족 (지금 {m['load_pct']}%, 남은 {m['avail_mb']:,}MB) — 많이 쓰는 프로그램: {top}"
    if force:
        return True, txt + " · --force 로 강제 실행 ('확정'은 붙이지 않음)"
    return False, txt + f" · 닫고 다시 실행하세요 (강제로 돌리려면 --force)"


def repro_verdict(tc, run, reps, forced, start_load):
    """reps = [{i, status, mem0, mem1}] (회차별). 결과 dict."""
    th, th_status, calibrated = thresholds()
    s0 = run.get("mem_start") or {}
    series = [{"i": 0, "pb": s0.get("pb"), "ws": s0.get("ws"), "load": s0.get("load"), "t": s0.get("t")}]
    pid = s0.get("pid")
    same = True
    for r in reps:
        m1 = r.get("mem1") or {}
        same = same and m1.get("pid") == pid
        series.append({"i": r["i"], "pb": m1.get("pb"), "ws": m1.get("ws"), "load": m1.get("load"), "t": m1.get("t"),
                       "status": r["status"]})
    n = len(reps)
    pm = max([x for x in (pc_max(run), start_load) if x is not None], default=None)
    pbs = [x["pb"] for x in series if x["pb"] is not None]
    total = (pbs[-1] - pbs[0]) if len(pbs) >= 2 else None
    fails = sum(1 for r in reps if r["status"] in ("fail", "env"))
    out = {"tc": tc, "repeat": n, "series": series, "thresholds": th, "threshold_status": th_status,
           "pc_start": start_load, "pc_max": pm, "forced": forced, "total_mb": total,
           "version": _version(run), "platform": run.get("platform_version"), "fails": fails}
    if not same or len(pbs) != len(series):
        out.update(result="판정 불가 (재현 중 앱이 재시작됨 — 메모리 연속성 없음)", reproduced=None, confirmed=False)
        return out
    if n == 1:
        rep = fails > 0 or (total or 0) >= th["item_jump_mb"]
        basis = f"1회 실행 · 증가 {total:+,}MB (기준 {th['item_jump_mb']}MB) · {'실패' if fails else '통과'}"
    else:
        diffs = [b - a for a, b in zip(pbs, pbs[1:])]
        inc = sum(1 for x in diffs if x > 0)
        slope = total / n
        rep = slope >= th["repeat_slope_mb"] and inc >= math.ceil(0.8 * n)
        basis = (f"{n}회 반복 · 전용 커밋 {pbs[0]:,} → {pbs[-1]:,}MB · 회당 평균 {slope:+.0f}MB (기준 {th['repeat_slope_mb']}MB) · "
                 f"증가한 회차 {inc}/{n}")
        out.update(slope_mb=round(slope, 1), increasing=inc)
    out["basis"] = basis
    out["reproduced"] = rep
    pc_bad = pm is not None and pm >= PC_LIMIT
    if pc_bad and not forced:
        out.update(result=f"판정 불가 (재현 중 PC 메모리 부족 — 최대 {pm}%)", confirmed=False)
    elif not rep:
        out.update(result="재현 안 됨 (깨끗한 상태에서 정상)", confirmed=False)
    elif forced and (pc_bad or (start_load or 0) >= PC_LIMIT):
        out.update(result="재현됨 — 확정 아님 (PC 메모리 부족 상태에서 강제 실행)", confirmed=False)
    elif not calibrated:
        out.update(result=f"재현됨 — 확정 보류 (기준값 {th_status})", confirmed=False)
    else:
        out.update(result="앱 메모리 확정 (재현됨)", confirmed=True)
    return out


def jira_text(rep):
    s = rep["series"]
    lines = [f"[메모리] {rep['tc']} 반복 실행 시 앱 메모리 증가 ({rep['result']})",
             f"- 앱: PalletizOS {rep['version']} / Dr.Dart-Platform {rep.get('platform')}",
             f"- 절차: 앱 재시작 직후 python run_smoke.py --only {rep['tc']} --fresh" + (f" --repeat {rep['repeat']}" if rep["repeat"] > 1 else ""),
             f"- 결과: {rep.get('basis', '')}",
             f"- PC 메모리: 시작 {rep.get('pc_start')}% · 최대 {rep.get('pc_max')}% (기준 {PC_LIMIT}% 미만)",
             f"- 회차별 전용 커밋(MB): " + ", ".join(f"{x['i']}:{x['pb']}" for x in s),
             f"- 판정 기준: {rep['threshold_status']}",
             "- 첨부: memory_repro.json, report.html (회차별 그래프), 앱 로그"]
    return "\n".join(lines)


# ---------------------------------------------------------------- 리포트 HTML
def _e(s):
    import html
    return html.escape(str(s if s is not None else ""))


def _svg(series):
    pts = [x for x in series if x.get("pb") is not None]
    if len(pts) < 2:
        return ""
    W, H, L, B, T = 640, 220, 56, 30, 14
    vals = [x["pb"] for x in pts] + [x["ws"] for x in pts if x.get("ws") is not None]
    lo, hi = min(vals), max(vals)
    if hi - lo < 50:
        lo, hi = lo - 25, hi + 25
    n = len(pts) - 1
    X = lambda i: L + (W - L - 12) * i / max(1, n)  # noqa: E731
    Y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    def line(key, color, name):
        p = " ".join(f"{X(k):.1f},{Y(x[key]):.1f}" for k, x in enumerate(pts) if x.get(key) is not None)
        dots = "".join(f"<circle cx='{X(k):.1f}' cy='{Y(x[key]):.1f}' r='3' fill='{color}'><title>{name} {x['i']}회: {x[key]:,}MB</title></circle>"
                       for k, x in enumerate(pts) if x.get(key) is not None)
        return f"<polyline points='{p}' fill='none' stroke='{color}' stroke-width='2'/>{dots}"
    grid = "".join(f"<line x1='{L}' x2='{W - 12}' y1='{Y(v):.1f}' y2='{Y(v):.1f}' stroke='#e3e6eb'/>"
                   f"<text x='{L - 6}' y='{Y(v) + 4:.1f}' text-anchor='end' font-size='11' fill='#5b6475'>{v:,.0f}</text>"
                   for v in (lo, (lo + hi) / 2, hi))
    xl = "".join(f"<text x='{X(k):.1f}' y='{H - 10}' text-anchor='middle' font-size='11' fill='#5b6475'>{x['i']}</text>"
                 for k, x in enumerate(pts))
    return (f"<svg viewBox='0 0 {W} {H}' style='width:100%;max-width:{W}px;background:#fff;border:1px solid #e3e6eb;border-radius:8px'>"
            f"{grid}{xl}{line('pb', '#d64545', '전용 커밋')}{line('ws', '#2f6fd6', '작업 집합')}</svg>"
            "<div class='sub'><span style='color:#d64545'>■</span> 전용 커밋(누수 판정 기준) · "
            "<span style='color:#2f6fd6'>■</span> 작업 집합(실제 RAM) · 가로축 = 회차(0 = 시작 직후), 단위 MB</div>")


def repro_html(rep):
    if not rep:
        return ""
    cls = "bad" if rep.get("confirmed") else ("warn" if rep.get("reproduced") else ("ok" if rep.get("reproduced") is False else "env"))
    rows = "".join(f"<tr><td>{x['i']}</td><td>{_e(x.get('t'))}</td><td>{_e(x.get('status', '시작'))}</td><td>{x.get('pb', '')}</td>"
                   f"<td>{x.get('ws', '')}</td><td>{_e(x.get('load'))}%</td></tr>" for x in rep["series"])
    return (f"<h2>메모리 재현 확인 — {_e(rep['tc'])}</h2>"
            f"<div class='hero'><span class='badge {cls}'>{_e(rep['result'])}</span><div class='meta'>"
            f"<div><b>근거</b>{_e(rep.get('basis', ''))}</div>"
            f"<div><b>PC 메모리</b>시작 {_e(rep.get('pc_start'))}% · 최대 {_e(rep.get('pc_max'))}%{' · 강제 실행' if rep.get('forced') else ''}</div>"
            f"<div><b>판정 기준값</b>{_e(rep['threshold_status'])}</div></div></div>"
            f"<div style='margin-top:12px'>{_svg(rep['series'])}</div>"
            f"<details><summary>회차별 숫자</summary><table><tr><th>회차</th><th>시각</th><th>결과</th><th>전용 커밋 MB</th>"
            f"<th>작업 집합 MB</th><th>PC</th></tr>{rows}</table></details>"
            f"<details><summary>JIRA 등록용 요약 (복사해서 붙여넣기 — 자동 등록 안 함)</summary><pre>{_e(jira_text(rep))}</pre></details>")


def items_html(run):
    rows = item_rows(run)
    if not rows:
        return ""
    th, th_status, _ = thresholds()
    rows = sorted(rows, key=lambda x: -x[4])
    s0, s1 = run.get("mem_start") or {}, run.get("mem_end") or {}
    tot = (f"실행 전체: 전용 커밋 {s0['pb']:,} → {s1['pb']:,}MB ({s1['pb'] - s0['pb']:+,}MB, 기준 {th['run_growth_mb']:,}MB)"
           if s0.get("pid") and s0.get("pid") == s1.get("pid") else "실행 전체: 중간에 앱이 재시작돼 누적 비교 불가")
    body = "".join(
        f"<tr><td class='tc'>{_e(tc)}</td><td>{att}</td><td>{p0:,} → {p1:,}</td>"
        f"<td><b style='color:{'#d64545' if d >= th['item_jump_mb'] else 'inherit'}'>{d:+,}</b></td><td>{w0:,} → {w1:,} ({dw:+,})</td></tr>"
        for tc, att, p0, p1, d, w0, w1, dw in rows)
    note = _e(run.get("memory_note", ""))
    return (f"<h2>항목별 앱 메모리 증가</h2><p class='sub'>{_e(tot)} · PC 사용률 최대 {_e(pc_max(run))}% · "
            f"판정 기준값 {_e(th_status)} (한 항목 {th['item_jump_mb']:,}MB) · 큰 순서" + (f"<br>{note}" if note else "") + "</p>"
            f"<details><summary>표 열기 ({len(rows)}행)</summary><div class='wrap'><table><tr><th>TC</th><th>시도</th>"
            f"<th>전용 커밋 MB</th><th>증가</th><th>작업 집합 MB</th></tr>{body}</table></div></details>")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "accept":
        print(accept())
    else:
        th, st, _ = thresholds()
        d = _load()
        print(f"기준값 상태: {st}")
        print("  " + ", ".join(f"{NAMES[k]} {th[k]}MB" for k in DEFAULT))
        if d.get("proposed"):
            print("제안 대기: " + ", ".join(f"{NAMES[k]} {d['proposed'][k]}MB" for k in DEFAULT) + " → python -m autotest.memwatch accept")
