"""PalletizOS Home 스모크 흐름. 흐름 하나 = 함수 하나.

각 함수는 실패 시 AssertionError를 던진다. 판정 근거는 2026-10-19 실측 동작(DESIGN.md)이다.
기대값은 고정 숫자가 아니라 출발 값 기준 상대 변화로 정의한다.
"""
import re
import time

from .ui import EL, P, pause

FLOWS = []

# 실행 중 오버레이 칩에 번호와 함께 보이는 짧은 이름
SHORT = {"H01": "진입", "H02": "토글", "H03": "레시피", "H04": "층±", "H05": "박스±", "H06": "3D확대",
         "H07": "Enable", "H08": "진공·홈",
         "R01": "목록", "R02": "선택", "R03": "검색", "R04": "⋮메뉴", "R05": "편집기",
         "I01": "탭", "I02": "DO", "I03": "Flange", "I04": "Modbus",
         "L01": "최신", "L02": "검색", "L03": "정렬", "L04": "필터", "L05": "페이지",
         "S01": "정보", "S02": "Save", "S03": "하위", "S04": "Tool", "S05": "계정",
         "J01": "Jog+", "Q01": "QLog", "V01": "Recovery"}


class NotApplicable(Exception):
    """현재 화면/레이아웃에 해당 컨트롤이 없어 판정 대상이 아님."""


