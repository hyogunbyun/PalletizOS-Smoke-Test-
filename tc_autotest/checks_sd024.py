"""SD024 Slipsheet Image Setting — TC Lite V2.1 (SR024) 자동 판정 루틴.

화면 값·경계 보정·저장·재기동 유지·이탈 팝업은 자동으로 확인한다. 3D 뷰의 색·질감·홀더 표시처럼 눈으로만
볼 수 있는 기대는 확인하지 못하므로 ctx.note 를 '[부분]' 으로 시작해 '부분 자동'으로 기록한다(Result 는 NT).
모든 루틴은 시작 때의 Slipsheet 설정·단위를 기억했다가 끝나면 원래대로 저장해 둔다.
"""
from autotest import secret
from autotest.flows import NotApplicable, check

from .checks import tc_check
from .helpers import COLORS, Slip, _num, ensure_role, leave_and, save, save_enabled, set_unit, settings, text_el

SR = "sr024"


def _run(ctx, unit, body, pre=None):
    """공통 틀: Admin → 단위 맞춤 → Slipsheet 진입·원래 값 기억 → (전제 저장) → body → 원래대로."""
    ensure_role(ctx, secret.LOGIN_ACCOUNT)
    unit0 = set_unit(ctx, unit) if unit else None
    s = Slip(ctx)
    s.open()
    snap0 = s.snapshot()
    ctx.step(f"시작 값 기억: {snap0}")
    try:
        if pre:
            s.apply(pre)
        body(s)
    finally:
        try:
            s.open()  # 미저장 편집은 Discard & Exit
            if s.snapshot() != snap0:
                s.apply(snap0)
        finally:
            if unit0:
                set_unit(ctx, unit0)


def _disabled_rows(s):
    names = ("Width", "Length", "Thickness")
    return [n for n in names if s.edit(n).is_enabled()]


@tc_check("SD024_01", "SD024-1 기본 상태 · 색 목록",
          "토글 Off·행 비활성, Paper·Warm Gray·914.4·1097.3·2.5, 토글 On 후 색 5개 순서",
          [(SR, "초기값", "색 목록")], admin=False)
def sd024_01(ctx):
    def body(s):
        ctx.step("토글 Off · 아래 행 비활성 확인")
        if s.is_on():  # 전제조건(한 번도 저장 안 한 초기 상태)을 만족하지 않음 — 결함이 아니므로 판정 대상 아님
            raise NotApplicable("전제조건 불충족: 이 장비는 Slipsheet 설정을 이미 저장함(토글 On) — Initialize 후에만 판정 가능")
        en = _disabled_rows(s)
        check(not en, f"토글 Off 인데 활성인 행: {en}")
        got = {"Type": s.type_selected(), "Color": s.color(), "Width": s.value("Width"),
               "Length": s.value("Length"), "Thickness": s.value("Thickness")}
        ctx.step(f"초기값 {got}")
        want = {"Type": "Paper", "Color": "Warm Gray", "Width": "914.4", "Length": "1097.3", "Thickness": "2.5"}
        bad = {k: got[k] for k in want if str(got[k]) != want[k]}
        check(not bad, f"초기값이 다름: {bad} (기대 {want})")
        s.set_on(True)
        items = [e.window_text() for e in s.color_items()]
        ctx.ui.esc()
        ctx.step(f"색 목록 {items}")
        check(items == list(COLORS), f"색 목록 {items} (기대 {list(COLORS)})")
        ctx.note = "[부분] 화면 값·색 목록 5개 순서 통과 · 색 스와치 모양은 눈으로 확인 필요"
    _run(ctx, "Metric", body)


@tc_check("SD024_02", "SD024-2 색·크기 저장 · 재기동 후 유지",
          "같은 색 다시 고르면 Save 비활성, Teal 고르면 Save 활성, Width 700 저장, 모듈 재기동 후 Teal·700.0",
          [(SR, "편집 즉시 반영"), (SR, "재기동 후 유지")], admin=False)
