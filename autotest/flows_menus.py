"""PalletizOS 메뉴 스모크 (Recipes·IO·Log·Settings·Jog +·Quick Log·Recovery).

판정 근거는 2026-10-19 Admin 계정 실측(DESIGN.md). 값을 바꾸는 동작은 원복 가능한 것만 하고,
Delete·Import·Initialize System·Install New Version·Get Pose/Move To·Open TeamViewer·Export(파일 생성)는 누르지 않는다.
각 흐름은 Home에서 시작하고, 끝나면 러너가 Home으로 되돌린다.
"""
import re
import time

from .flows import NotApplicable, check, flow
from .ui import pause

LOG_ROW = re.compile(r"^(\d\d\.\d\d \d\d:\d\d:\d\d) (\w+) (\w+) (\d{4}) (.*)$")


# ---------------------------------------------------------------- 공통
def _open(ctx, menu, anchor, timeout=8):
    ctx.ui.goto(menu)
    check(ctx.ui.wait_for(lambda: anchor in ctx.ui.top_names(), timeout), f"'{menu}' 화면이 열리지 않음 ('{anchor}' 없음)")


def _content_left(ui):
    """좌측 메뉴(펼침/접힘) 오른쪽 = 콘텐츠 영역 시작 x."""
    wr = ui.wrapper().rectangle()
    nav = [b.rectangle().right for b in ui.top_all("Button") if b.rectangle().left < wr.left + 40 and b.rectangle().width() > 0]
    return (max(nav) if nav else wr.left) + 5


def _cy(e):
    r = e.rectangle()
    return (r.top + r.bottom) // 2