def flow(tc, title, desc, admin=False):
    """admin=True: Admin 계정에서만 보이는 메뉴(Recipes·Log·Settings)를 쓰는 흐름."""
    def deco(fn):
        FLOWS.append({"tc": tc, "title": title, "desc": desc, "fn": fn, "admin": admin})
        return fn
    return deco


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _pct(n, total):
    """진행률 표시 기대값 = 버림. 제품 MonitoringPalletInfo.tsx: Math.floor(box / maxBoxCount * 100)
    (v1.2.0-2 · v2.0.0-10/-17/-21 소스 확인, 2026-10-27). 예전엔 반올림을 기대해 71/288=24.65% → 24 vs 25로 H05 오판"""
    return str(int(n * 100 // total)) if total else "0"


def _active_side(ctx):
    """켜져 있는 열 (Right 우선). 없으면 None."""
    snap = ctx.snap0
    for s in ("Right", "Left"):
        if snap[s]["on"]:
            return s
    return None


def _check_model(c, where):
    """N 모델과 화면 표시(진행률, 버튼 활성)가 일치하는지."""
    n, total = c["n"], c["total"]
    check(c["progress"] == _pct(n, total), f"{where}: 진행률 {c['progress']}% ≠ 기대 {_pct(n, total)}% (N={n}/{total})")
    check(c["en"]["layer-"] == (n > 0) and c["en"]["boxes-"] == (n > 0),
          f"{where}: [−] 활성 상태 이상 (N={n}, layer-={c['en']['layer-']}, boxes-={c['en']['boxes-']})")
    check(c["en"]["layer+"] == (n < total) and c["en"]["boxes+"] == (n < total),
          f"{where}: [+] 활성 상태 이상 (N={n}/{total}, layer+={c['en']['layer+']}, boxes+={c['en']['boxes+']})")


def _no_error_popup(ui, before, where):
    errs = ui.error_texts(before, ui.window_texts())
    check(not errs, f"{where}: 에러 문구 표시 {errs}")


# ---------------------------------------------------------------- P01
@flow("H01", "화면 진입", "PalletizOS Home 화면 표시, 버전 확인, 핵심 요소 존재")
def p01_entry(ctx):
    ui = ctx.ui
    ctx.step("화면 버전 표시 확인")
    ver = ui.version()
    check(ver and re.fullmatch(r"v\d+\.\d+\.\d+", ver), f"PalletizOS 버전 표시 없음: {ver!r}")
    ctx.info["palletizos_version"] = ver
    if ctx.expect_version:
        want = ctx.expect_version if ctx.expect_version.startswith("v") else "v" + ctx.expect_version
        # 화면은 'v2.0.0' 까지만 표시하고 데일리 빌드 번호(-23)는 없음 → 화면은 앞부분만 비교하고, 빌드 번호는 앱 로그로 확인
        # (2026-10-29: 기대 v2.0.0-23 을 화면 v2.0.0 과 통째로 비교해 정상 설치를 FAIL 로 판정)
        base, _, build = want.partition("-")
        check(ver == base, f"설치 버전 불일치: 화면 {ver}, 기대 {base}")
        if build:
            from .installer import installed_version
            got = installed_version()
            ctx.info["palletizos_build"] = got
            check(got == want[1:], f"설치 빌드 불일치: 앱 로그 {got}, 기대 {want[1:]}")
    ctx.step("Home 핵심 요소(층·박스·진행률·버튼) 존재 확인")
    have = ui.visible_texts()
    for name in (P["current_layer"], P["boxes_on_layer"], P["progress"], P["release_vacuum"]):
        check(name in have, f"Home 화면 요소 없음: {name}")
    check(ui.go_home_button() is not None, "Go To Home Position 버튼 없음 (이름 버튼/아이콘 모두)")
    check(ui.enable_button_name() in (P["enable_robot"], DISABLE), f"Enable/Disable Robot 버튼 없음 ({ui.enable_button_name()})")
    check(set(ui.sides()) == set(P["side_labels"]), "Left/Right 열 해석 실패")


# ---------------------------------------------------------------- P02
@flow("H02", "Left/Right 토글", "토글 On/Off에 따라 해당 열의 레시피·진행률 영역이 활성/비활성")
def p02_toggle(ctx):
    ui = ctx.ui
    for side in P["side_labels"]:
        start = ctx.snap0[side]
        onoff = "켜기" if not start["on"] else "끄기"
        ctx.step(f"{side} 토글 {onoff} → 레시피·진행률 영역이 {'활성' if not start['on'] else '비활성'}되는지")
        before = ui.window_texts()
        ui.click(ui.sides()[side].toggle, settle=2, label=f"{side} 토글")
        snap = ui.snapshot()[side]
        check(snap["on"] == (not start["on"]), f"{side} 토글 상태가 바뀌지 않음 ({start['on']} → {snap['on']})")
        if snap["on"]:
            check(snap["recipe_enabled"], f"{side} 켰는데 레시피 버튼 비활성")
            check(snap["progress"] not in (None, "-"), f"{side} 켰는데 진행률 표시 없음 ({snap['progress']})")
            check(snap["layer"][0] not in ("", None), f"{side} 켰는데 층 값 없음")
        else:
            check(not snap["recipe_enabled"], f"{side} 껐는데 레시피 버튼 활성")
            check(snap["progress"] == "-", f"{side} 껐는데 진행률 표시 남음 ({snap['progress']})")
        _no_error_popup(ui, before, f"{side} 토글")
        ctx.step(f"{side} 토글 원래대로 되돌리고 값 복구")
        ui.click(ui.sides()[side].toggle, settle=2, label=f"{side} 토글")
        check(ui.snapshot()[side]["on"] == start["on"], f"{side} 토글 원복 실패")
        ctx.restore_side(side)


# ---------------------------------------------------------------- P03
@flow("H03", "레시피 선택", "Select Recipe 대화상자: 취소 시 유지, 다른 레시피 적용 시 표시 변경, 원래 레시피 복귀")
def p03_recipe(ctx):
    ui = ctx.ui
    side = _active_side(ctx)
    if side is None:
        raise NotApplicable("켜진 열이 없어 레시피를 선택할 수 없음")
    orig = ctx.snap0[side]["recipe"]

    # 1) 열고 Cancel → 그대로
    ctx.step(f"{side} 레시피 대화상자 열고 Cancel → 레시피 그대로인지")
    ui.click(ui.sides()[side].recipe, settle=2, label=f"{side} 레시피 선택")
    check(ui.dialog_open(), "레시피 버튼을 눌렀는데 Select Recipe 대화상자가 안 열림")
    ui.click(ui.win_button("Cancel"), settle=1.5)
    check(not ui.dialog_open(), "Cancel 후에도 대화상자가 남아 있음")
    check(ui.sides()[side].recipe.window_text() == orig, "Cancel 했는데 레시피가 바뀜")

    # 2) 다른 레시피(오류 아이콘 없는 것) 적용
    ui.click(ui.sides()[side].recipe, settle=2, label=f"{side} 레시피 선택")
    ui.wait_for(lambda: len(ui.recipe_items()) > 0, 6)  # 목록은 대화상자가 뜬 뒤 늦게 채워짐
    items = ui.recipe_items()
    cands = [(n, b) for n, b, bad in items if n != orig and not bad]
    if not cands:
        ui.click(ui.win_button("Cancel"), settle=1.5)
        raise NotApplicable(f"바꿔 볼 정상 레시피가 없음 (목록: {[n for n, _, _ in items]})")
    name, btn = cands[0]
    ctx.step(f"다른 레시피 {name} 적용 → 표시 변경·진행 초기화(N=0) 확인")
    before = ui.window_texts()
    ui.click(btn, settle=1.5)
    ui.click(ui.win_button("Apply"), settle=2.5)
    check(not ui.dialog_open(), "Apply 후에도 대화상자가 남아 있음")
    check(ui.sides()[side].recipe.window_text() == name, f"레시피 표시가 {name}(으)로 바뀌지 않음")
    c = ui.counter(side)
    check(c["n"] == 0, f"새 레시피 적용 후 진행 상태가 초기화되지 않음 (N={c['n']})")
    _check_model(c, f"레시피 {name} 적용 직후")
    _no_error_popup(ui, before, "레시피 적용")

    # 3) 원래 레시피로 복귀
    ctx.step(f"원래 레시피 {orig}(으)로 되돌리기")
    ui.click(ui.sides()[side].recipe, settle=2, label=f"{side} 레시피 선택")
    orig_btn = next((b for n, b, _ in ui.recipe_items() if n == orig), None)
    check(orig_btn is not None, f"목록에 원래 레시피 {orig} 없음")
    ui.click(orig_btn, settle=1.5)
    ui.click(ui.win_button("Apply"), settle=2.5)
    check(ui.sides()[side].recipe.window_text() == orig, f"원래 레시피 {orig}(으)로 복귀 실패")
    ctx.restore_side(side)


# ---------------------------------------------------------------- P04
@flow("H04", "Current Layer +/−", "층 [+]는 다음 층 경계로, [−]는 이전 경계로. 끝에서 버튼 비활성. 진행률 일치")
def p04_layer(ctx):
    ui = ctx.ui
    side = _active_side(ctx)
    if side is None:
        raise NotApplicable("켜진 열이 없음")
    c = ui.counter(side)
    _check_model(c, "시작")
    total, bm = c["total"], c["bm"]
    for _ in range(c["layers"] + 1):           # [+]를 끝까지
        if not c["en"]["layer+"]:
            break
        n = c["n"]
        want = min((n // bm + 1) * bm, total)
        ctx.step(f"층 [+] → 완료 박스 N {n}→{want}, 진행률 {_pct(want, total)}% 기대")
        ui.press(side, "layer+")
        c = ui.counter(side)
        check(c["n"] == want, f"층 [+]: N {n} → {c['n']} (기대 {want})")
        _check_model(c, f"층 [+] 후 N={c['n']}")
    check(c["n"] == total, f"층 [+]를 끝까지 눌렀는데 N={c['n']} ≠ 전체 {total}")
    for _ in range(c["layers"] + 1):           # [−]를 끝까지
        if not c["en"]["layer-"]:
            break
        n = c["n"]
        want = (n - 1) // bm * bm if n % bm else n - bm
        ctx.step(f"층 [−] → 완료 박스 N {n}→{want}, 진행률 {_pct(want, total)}% 기대")
        ui.press(side, "layer-")
        c = ui.counter(side)
        check(c["n"] == want, f"층 [−]: N {n} → {c['n']} (기대 {want})")
        _check_model(c, f"층 [−] 후 N={c['n']}")
    check(c["n"] == 0, f"층 [−]를 끝까지 눌렀는데 N={c['n']} ≠ 0")
    ctx.step(f"끝(0)에서 [−] 비활성 확인 완료 → 원래 값으로 복구")
    ctx.restore_side(side)


# ---------------------------------------------------------------- P05
@flow("H05", "Boxes on Layer +/−", "박스 [+]/[−]는 N±1, 층 경계에서 다음 층으로 넘어감, 진행률 일치")
def p05_boxes(ctx):
    ui = ctx.ui
    side = _active_side(ctx)
    if side is None:
        raise NotApplicable("켜진 열이 없음")
    c = ui.counter(side)
    order = ["boxes-", "boxes+"] if c["n"] > 0 else ["boxes+", "boxes-"]
    for key in order:
        n = c["n"]
        want = n + (1 if key == "boxes+" else -1)
        ctx.step(f"박스 [{key[-1]}] → N {n}→{want}, 진행률 {_pct(want, c['total'])}% 기대")
        ui.press(side, key)
        c = ui.counter(side)
        check(c["n"] == want, f"박스 {key[-1]}: N {n} → {c['n']} (기대 {want})")
        _check_model(c, f"박스 {key[-1]} 후 N={c['n']}")
    if c["layers"] > 1:                         # 층 경계 넘김: N=bm에서 [+] → 2층 1개
        ctx.step(f"1층 꽉 찬 상태({c['bm']}/{c['bm']})에서 박스 [+] → 2층 1개로 넘어가는지")
        ui.set_n(side, c["bm"])
        ui.press(side, "boxes+")
        s = ui.sides()[side]
        check(s.layer["value"] == "2" and s.boxes["value"] == "1",
              f"층 경계 넘김 이상: {s.layer['value']}층 {s.boxes['value']}개 (기대 2층 1개)")
    ctx.restore_side(side)


# ---------------------------------------------------------------- H06
ZOOM = re.compile(r"^\d+%$")


def _zoom_button(ui):
    return next((b for b in ui._all(None, "Button") if ZOOM.match(b.window_text() or "")), None)


@flow("H06", "3D 뷰 확대", "3D 뷰 확대 드롭다운: 다른 비율 선택 → 표시 반영 → 원래 비율 복귀 (2D 레이아웃이면 해당없음)")
def h06_zoom(ctx):
    ui = ctx.ui
    z = _zoom_button(ui)
    if z is None:
        raise NotApplicable("현재 레이아웃(큰 화면 2D 개요)에는 3D 뷰 확대 컨트롤이 없음")
    orig = z.window_text()
    ui.click(z, settle=1.5, label=f"3D 확대 {orig}")
    opts = [o for o in ui.top_all("ListItem") if ZOOM.match(o.element_info.name or "")]
    check(len(opts) >= 2, f"확대 선택지가 부족함 ({[o.element_info.name for o in opts]})")
    pick = next(o for o in opts if o.element_info.name != orig)
    name = pick.element_info.name
    ctx.step(f"확대 {orig} → {name} 선택 → 표시 반영 기대")
    ui.click(pick, settle=1.5, label=f"확대 {name}")
    check(ui.wait_for(lambda: (_zoom_button(ui) or z).window_text() == name, 5), f"확대 표시가 {name}(으)로 바뀌지 않음")
    ctx.step(f"원래 비율 {orig}(으)로 복귀")
    ui.click(_zoom_button(ui), settle=1.5, label=f"3D 확대 {name}")
    ui.click(next(o for o in ui.top_all("ListItem") if o.element_info.name == orig), settle=1.5, label=f"확대 {orig}")
    check(ui.wait_for(lambda: _zoom_button(ui).window_text() == orig, 5), f"확대 비율 {orig} 복귀 실패")


# ---------------------------------------------------------------- P07
DISABLE = "Disable Robot"


def _flip_robot(ctx, where):
    """Enable↔Disable 한 번 전환하고 버튼 이름·상태 문구·ModuleLog(Servo ON/OFF)를 확인."""
    ui, log = ctx.ui, ctx.log
    cur = ui.enable_button_name()
    nxt, servo = (DISABLE, "Servo ON") if cur == P["enable_robot"] else (P["enable_robot"], "Servo OFF")
    status0 = ui.robot_status()
    ctx.step(f"{where}: '{cur}' → 버튼 '{nxt}'·상태 문구 변경·로그 '{servo}' 확인")
    before = ui.window_texts()
    ui.click(ui.by_name(cur), settle=2)
    check(ui.wait_for(lambda: ui.enable_button_name() == nxt, 10), f"{where}: '{cur}' 후 버튼이 '{nxt}'(으)로 안 바뀜")
    check(ui.robot_status() != status0, f"{where}: '{cur}' 후 상태 문구가 그대로 ({status0})")
    check(ui.wait_for(lambda: log.saw(rf"\[ModuleLog\].*{servo}"), 5), f"{where}: 로그에 '{servo}' 없음")
    _no_error_popup(ui, before, f"{where} {cur}")


@flow("H07", "Enable/Disable Robot", "Enable ↔ Disable 전환: 버튼 이름·상태 문구 변경, Servo ON/OFF 로그, 다시 눌러 원복")
def p07_enable(ctx):
    ui = ctx.ui
    start, status0 = ui.enable_button_name(), ui.robot_status()
    _flip_robot(ctx, "1차 전환")
    _flip_robot(ctx, "원복 전환")
    check(ui.enable_button_name() == start and ui.robot_status() == status0,
          f"원복 후 상태가 출발과 다름 ({ui.enable_button_name()}, {ui.robot_status()})")


# ---------------------------------------------------------------- P09
@flow("H08", "Release Vacuum·홈 이동", "로봇 Enable 상태에서 Release Vacuum·Go To Home Position이 에러 없이 수행되고 로그에 기록")
def p09_actions(ctx):
    ui, log = ctx.ui, ctx.log
    was_enabled = ui.enable_button_name() == DISABLE
    if not was_enabled:
        ctx.step("사전 조건: 로봇 Enable")
        ui.click(ui.by_name(P["enable_robot"]), settle=2)
        check(ui.wait_for(lambda: ui.enable_button_name() == DISABLE, 10), "Enable 실패 (사전 조건)")
    ctx.step("Release Vacuum → 에러 없이 로그 'Release vacuum' 기록되는지")
    before = ui.window_texts()
    ui.click(ui.by_name(P["release_vacuum"]), settle=1.5)
    check(ui.wait_for(lambda: log.saw(r"\[ModuleLog\].*Release vacuum"), 5), "로그에 'Release vacuum' 없음")
    _no_error_popup(ui, before, "Release Vacuum")
    ctx.step("Go To Home Position → 이동 시작(로그 'Move home')·45초 안에 완료되는지")
    before = ui.window_texts()
    # Release Vacuum 직후 홈 이동 아이콘이 잠깐 비활성 → 바로 누르면 '비활성 요소 클릭'으로 1차 실패(재시도 때 통과)했음 (2026-10-22 실측)
    check(ui.wait_for(lambda: ui.go_home_button() is not None and ui.go_home_button().is_enabled(), 10),
          "Go To Home Position 버튼이 10초 안에 활성화되지 않음")
    ui.click(ui.go_home_button(), settle=1, label="Go To Home Position")
    check(ui.wait_for(lambda: log.saw(r"\[ModuleLog\].*Move home"), 5), "로그에 'Move home' 없음")
    done = ui.wait_for(lambda: ui.by_name(P["release_vacuum"]) is not None and ui.by_name("Stop") is None, 45, 1)
    check(done, "홈 이동이 45초 안에 끝나지 않음 (Pause/Stop 상태 유지)")
    _no_error_popup(ui, before, "Go To Home Position")
    if not was_enabled:
        ctx.step("원복: 로봇 Disable")
        ui.click(ui.by_name(DISABLE), settle=2)
        check(ui.wait_for(lambda: ui.enable_button_name() == P["enable_robot"], 10), "Disable 실패 (원복)")