def sd024_02(ctx):
    pre = {"on": True, "type": "Cardboard", "color": "Warm Gray", "Width": "914.4", "Length": "1097.3"}

    def body(s):
        ui = ctx.ui
        s.pick_color("Warm Gray")
        ctx.step("저장된 색을 다시 고름 → Save 비활성 기대")
        check(not save_enabled(ui), "같은 색을 다시 골랐는데 Save 가 활성")
        s.pick_color("Teal")
        check(save_enabled(ui), "Teal 로 바꿨는데 Save 가 비활성")
        v = s.type("Width", "700")
        ctx.step(f"Width 700 → 표시 {v}")
        save(ctx)
        ctx.step("모듈 재기동 (Exit Module → 다시 열기)")
        _restart_module(ctx)
        s.open()
        got = (s.color(), s.value("Width"))
        ctx.step(f"재기동 후 Color {got[0]} · Width {got[1]}")
        check(got[0] == "Teal", f"재기동 후 Color {got[0]} (기대 Teal)")
        check(_num(got[1]) == 700.0 and got[1] == "700.0", f"재기동 후 Width {got[1]!r} (기대 '700.0')")
        ctx.note = "[부분] Save 활성/비활성·저장·재기동 유지 통과 · 3D 홀더/팔레트 시트 색·크기는 눈으로 확인 필요"
    _run(ctx, "Metric", body, pre)


def _restart_module(ctx):
    from autotest import env
    ui = ctx.ui
    settings(ctx, "General")
    ui.click(ui.top_find("Exit Module"), settle=4, label="Exit Module")
    for c in ("Confirm", "OK", "Yes", "Exit"):
        b = ui.top_find(c)
        if b is not None:
            ui.click(b, settle=4, label=f"종료 확인 {c}")
            break
    env.ensure_ready(ui, ctx.step)
    ui.remember_nav()


@tc_check("SD024_03", "SD024-3 Type 변경 시 색 유지",
          "Teal·Cardboard 저장 상태에서 Paper 선택 → Color 는 Teal 유지 (질감 변화는 눈으로)",
          [(SR, "질감만 변경")], admin=False)
def sd024_03(ctx):
    pre = {"on": True, "type": "Cardboard", "color": "Teal"}

    def body(s):
        s.set_type("Paper")
        ctx.step(f"Paper 선택 후 Color {s.color()}")
        check(s.type_selected() == "Paper", "Paper 가 선택되지 않음")
        check(s.color() == "Teal", f"Type 을 바꿨더니 Color 가 {s.color()} (기대 Teal 유지)")
        ctx.note = "[부분] Color 유지 통과 · 골판지 질감 표시/사라짐은 눈으로 확인 필요"
    _run(ctx, "Metric", body, pre)


@tc_check("SD024_04", "SD024-4 Width·Length·Thickness 경계 보정",
          "600→609.6, 609.6, 1301→1300.0, 1300, 101→100.0, 0→0.0 (mm)",
          [(SR, "범위 밖 보정")], admin=False)
def sd024_04(ctx):
    def body(s):
        s.set_on(True)
        cases = [("Width", "600", "609.6"), ("Width", "609.6", "609.6"), ("Length", "1301", "1300.0"),
                 ("Length", "1300", "1300.0"), ("Thickness", "101", "100.0"), ("Thickness", "0", "0.0")]
        bad = []
        for f, v, want in cases:
            got = s.type(f, v)
            ctx.step(f"{f} {v} → {got} (기대 {want})")
            if str(got) != want:
                bad.append(f"{f} {v}→{got} (기대 {want})")
        errs = [t.window_text() for t in ctx.ui.top_all("Text") if "must be" in (t.window_text() or "") or "range" in (t.window_text() or "").lower()]
        check(not bad, "경계 보정 다름: " + "; ".join(bad))
        check(not errs, f"오류 문구 표시: {errs}")
        ctx.note = "[부분] 입력 경계 보정 6건 통과 · Width 1300 저장 후 레시피 3D 시트 표시는 눈으로 확인 필요"
    _run(ctx, "Metric", body)