def _same_row(elems, ref, tol=None):
    tol = tol or max(12, ref.rectangle().height() // 2)
    return sorted([e for e in elems if abs(_cy(e) - _cy(ref)) <= tol], key=lambda e: e.rectangle().left)


def _type(ui, edit, text, label):
    ui.set_text(edit, text, label=label)
    pause(0.6)


def _selected(e):
    try:
        return bool(e.iface_selection_item.CurrentIsSelected)
    except Exception:
        return None


# ================================================================ Recipes
def _recipe_rows(ui):
    """레시피 목록 [(이름, 이름Text, ⋮버튼)] — 오른쪽 목록 영역의 체크박스 행 기준."""
    wr = ui.wrapper().rectangle()
    mid = wr.left + wr.width() // 2
    texts = [t for t in ui.top_all("Text") if t.rectangle().left > mid and t.rectangle().width() > 0]
    menus = [b for b in ui.top_all("Button") if b.window_text() == "menu" and b.rectangle().left > mid]
    rows = []
    for cb in [c for c in ui.top_all("CheckBox") if c.rectangle().left > mid and c.rectangle().width() > 0]:
        row = [t for t in _same_row(texts, cb) if t.rectangle().left > cb.rectangle().right and t.window_text() not in ("In Use",)]
        if row:
            m = next(iter(_same_row(menus, cb)), None)
            rows.append((row[0].window_text(), row[0], m, any(t.window_text() == "In Use" for t in _same_row(texts, cb))))
    return sorted(rows, key=lambda r: r[1].rectangle().top)


def _recipe_count(ui):
    ts = [t for t in ui.top_all("Text") if t.rectangle().width() > 0]
    for i, t in enumerate(ts):
        if t.window_text() == "Recipe" and i and ts[i - 1].window_text().isdigit():
            return int(ts[i - 1].window_text())
    return None


def _recipe_panel(ui):
    """3D 미리보기 아래 정보 패널의 Boxes / Layer 값."""
    ts = [t for t in ui.top_all("Text") if t.rectangle().width() > 0]
    out = {}
    for key in ("Boxes", "Layer"):
        lab = next((t for t in ts if t.window_text() == key and t.rectangle().left < ui.wrapper().rectangle().left
                    + ui.wrapper().rectangle().width() // 2), None)
        if lab:
            vals = [t.window_text() for t in _same_row(ts, lab) if t.rectangle().left > lab.rectangle().right and t.window_text().isdigit()]
            out[key] = int(vals[-1]) if vals else None
    return out


def _home_recipe(ctx):
    for s in ("Right", "Left"):
        if ctx.snap0[s]["on"]:
            lv, lm = ctx.snap0[s]["layer"]
            bv, bm = ctx.snap0[s]["boxes"]
            return ctx.snap0[s]["recipe"], int(lm) * int(bm), int(lm)
    return None, None, None


@flow("R01", "Recipes 목록·In Use", "목록 개수 표시 = 행 수, 'In Use' 레시피 = Home 레시피, 정보 패널 Boxes/Layer = Home 값", admin=True)
def r01_list(ctx):
    ui = ctx.ui
    _open(ctx, "Recipes", "Create Recipe")
    ctx.step("목록 개수 표시와 실제 행 수 비교")
    rows, cnt = _recipe_rows(ui), _recipe_count(ui)
    check(rows, "레시피 목록이 비어 있음")
    check(cnt == len(rows), f"개수 표시 {cnt} ≠ 행 수 {len(rows)}")
    name, total, layers = _home_recipe(ctx)
    inuse = [r[0] for r in rows if r[3]]
    if name:
        ctx.step(f"'In Use' 레시피가 Home 레시피({name})와 같은지")
        check(inuse == [name], f"In Use {inuse} ≠ Home 레시피 {name}")
        ui.click(next(r[1] for r in rows if r[0] == name), settle=1.5, label=f"{name} 선택")
        p = _recipe_panel(ui)
        check(p.get("Boxes") == total and p.get("Layer") == layers,
              f"정보 패널 Boxes/Layer {p} ≠ Home 값 (전체 {total}, 층 {layers})")


@flow("R02", "레시피 선택 → 정보 패널", "다른 행을 누르면 정보 패널이 그 레시피 값으로 바뀌고, 원래 행을 누르면 되돌아옴", admin=True)
def r02_select(ctx):
    ui = ctx.ui
    _open(ctx, "Recipes", "Create Recipe")
    rows = _recipe_rows(ui)
    if len(rows) < 2:
        raise NotApplicable("레시피가 1개뿐")
    ui.click(rows[0][1], settle=1.5, label=f"{rows[0][0]} 선택")
    p0 = _recipe_panel(ui)
    seen = {rows[0][0]: p0}
    for nm, t, _, _ in rows[1:]:
        ctx.step(f"'{nm}' 선택 → 정보 패널 값 확인")
        ui.click(t, settle=1.5, label=f"{nm} 선택")
        p = _recipe_panel(ui)
        check(p.get("Boxes") is not None and p.get("Layer") is not None, f"{nm} 선택 후 정보 패널 값 없음 {p}")
        seen[nm] = p
    ui.click(rows[0][1], settle=1.5, label=f"{rows[0][0]} 다시 선택")
    check(_recipe_panel(ui) == p0, f"처음 레시피를 다시 골랐는데 패널 값이 다름 ({_recipe_panel(ui)} ≠ {p0})")
    ctx.info.setdefault("recipes", seen)


@flow("R03", "레시피 검색", "부분 일치 검색 → 해당 행만, 없는 단어 → 0개·'No matching results.', 지우면 전체 복귀", admin=True)
def r03_search(ctx):
    ui = ctx.ui
    _open(ctx, "Recipes", "Create Recipe")
    names = [r[0] for r in _recipe_rows(ui)]
    edit = ui.top_find("Search", "Edit")
    check(edit is not None, "검색창 없음")
    # 일부 행에만 들어 있는 숫자 조각을 검색어로 (모든 행에 있으면 걸러지는지 알 수 없음)
    parts = [m for n in names for m in re.findall(r"\d+", n) if 0 < sum(m in x for x in names) < len(names)]
    q = parts[0] if parts else names[0][:4]
    want = [n for n in names if q.lower() in n.lower()]
    ctx.step(f"'{q}' 검색 → {len(want)}개 기대")
    _type(ui, edit, q, f"검색 '{q}'")
    got = [r[0] for r in _recipe_rows(ui)]
    check(got == want and _recipe_count(ui) == len(want), f"'{q}' 검색 결과 {got} ≠ 기대 {want}")
    ctx.step("없는 단어 검색 → 0개·안내 문구")
    _type(ui, edit, "zzqq_nomatch", "검색 'zzqq_nomatch'")
    check(not _recipe_rows(ui) and "No matching results." in ui.top_names(), "결과 없음 안내가 표시되지 않음")
    ctx.step("검색어 지우기 → 전체 목록 복귀")
    _type(ui, edit, "", "검색어 지우기")
    check([r[0] for r in _recipe_rows(ui)] == names, "검색어를 지웠는데 전체 목록으로 돌아오지 않음")


@flow("R04", "레시피 ⋮ 메뉴", "행의 ⋮ → 메뉴 6개(Edit Recipe·Save As·Export·Apply SwiftMove·Advanced Settings·Delete), ESC로 닫힘", admin=True)
def r04_menu(ctx):
    ui = ctx.ui
    _open(ctx, "Recipes", "Create Recipe")
    row = _recipe_rows(ui)[0]
    ctx.step(f"'{row[0]}' ⋮ 메뉴 열기")
    ui.click(row[2], settle=1.5, label=f"{row[0]} ⋮")
    items = {e.element_info.name for e in ui.top_all("MenuItem")}
    want = {"Edit Recipe", "Save As", "Export", "Apply SwiftMove", "Advanced Settings", "Delete"}
    check(want <= items, f"⋮ 메뉴 항목 누락: {sorted(want - items)}")
    ctx.step("ESC → 메뉴 닫힘 (아무 항목도 누르지 않음)")
    ui.esc()
    check(not ui.top_all("MenuItem"), "ESC를 눌렀는데 ⋮ 메뉴가 남아 있음")


@flow("R05", "Create Recipe 편집기", "Create Recipe → 편집기(이름 기본값·Box 단계) 열림 → X로 닫으면 레시피 수 그대로", admin=True)
def r05_create(ctx):
    ui = ctx.ui
    _open(ctx, "Recipes", "Create Recipe")
    n0 = _recipe_count(ui)
    ctx.step("Create Recipe → 편집기 열림 확인")
    ui.click(ui.top_find("Create Recipe"), settle=3)
    check(ui.wait_for(lambda: {"Box", "Stack"} <= ui.top_names(), 8), "편집기(Box/Stack 단계)가 열리지 않음")
    check(ui.top_find("Next", startswith=True) is not None, "편집기에 Next 버튼 없음")
    names = [e.iface_value.CurrentValue for e in ui.top_all("Edit") if e.rectangle().top < ui.wrapper().rectangle().top + 150]
    check(any(v for v in names), "새 레시피 이름 기본값이 비어 있음")
    ctx.step("저장하지 않고 X로 닫기 → 목록·개수 그대로")
    wr = ui.wrapper().rectangle()
    x = [b for b in ui.top_all("Button") if b.rectangle().left < wr.left + 120 and b.rectangle().top < wr.top + 150 and not b.window_text()]
    check(x, "편집기 닫기(X) 버튼 없음")
    ui.click(x[0], settle=2.5, label="편집기 닫기(X)")
    check(ui.wait_for(lambda: "Create Recipe" in ui.top_names(), 8), "편집기를 닫았는데 목록으로 돌아오지 않음 (저장 확인창?)")
    check(_recipe_count(ui) == n0, f"편집기만 열고 닫았는데 레시피 수가 바뀜 ({n0} → {_recipe_count(ui)})")


# ================================================================ IO
IO_TABS = {"Favorites": "Digital IO & Flange IO", "Modbus Master": "Modbus Input Card",
           "Digital Input": "Port #", "Digital Output": "Test", "Flange IO": "Output"}


def _io_tab(ctx, tab):
    ui = ctx.ui
    ui.click(ui.top_find(tab), settle=2, label=f"탭 {tab}")
    check(ui.wait_for(lambda: IO_TABS[tab] in ui.top_names(), 6), f"IO '{tab}' 탭 내용이 보이지 않음 ('{IO_TABS[tab]}' 없음)")


def _io_row(ui, port_text_left_max, port="1", x_min=None):
    """포트 번호 행의 값(On/Off)과 Test 버튼 [On, Off]."""
    x_min = x_min if x_min is not None else _content_left(ui)
    # 표가 좌우 두 열(1~8 | 9~16)이면 같은 높이의 오른쪽 열이 섞이지 않게 다음 'Port #' 머리글 앞까지만
    heads = [t.rectangle().left for t in ui.top_all("Text") if t.window_text() == "Port #" and t.rectangle().left > x_min + 100]
    x_max = (min(heads) - 10) if heads else 10 ** 6
    ts = [t for t in ui.top_all("Text") if x_min <= t.rectangle().left < x_max and t.rectangle().width() > 0]
    p = next((t for t in ts if t.window_text() == port and t.rectangle().left <= port_text_left_max), None)
    check(p is not None, f"포트 {port} 행 없음")
    vals = [t.window_text() for t in _same_row(ts, p, 20) if t.window_text() in ("On", "Off")]
    btns = [b for b in _same_row([b for b in ui.top_all("Button") if x_min <= b.rectangle().left < x_max], p, 30)
            if b.window_text() in ("On", "Off")]
    return (vals[0] if vals else None), btns


@flow("I01", "IO 탭 전환", "Favorites·Modbus Master·Digital Input·Digital Output·Flange IO 탭이 각각 고유 내용을 표시")
def i01_tabs(ctx):
    _open(ctx, "IO", "Modbus Master")
    for tab in IO_TABS:
        ctx.step(f"'{tab}' 탭 → '{IO_TABS[tab]}' 표시 확인")
        _io_tab(ctx, tab)


def _toggle_output(ctx, tab, where, x_min_fn, log_pat=None):
    ui = ctx.ui
    _open(ctx, "IO", "Modbus Master")
    _io_tab(ctx, tab)
    x_min = x_min_fn(ui)
    v0, btns = _io_row(ui, x_min + 60, x_min=x_min)
    check(v0 in ("On", "Off") and len(btns) == 2, f"{where} 1번 행 해석 실패 (값 {v0}, 버튼 {len(btns)}개)")
    flip = "On" if v0 == "Off" else "Off"
    ctx.step(f"{where} 1번 Test '{flip}' → 값 {flip} 기대")
    ui.click(next(b for b in btns if b.window_text() == flip), settle=1.5, label=f"{where}1 {flip}")
    check(ui.wait_for(lambda: _io_row(ui, x_min + 60, x_min=x_min)[0] == flip, 5), f"{where} 1번 값이 {flip}(으)로 바뀌지 않음")
    if log_pat:
        check(ui.wait_for(lambda: ctx.log.saw(log_pat), 5), f"로그에 '{log_pat}' 없음")
    ctx.step(f"{where} 1번 원래 값 {v0}(으)로 복구")
    _, btns = _io_row(ui, x_min + 60, x_min=x_min)
    ui.click(next(b for b in btns if b.window_text() == v0), settle=1.5, label=f"{where}1 {v0}")
    check(ui.wait_for(lambda: _io_row(ui, x_min + 60, x_min=x_min)[0] == v0, 5), f"{where} 1번 원복 실패")


@flow("I02", "Digital Output 테스트", "DO 1번 Test On/Off → 값 표시 변경 + 로그 setDigitalOutput 200 OK, 원복")
def i02_do(ctx):
    _toggle_output(ctx, "Digital Output", "DO", _content_left, r"setDigitalOutput\(\), status: 200")


@flow("I03", "Flange IO 출력 테스트", "Flange Output 1번 Test On/Off → 값 표시 변경, 원복")
def i03_flange(ctx):
    def output_left(ui):
        out = next(t for t in ui.top_all("Text") if t.window_text() == "Output")
        return out.rectangle().left - 10
    _toggle_output(ctx, "Flange IO", "Flange", output_left)


@flow("I04", "Modbus Master 상태", "Modbus 카드 연결 상태(Connected/Disconnected)·IP 4자리·Port·신호 목록 표시")
def i04_modbus(ctx):
    ui = ctx.ui
    _open(ctx, "IO", "Modbus Master")
    _io_tab(ctx, "Modbus Master")
    n = ui.top_names()
    ctx.step("연결 상태·IP·Port·신호 목록 표시 확인")
    check({"Connected", "Disconnected"} & n, "Modbus 연결 상태 문구 없음")
    ts = [t for t in ui.top_all("Text") if t.rectangle().width() > 0]
    ip = next((t for t in ts if t.window_text() == "IP Address"), None)
    check(ip is not None, "IP Address 항목 없음")
    octets = [t.window_text() for t in _same_row(ts, ip) if t.rectangle().left > ip.rectangle().right and t.window_text().isdigit()]
    check(len(octets) >= 4 and all(0 <= int(o) <= 255 for o in octets[:4]), f"IP 표시 이상: {octets[:4]}")
    check("Port" in n and "Signal Type" in n, "Port/신호 목록 헤더 없음")
    ctx.info["modbus"] = {"status": sorted({"Connected", "Disconnected"} & n)[0], "ip": ".".join(octets[:4])}


# ================================================================ Log
def _log_rows(ui):
    out = []
    for b in ui.top_all("Button"):
        m = LOG_ROW.match(b.window_text() or "")
        if m:
            out.append((b.rectangle().top, m.groups()))
    return [g for _, g in sorted(out)]


@flow("L01", "Palletizing Log = 앱 로그", "Refresh 후 화면 최신 로그의 코드·메시지가 앱 로그 파일의 마지막 ModuleLog와 일치", admin=True)
def l01_latest(ctx):
    ui = ctx.ui
    _open(ctx, "Log", "Palletizing Log")
    ui.click(ui.top_find("Refresh"), settle=2)
    rows = _log_rows(ui)
    check(rows, "Palletizing Log 목록이 비어 있음")
    last = None
    for line in reversed(ctx.log.all_lines()):
        m = re.search(r"\[ModuleLog\]\[\d+\.(\d{4})\] (.*)$", line)
        if m:
            last = m.groups()
            break
    check(last is not None, "앱 로그 파일에 ModuleLog가 없음")
    top = rows[0]
    ctx.step(f"화면 최신 [{top[3]}] {top[4][:30]} ↔ 파일 [{last[0]}] {last[1][:30]}")
    check(top[3] == last[0] and top[4].strip() == last[1].strip(), f"화면 최신 로그 {top[3]} {top[4]!r} ≠ 파일 {last[0]} {last[1]!r}")


@flow("L02", "로그 검색", "메시지 단어로 검색 → 모든 행에 그 단어 포함, 지우면 원래 행 수", admin=True)
def l02_search(ctx):
    ui = ctx.ui
    _open(ctx, "Log", "Palletizing Log")
    rows = _log_rows(ui)
    m = re.search(r"\[(\w+)\]", rows[0][4]) if rows else None
    check(m, "검색어로 쓸 로그 메시지가 없음")
    q = m.group(1)
    edit = ui.top_find("Search", "Edit")
    ctx.step(f"'{q}' 검색 → 모든 행에 '{q}' 포함 기대")
    _type(ui, edit, q, f"로그 검색 '{q}'")
    # 목록이 검색 결과로 바뀌는 데 시간이 걸림 — 바로 읽으면 0행(2026-10-22 1차 실패) → 결과가 뜰 때까지 최대 4초
    ok = ui.wait_for(lambda: (lambda g: bool(g) and all(q.lower() in r[4].lower() for r in g))(_log_rows(ui)), 4)
    got = _log_rows(ui)
    check(ok, f"'{q}' 검색 결과에 다른 행이 섞임 ({len(got)}행)")
    _type(ui, edit, "", "검색어 지우기")
    check(len(_log_rows(ui)) == len(rows), f"검색어를 지웠는데 행 수가 다름 ({len(rows)} → {len(_log_rows(ui))})")


@flow("L03", "로그 정렬", "Time 헤더 → 오래된 순(첫 행 ≤ 마지막 행), 다시 → 최신 순 복귀", admin=True)
def l03_sort(ctx):
    ui = ctx.ui
    _open(ctx, "Log", "Palletizing Log")
    r0 = _log_rows(ui)
    check(len(r0) >= 2, "정렬을 볼 만큼 로그가 없음")
    check(r0[0][0] >= r0[-1][0], f"기본 정렬이 최신 순이 아님 ({r0[0][0]} … {r0[-1][0]})")
    ctx.step("Time 헤더 → 오래된 순 기대")
    ui.click(ui.top_find("Time"), settle=2, label="Time 정렬")
    r1 = _log_rows(ui)
    check(r1[0][0] <= r1[-1][0] and r1[0] != r0[0], f"오래된 순 정렬 안 됨 ({r1[0][0]} … {r1[-1][0]})")
    ctx.step("Time 헤더 다시 → 최신 순 복귀")
    ui.click(ui.top_find("Time"), settle=2, label="Time 정렬")
    check(_log_rows(ui)[0] == r0[0], "다시 눌렀는데 최신 순으로 돌아오지 않음")


@flow("L04", "로그 레벨 필터", "필터에서 Info를 끄면 Info 행이 사라지고, 다시 켜면 원래 행 수. 필터 버튼을 다시 누르면 닫힘", admin=True)
def l04_filter(ctx):
    ui = ctx.ui
    _open(ctx, "Log", "Palletizing Log")
    r0 = _log_rows(ui)
    title = ui.top_find("Palletizing Log", "Text")
    tr = title.rectangle()
    fb = min((b for b in ui.top_all("Button") if not b.window_text() and b.rectangle().left > tr.right
              and abs(_cy(b) - _cy(title)) < tr.height()), key=lambda b: b.rectangle().left, default=None)
    check(fb is not None, "필터 버튼 없음")
    ui.click(fb, settle=1.5, label="로그 필터")
    check(ui.wait_for(lambda: "Message Level" in ui.top_names(), 5), "필터 패널이 열리지 않음")
    ctx.step("Message Level 'Info' 끄기 → Info 행 사라짐 기대")
    ui.click(ui.top_find("Info"), settle=2, label="필터 Info")
    r1 = _log_rows(ui)
    check(all(r[1] != "Info" for r in r1), f"Info를 껐는데 Info 행이 남음 ({sum(r[1] == 'Info' for r in r1)}행)")
    ctx.step("'Info' 다시 켜기 → 원래 행 수")
    ui.click(ui.top_find("Info"), settle=2, label="필터 Info")
    check(len(_log_rows(ui)) == len(r0), f"Info를 다시 켰는데 행 수가 다름 ({len(r0)} → {len(_log_rows(ui))})")
    # 필터 창(CustomPopover)은 ESC 처리가 없고 바깥 클릭·필터 버튼 다시 누르기로 닫힘 (v2.0.0-21 소스 확인, 2026-10-27;
    # v1.2 TER-4369 "Filter 버튼을 다시 누르면 닫힘") → 필터 버튼을 다시 눌러 닫히는지 확인
    ctx.step("필터 버튼 다시 누르기 → 필터 창 닫힘 기대")
    ui.click(fb, settle=1.5, label="로그 필터 (닫기)")
    check(ui.wait_for(lambda: "Message Level" not in ui.top_names(), 4), "필터 버튼을 다시 눌렀는데 필터 창이 닫히지 않음")


@flow("L05", "로그 페이지 이동", "Next page → 2쪽(겹치는 행 없음, 앞쪽 버튼 활성), First page → 1쪽", admin=True)
def l05_page(ctx):
    ui = ctx.ui
    _open(ctx, "Log", "Palletizing Log")
    nxt = ui.top_find("Next page")
    if nxt is None or not nxt.is_enabled():
        raise NotApplicable("로그가 1쪽뿐")
    r1 = _log_rows(ui)
    ctx.step("Next page → 2쪽, 1쪽과 겹치는 행 없음 기대")
    ui.click(nxt, settle=2)
    r2 = _log_rows(ui)
    check(r2 and not set(r1) & set(r2), "2쪽 행이 1쪽과 겹침")
    check(ui.top_find("First page").is_enabled() and ui.top_find("Previous page").is_enabled(), "2쪽인데 앞쪽 이동 버튼 비활성")
    ctx.step("First page → 1쪽 복귀")
    ui.click(ui.top_find("First page"), settle=2)
    check(_log_rows(ui)[0] == r1[0] and not ui.top_find("First page").is_enabled(), "First page로 1쪽에 돌아오지 않음")


# ================================================================ Settings
SET_SUB = {"General": "Solution Version", "Conveyor": "Conveyor Direction", "Pallet": "Pallet Overhang",
           "Tool": "Add Tool", "Slipsheet": "Thickness", "Account": "Account List",
           "Remote CS": "Remote Service", "Backup & Restore": "Export Backup Data"}


def _settings(ctx, sub="General"):
    _open(ctx, "Settings", "Backup & Restore")
    ui = ctx.ui
    ui.click(ui.top_find(sub), settle=2, label=f"Settings {sub}")
    check(ui.wait_for(lambda: SET_SUB[sub] in ui.top_names(), 6), f"Settings '{sub}' 화면 내용이 없음 ('{SET_SUB[sub]}')")


@flow("S01", "Settings General 정보", "Solution Version = 화면 버전, Serial 'Virtual', Language English, 변경 없으면 Save 비활성", admin=True)
def s01_general(ctx):
    ui = ctx.ui
    _settings(ctx, "General")
    ts = [t.window_text() for t in ui.top_all("Text") if t.rectangle().width() > 0]
    i = ts.index("Solution Version")
    ver = "".join(ts[i + 1:i + 3]).replace(" ", "")
    want = ctx.info.get("palletizos_version")
    ctx.step(f"Solution Version {ver} ↔ Home 표시 {want}")
    check(re.fullmatch(r"v\d+\.\d+\.\d+", ver or ""), f"Solution Version 표시 이상: {ver!r}")
    if want:
        check(ver == want, f"Solution Version {ver} ≠ Home 표시 {want}")
    check(ts.count("Virtual") >= 2, "Controller/Robot Serial이 'Virtual'로 표시되지 않음 (가상 제어기)")
    check(ui.top_find("English") is not None, "Language가 English가 아님")
    check(not ui.top_find("Save").is_enabled(), "아무것도 바꾸지 않았는데 Save가 활성")


@flow("S02", "Settings 미저장 변경 감지", "Unit을 바꾸면 Save 활성, 원래대로 되돌리면 다시 비활성 (저장하지 않음)", admin=True)
def s02_dirty(ctx):
    ui = ctx.ui
    _settings(ctx, "General")
    radios = [r for r in ui.top_all("RadioButton") if r.element_info.name]
    check(len(radios) >= 2, "Unit 선택 항목 없음")
    cur = next(r for r in radios if _selected(r))
    other = next(r for r in radios if not _selected(r))
    cur_n, other_n = cur.element_info.name, other.element_info.name
    ctx.step(f"Unit '{other_n}' 선택 → Save 활성 기대")
    ui.click(other, settle=1.5, label=f"Unit {other_n}")
    check(ui.top_find("Save").is_enabled(), "값을 바꿨는데 Save가 활성화되지 않음")
    ctx.step(f"Unit '{cur_n}'(으)로 되돌리기 → Save 비활성 기대")
    ui.click(ui.top_find(cur_n, "RadioButton"), settle=1.5, label=f"Unit {cur_n}")
    check(_selected(ui.top_find(cur_n, "RadioButton")), "원래 Unit으로 되돌아가지 않음")
    check(not ui.top_find("Save").is_enabled(), "원래 값으로 되돌렸는데 Save가 계속 활성")


@flow("S03", "Settings 하위 메뉴", "General·Conveyor·Pallet·Tool·Slipsheet·Account·Remote CS·Backup & Restore 8개 화면이 각각 열림", admin=True)
def s03_subs(ctx):
    ui = ctx.ui
    _open(ctx, "Settings", "Backup & Restore")
    for sub, anchor in SET_SUB.items():
        ctx.step(f"'{sub}' → '{anchor}' 표시 확인")
        ui.click(ui.top_find(sub), settle=2, label=f"Settings {sub}")
        check(ui.wait_for(lambda: anchor in ui.top_names(), 6), f"Settings '{sub}' 화면 내용이 없음 ('{anchor}')")
    ui.click(ui.top_find("General"), settle=1.5, label="Settings General")


@flow("S04", "Settings Tool 목록", "툴 개수 표시(n/최대) = 목록 행 수, 행 선택 시 이름 입력칸 = 선택한 툴", admin=True)
def s04_tool(ctx):
    ui = ctx.ui
    _settings(ctx, "Tool")
    ts = [t for t in ui.top_all("Text") if t.rectangle().width() > 0]
    slash = next((t for t in ts if t.window_text() == "/" and t.rectangle().top < ui.top_find("Add Tool").rectangle().bottom + 120), None)
    check(slash is not None, "툴 개수 표시(n / 최대) 없음")
    seq = [t.window_text() for t in _same_row(ts, slash)]
    n = int(seq[seq.index("/") - 1])
    rows = [b for b in ui.top_all("Button") if (b.window_text() or "").endswith(" menu") and b.window_text() != "menu"]
    ctx.step(f"개수 표시 {n} ↔ 목록 {len(rows)}행")
    check(n == len(rows), f"툴 개수 표시 {n} ≠ 목록 행 수 {len(rows)}")
    name = rows[0].window_text()[:-5]
    ui.click(rows[0], settle=1.5, label=f"툴 {name}")
    vals = [e.iface_value.CurrentValue for e in ui.top_all("Edit") if e.element_info.name == name]
    check(vals and vals[0] == name, f"툴 '{name}'을(를) 골랐는데 이름 입력칸이 다름 ({vals})")
    check(not ui.top_find("Save").is_enabled(), "툴을 고르기만 했는데 Save가 활성")


@flow("S05", "Settings Account 목록", "계정 목록에 Admin·Operator와 현재 로그인 계정 표시, Add Account 버튼 존재", admin=True)
def s05_account(ctx):
    ui = ctx.ui
    _settings(ctx, "Account")
    rows = [re.match(r"^[A-Z] (?:\(\w+\) )?(\w+)", b.window_text()).group(1) for b in ui.top_all("Button")
            if re.match(r"^[A-Z] (?:\(\w+\) )?\w+ .*menu$", b.window_text() or "")]
    ctx.step(f"계정 목록 {rows}")
    check({"Admin", "Operator"} <= set(rows), f"계정 목록에 Admin/Operator 없음 ({rows})")
    check(ui.top_find("Add Account") is not None, "Add Account 버튼 없음")


# ================================================================ Jog + / Quick Log / Recovery
@flow("J01", "Jog + 패널", "Jog + 패널 열림 → Jog·Move·Align 탭 전환(선택 상태) → J1~J6 표시 → X로 닫힘")
def j01_jog(ctx):
    ui = ctx.ui
    if ui.has_menu("Jog +") is False:  # v2.0.0에는 이 메뉴가 없음 (Robot Control 등으로 바뀜)
        raise NotApplicable("이 버전에는 'Jog +' 메뉴가 없음")
    ui.goto("Jog +")
    check(ui.wait_for(lambda: ui.dialog_open("Jog +"), 6), "Jog + 패널이 열리지 않음")
    for tab in ("Move", "Align", "Jog"):
        ctx.step(f"'{tab}' 탭 선택 확인")
        ui.click(ui.top_find(tab, "TabItem"), settle=1.5, label=f"Jog 탭 {tab}")
        check(_selected(ui.top_find(tab, "TabItem")), f"'{tab}' 탭이 선택 상태가 아님")
    joints = {f"J{i}" for i in range(1, 7)}
    check(joints <= {e.element_info.name for e in ui.top_all("Button")}, "Jog 탭에 J1~J6 버튼 없음")
    ctx.step("X로 패널 닫기")
    check(ui.close_panel("Jog +") and not ui.dialog_open("Jog +"), "Jog + 패널이 닫히지 않음")


@flow("Q01", "Quick Log 패널", "Quick Log 패널 열림(검색·Copy·Clear) → 검색 입력 반영 → X로 닫힘 (Clear는 누르지 않음)")
def q01_quicklog(ctx):
    ui = ctx.ui
    if ui.has_menu("Quick Log") is False:  # v2.0.0에는 이 메뉴가 없음 (Robot Control 등으로 바뀜)
        raise NotApplicable("이 버전에는 'Quick Log' 메뉴가 없음")
    ui.goto("Quick Log")
    check(ui.wait_for(lambda: ui.dialog_open("Quick Log"), 6), "Quick Log 패널이 열리지 않음")
    n = ui.top_names()
    check({"Copy", "Clear", "Search logs"} <= n, f"Quick Log 구성 요소 누락: {sorted({'Copy', 'Clear', 'Search logs'} - n)}")
    edit = ui.top_find("Search logs", "Edit")
    ctx.step("검색창 입력 반영 확인")
    _type(ui, edit, "Servo", "Quick Log 검색")
    check(edit.iface_value.CurrentValue == "Servo", "검색어가 입력되지 않음")
    _type(ui, edit, "", "검색어 지우기")
    ctx.info["quicklog_empty"] = "No matching results" in ui.top_names()
    check(ui.close_panel("Quick Log") and not ui.dialog_open("Quick Log"), "Quick Log 패널이 닫히지 않음")


@flow("V01", "Recovery 모듈", "Recovery → 복구 모듈(관절 J1~J6·탭 2개) 진입·로그 'Recovery enter' → Exit → Home 복귀·값 유지")
def v01_recovery(ctx):
    ui = ctx.ui
    base = ui.snapshot()
    rec = ui.by_name("Recovery")
    if rec is None:
        r = ui.rail()
        rec = r[-2] if len(r) >= 2 else None
    ctx.step("Recovery → 복구 모듈 진입")
    ui.click(rec, settle=3, label="Recovery")
    check(ui.wait_for(lambda: "Exit Recovery Module" in ui.top_names(), 10), "Recovery 모듈이 열리지 않음")
    n = ui.top_names()
    joints = [e for e in ui.top_all("ListItem") if re.match(r"^J[1-6]-?\d", e.element_info.name or "")]
    check(len(joints) == 6, f"관절 값 J1~J6 표시 이상 ({len(joints)}개)")
    check({"Software Recovery", "Pack/Unpack"} <= n, "Recovery 탭(Software Recovery·Pack/Unpack) 없음")
    check(ui.wait_for(lambda: ctx.log.saw(r"\[ModuleLog\].*Recovery enter"), 5), "로그에 'Recovery enter' 없음")
    ctx.step("Exit Recovery Module → PalletizOS Home 복귀·값 유지")
    ui.click(ui.top_find("Exit Recovery Module"), settle=3)
    check(ui.wait_for(ui.on_home, 10), "Recovery에서 나왔는데 Home으로 돌아오지 않음")
    check(ui.wait_for(lambda: ui.snapshot() == base, 8), "Recovery를 다녀온 뒤 Home 값이 달라짐")
