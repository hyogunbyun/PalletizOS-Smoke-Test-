"""녹화 시나리오 재생: scenarios/C##_*.json을 읽어 흐름(C01, C02…)으로 등록한다.

단계 찾기: 이름 있는 요소는 (종류, 이름, 같은 이름 중 순서), 이름 없는 요소는 기준 요소 + 상대 위치,
접힌 메뉴 아이콘은 메뉴 이름(goto). 각 단계 뒤 새 에러 문구가 없어야 하고, 끝나면 고른 문구가 보여야 PASS.
"""
import json
from pathlib import Path

from .flows import FLOWS, SHORT, check, flow
from .ui import pause

SCEN_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def _center(e):
    r = e.rectangle()
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


def _nth(ui, ctype, name, nth):
    same = sorted([e for e in ui.top_all(ctype) if (e.element_info.name or "").strip() == name
                   and e.rectangle().width() > 0], key=lambda e: (e.rectangle().top, e.rectangle().left))
    if not same:
        return None
    return same[min(nth, len(same) - 1)]


def _find(ui, st):
    if st["type"] == "nav":
        return "nav"
    if st.get("name"):
        return _nth(ui, st["type"], st["name"], st.get("nth", 0))
    a = st["anchor"]
    anc = _nth(ui, a["type"], a["name"], a.get("nth", 0))
    if anc is None:
        return None
    ax, ay = _center(anc)
    x, y = ax + st["offset"][0], ay + st["offset"][1]
    hits = [e for e in ui.top_all(st["type"]) if e.rectangle().left <= x < e.rectangle().right
            and e.rectangle().top <= y < e.rectangle().bottom]
    return min(hits, key=lambda e: e.rectangle().width() * e.rectangle().height()) if hits else None


def _run(data):
    def fn(ctx):
        ui = ctx.ui
        for i, st in enumerate(data["steps"], 1):
            ctx.step(f"{i}/{len(data['steps'])} {st['label']}" + (f" ← '{st['value']}'" if st.get("action") == "set_text" else ""))
            el = None
            ok = ui.wait_for(lambda: (_find(ui, st) is not None), 6)
            check(ok, f"{i}단계 요소를 찾지 못함: {st['label']}")
            el = _find(ui, st)
            before = ui.window_texts()
            if el == "nav":
                ui.goto(st["name"])
            elif st.get("action") == "set_text":
                ui.set_text(el, st.get("value", ""), label=st["label"])
            else:
                ui.click(el, settle=1.5, label=st["label"])
            errs = ui.error_texts(before, ui.window_texts())
            check(not errs, f"{i}단계 뒤 에러 문구 표시: {errs}")
        if data.get("expects"):
            ctx.step(f"확인 문구 {len(data['expects'])}개 표시 기대")
            ok = ui.wait_for(lambda: set(data["expects"]) <= ui.top_names(), 6)
            missing = sorted(set(data["expects"]) - ui.top_names())
            check(ok, f"끝났을 때 보여야 할 문구 없음: {missing}")
        pause(0.5)
    return fn


def load():
    if not SCEN_DIR.exists():
        return
    have = {f["tc"] for f in FLOWS}
    for p in sorted(SCEN_DIR.glob("C*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("id") in have or not data.get("steps") or not data.get("enabled", True):
            continue  # 관리 창에서 '실행에 포함'을 끈 시나리오는 건너뜀
        flow(data["id"], data.get("title", p.stem), data.get("desc", "녹화 시나리오"), admin=bool(data.get("admin")))(_run(data))
        SHORT[data["id"]] = data.get("title", "")[:6]


load()