@tc_check("SD024_05", "SD024-5 토글 Off/On · 이탈 팝업",
          "Pink + 토글 Off → 입력 비활성, On → 활성·Pink 유지, 이탈 시 Unsaved Changes → Cancel 은 남음, Discard & Exit 후 Warm Gray",
          [(SR, "이탈 팝업")], admin=False)
def sd024_05(ctx):
    pre = {"on": True, "type": "Cardboard", "color": "Warm Gray", "Width": "36.00", "Length": "43.20"}

    def body(s):
        ui = ctx.ui
        s.pick_color("Pink")
        s.set_on(False)
        en = [e.window_text() for e in ui.top_all("Edit") if e.rectangle().left > 1150 and e.is_enabled()]
        btn = [b.window_text() for b in ui.top_all("Button") if b.window_text() in ("Get Pose", "Move To", "Move To Seek Start Position") and b.is_enabled()]
        ctx.step(f"토글 Off: 활성 입력칸 {len(en)} · 활성 버튼 {btn}")
        check(not en and not btn, f"토글 Off 인데 활성: 입력칸 {en[:5]} · 버튼 {btn}")
        s.set_on(True)
        check(s.edit("Width").is_enabled(), "토글을 다시 켰는데 입력칸이 비활성")
        check(s.color() == "Pink", f"토글을 다시 켠 뒤 Color {s.color()} (기대 Pink)")
        leave_and(ctx, "Cancel")
        check(text_el(ui, "Thickness", 900) is not None and s.color() == "Pink", "Cancel 후 Slipsheet 화면·Pink 편집 상태가 아님")
        leave_and(ctx, "Discard & Exit")
        s.open()
        ctx.step(f"Discard 후 토글 {s.is_on()} · Color {s.color()}")
        check(s.is_on() and s.color() == "Warm Gray", f"Discard 후 저장값이 아님 (토글 {s.is_on()}, Color {s.color()})")
        ctx.note = "[부분] 활성/비활성·Pink 유지·Unsaved Changes Cancel/Discard 통과 · 스와치 회색조·3D 홀더 표시는 눈으로 확인 필요"
    _run(ctx, "Imperial", body, pre)


@tc_check("SD024_06", "SD024-6 단위 METRIC↔IMPERIAL 표시·경계",
          "IMPERIAL: 36.00·43.20·0.10 in, Width 23 → 24.00, METRIC 복귀: 914.4·1097.3·2.5",
          [(SR, "metric", "imperial")], admin=False)
def sd024_06(ctx):
    pre = {"on": True, "type": "Paper", "Width": "914.4", "Length": "1097.3", "Thickness": "2.5"}

    def body(s):
        set_unit(ctx, "Imperial")
        s.open()
        got = tuple(s.value(f) for f in ("Width", "Length", "Thickness"))
        ctx.step(f"IMPERIAL 표시 {got}")
        check(got == ("36.00", "43.20", "0.10"), f"IMPERIAL 표시 {got} (기대 36.00·43.20·0.10)")
        check(text_el(ctx.ui, "in", 1700) is not None, "단위 in 표시 없음")
        v = s.type("Width", "23")
        check(v == "24.00", f"Width 23 → {v} (기대 24.00)")
        leave_and(ctx, "Discard & Exit")
        set_unit(ctx, "Metric")
        s.open()
        got = tuple(s.value(f) for f in ("Width", "Length", "Thickness"))
        ctx.step(f"METRIC 복귀 표시 {got}")
        check(got == ("914.4", "1097.3", "2.5"), f"METRIC 표시 {got} (기대 914.4·1097.3·2.5)")
        check(text_el(ctx.ui, "mm", 1700) is not None, "단위 mm 표시 없음")
    _run(ctx, "Metric", body, pre)
