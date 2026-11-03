"""#1512 SOL-819 · #1564 천장 높이 — v2.0.0-21 변경 TC No 19~25 · 29 · 31 · 32 자동 판정 루틴.

Settings > Robot > Base 는 상위 계정(doosan, Lv. Internal)에서만 보인다. 값은 앱을 잠깐 앞으로 가져와 키보드로 넣고,
저장이 필요 없는 TC 는 Discard & Exit 로 버린다. 저장하는 TC(29·31·32)는 끝나면 시작 값으로 되돌려 저장한다.
기대값은 소스 기준: 기본 3000mm, 최소 2000mm(78.74in), 최대 9999.99, 여유 = 천장 − 베이스(V2.0 1131 / V1.6 1095.3)
− 오프셋 − (리프트 사용 시) Max Stroke, 여유 < 0 이면 'The ceiling height is too low. A collision is expected.'
"""
from autotest.flows import NotApplicable, check

from .checks import tc_check
from .fginput import real_click
from .helpers import _num, cy, ensure_role, go_home, leave_and, save, save_enabled, set_unit, settings, text_el, texts
from .fginput import type_into

WARN = "The ceiling height is too low. A collision is expected."
BASE_H = {"v2.0": 1131.0, "v1.6": 1095.3}


class RobotBase:
    def __init__(self, ctx):
        self.ctx, self.ui = ctx, ctx.ui

    def open(self):
        settings(self.ctx, "Robot")
        b = self.ui.top_find("Base")
        if b is not None:
            self.ui.click(b, settle=2, label="Base 탭")
        check(self.ui.wait_for(lambda: text_el(self.ui, "Ceiling Height") is not None, 6), "Settings > Robot > Base 화면이 열리지 않음")

    def edit(self, label):
        lab = text_el(self.ui, label, 900)
        check(lab is not None, f"'{label}' 항목 없음")
        row = [e for e in self.ui.top_all("Edit") if abs(cy(e) - cy(lab)) <= 25 and e.rectangle().left > lab.rectangle().right]
        check(row, f"'{label}' 입력칸 없음")
        return row[-1]

    def value(self, label):
        return _num(self.edit(label).iface_value.CurrentValue)

    def type(self, label, v):
        type_into(self.ui, self.edit(label), v)
        return self.value(label)

    def base_btn(self):
        lab = text_el(self.ui, "Base Version", 900)
        return next(b for b in self.ui.top_all("Button") if abs(cy(b) - cy(lab)) <= 25 and b.rectangle().left > lab.rectangle().right)

    def base(self):
        t = self.base_btn().window_text()
        return "v1.6" if t.startswith("v1.6") else "v2.0" if t.startswith("v2.0") else t

    def set_base(self, v):
        if self.base() == v:
            return
        btn = self.base_btn()
        real_click(self.ui, btn, 1.2)
        it = next((i for i in self.ui.top_all("ListItem") if i.window_text().startswith(v) and abs(i.rectangle().left - btn.rectangle().left) < 60), None)
        check(it is not None, f"Base Version 목록에 {v} 없음")
        real_click(self.ui, it, 1.2)

    def lift_toggle(self):
        lab = text_el(self.ui, "Lift", 900)
        return next(c for c in self.ui.top_all("CheckBox") if abs(cy(c) - cy(lab)) <= 30)

    def set_lift(self, on):
        t = self.lift_toggle()
        if bool(t.get_toggle_state()) != on:
            self.ui.click(t, settle=1.5, label=f"Lift {'On' if on else 'Off'}")

    def warning(self):
        return any((e.window_text() or "") == WARN for e in self.ui.top_all())

    def snapshot(self):
        return {"base": self.base(), "Ceiling Height": self.value("Ceiling Height"),
                "Robot Height Offset": self.value("Robot Height Offset"), "lift": bool(self.lift_toggle().get_toggle_state())}

    def apply(self, snap):
        self.set_base(snap["base"])
        for f in ("Ceiling Height", "Robot Height Offset"):
            if self.value(f) != snap[f]:
                self.type(f, snap[f])
        self.set_lift(snap["lift"])
        if save_enabled(self.ui):
            save(self.ctx)


def _run(ctx, unit, body, saves=False):
    ensure_role(ctx, "doosan")
    unit0 = set_unit(ctx, unit) if unit else None
    rb = RobotBase(ctx)
    rb.open()
    snap0 = rb.snapshot()
    ctx.step(f"시작 값 {snap0}")
    try:
        body(rb)
    finally:
        try:
            rb.open()  # 미저장 편집은 Discard & Exit
            if saves and rb.snapshot() != snap0:
                rb.apply(snap0)
                rb.open()
                check(rb.snapshot() == snap0, f"Robot 설정을 시작 값으로 되돌리지 못함: {rb.snapshot()} ≠ {snap0}")
        finally:
            if unit0:
                set_unit(ctx, unit0)


def _need_v20(rb):
    if rb.base() != "v2.0":
        raise NotApplicable(f"전제조건 불충족: Base Version {rb.base()} (TC 는 V2.0 기준 계산)")


@tc_check("CEIL_19", "천장 높이 기본값", "Ceiling Height 기본 3000mm (바닥 기준)", [("천장 높이 기본값",)], admin=False)
def ceil_19(ctx):
    def body(rb):
        v = rb.value("Ceiling Height")
        ctx.step(f"Ceiling Height {v} mm")
        check(v == 3000.0, f"Ceiling Height {v} mm (기대 3000 — 바꾼 적 없는 기본값)")
    _run(ctx, "Metric", body)


@tc_check("CEIL_20", "천장 높이 최소 2000mm·최대 9999.99", "1999.99 불허, 2000 허용, 9999.99 허용, 10000 불허",
          [("천장 높이 최소 2000",)], admin=False)
def ceil_20(ctx):
    def body(rb):
        res = {v: rb.type("Ceiling Height", v) for v in ("1999.99", "2000", "9999.99", "10000")}
        ctx.step(f"입력 → 표시 {res}")
        check(res["1999.99"] != 1999.99 and res["1999.99"] >= 2000, f"1999.99 가 허용됨 (표시 {res['1999.99']})")
        check(res["2000"] == 2000.0, f"2000 이 {res['2000']} 로 바뀜")
        check(res["9999.99"] == 9999.99, f"9999.99 가 {res['9999.99']} 로 바뀜")
        check(res["10000"] != 10000, "10000 이 허용됨")
    _run(ctx, "Metric", body)


@tc_check("CEIL_21", "inch 단위 최소 78.74", "78.73 불허, 78.74 허용, 9999.99 in 허용 (최대는 단위 환산 안 함)",
          [("inch 단위 최소 78.74",)], admin=False)
def ceil_21(ctx):
    def body(rb):
        res = {v: rb.type("Ceiling Height", v) for v in ("78.73", "78.74", "9999.99")}
        ctx.step(f"입력 → 표시 {res}")
        check(res["78.73"] != 78.73, "78.73 in 이 허용됨")
        check(res["78.74"] == 78.74, f"78.74 in 이 {res['78.74']} 로 바뀜")
        check(res["9999.99"] == 9999.99, f"9999.99 in 이 {res['9999.99']} 로 바뀜")
    _run(ctx, "Imperial", body)


@tc_check("CEIL_22", "천장 여유 < 0 경고 문구", "V2.0 · Offset 900 · Ceiling 2000 → 여유 −31 → 경고 문구, Save 는 활성",
          [("천장 여유 < 0 경고",)], admin=False)
def ceil_22(ctx):
    def body(rb):
        _need_v20(rb)
        rb.set_lift(False)
        rb.type("Robot Height Offset", "900")
        rb.type("Ceiling Height", "2000")
        ctx.step(f"경고 {rb.warning()} · Save {save_enabled(ctx.ui)}")
        check(rb.warning(), f"여유 −31mm 인데 경고 문구가 없음 ('{WARN}')")
        check(save_enabled(ctx.ui), "경고가 있어도 Save 는 활성이어야 함")
    _run(ctx, "Metric", body)


@tc_check("CEIL_23", "여유 = 0 경계", "V2.0 · Ceiling 2000 · Offset 869 → 경고 없음 / 869.01 → 경고",
          [("여유 = 0 경계",)], admin=False)
def ceil_23(ctx):
    def body(rb):
        _need_v20(rb)
        rb.set_lift(False)
        rb.type("Ceiling Height", "2000")
        rb.type("Robot Height Offset", "869")
        w0 = rb.warning()
        rb.type("Robot Height Offset", "869.01")
        w1 = rb.warning()
        ctx.step(f"여유 0 → 경고 {w0} · 여유 −0.01 → 경고 {w1}")
        check(not w0, "여유 0 인데 경고가 표시됨")
        check(w1, "여유 −0.01 인데 경고가 없음")
    _run(ctx, "Metric", body)


@tc_check("CEIL_24", "베이스 버전별 높이 반영", "Ceiling 2000 · V1.6 Offset 904.6 경고 없음 / 904.8 경고 / V2.0 으로 바꿔도 경고",
          [("베이스 버전별 높이",)], admin=False)
def ceil_24(ctx):
    def body(rb):
        rb.set_lift(False)
        rb.type("Ceiling Height", "2000")
        rb.set_base("v1.6")
        rb.type("Robot Height Offset", "904.6")
        a = rb.warning()
        rb.type("Robot Height Offset", "904.8")
        b = rb.warning()
        rb.set_base("v2.0")
        c = rb.warning()
        ctx.step(f"V1.6 904.6 경고 {a} · 904.8 경고 {b} · V2.0 904.8 경고 {c}")
        check(not a, "V1.6 · 여유 +0.1 인데 경고 표시")
        check(b, "V1.6 · 여유 −0.1 인데 경고 없음")
        check(c, "V2.0 · 여유 −35.8 인데 경고 없음")
    _run(ctx, "Metric", body)


@tc_check("CEIL_25", "리프트 최대 스트로크 반영", "V2.0 · Offset 0 · Ceiling 2000: Lift Off 경고 없음 → Lift On · Max Stroke 900 → 경고",
          [("리프트 최대 스트로크",)], admin=False)
def ceil_25(ctx):
    def body(rb):
        _need_v20(rb)
        rb.set_lift(False)
        rb.type("Ceiling Height", "2000")
        rb.type("Robot Height Offset", "0")
        a = rb.warning()
        rb.set_lift(True)
        if "Tool signals are assigned to DO3/DO4" in " ".join(e.window_text() or "" for e in ctx.ui.wrapper().descendants(control_type="Text")):
            raise NotApplicable("툴 신호가 DO3/DO4 에 있어 Lift 를 켤 수 없음")
        rb.type("Max Stroke", "900")
        b = rb.warning()
        ctx.step(f"Lift Off 경고 {a} · Lift On 900 경고 {b}")
        check(not a, "여유 869 인데 경고 표시")
        check(b, "Lift Max Stroke 900 (여유 −31) 인데 경고 없음")
    _run(ctx, "Metric", body)


@tc_check("CEIL_32", "Offset 변경 시 천장 값 유지", "Robot Height Offset 을 바꿔 저장해도 Ceiling Height 는 그대로 (바닥 기준)",
          [("offset 변경 시 천장",)], admin=False)
def ceil_32(ctx):
    def body(rb):
        c0, o0 = rb.value("Ceiling Height"), rb.value("Robot Height Offset")
        rb.type("Robot Height Offset", str(round(o0 + 100, 2)))
        save(ctx)
        rb.open()
        c1 = rb.value("Ceiling Height")
        ctx.step(f"Offset {o0} → {o0 + 100} 저장 후 Ceiling {c0} → {c1}")
        check(c1 == c0, f"Offset 을 바꿨더니 Ceiling Height 가 {c0} → {c1} 로 바뀜")
    _run(ctx, "Metric", body, saves=True)


@tc_check("CEIL_29", "Admin 계정 천장 배너 + Start 비활성 · 해소 후 해제",
          "doosan 으로 여유 < 0 저장 → Admin Home 에 'Ceiling collision expected' 배너 + 시작 버튼 비활성 → 원복 후 배너 사라짐",
          [("admin 계정은 배너",), ("여유 해소 후 배너",)], admin=False)
def ceil_29(ctx):
    def body(rb):
        _need_v20(rb)
        rb.set_lift(False)
        rb.type("Robot Height Offset", "900")
        rb.type("Ceiling Height", "2000")
        save(ctx)
        ensure_role(ctx, "Admin")
        go_home(ctx)
        ui = ctx.ui
        banner = any("Ceiling collision expected" in (e.window_text() or "") for e in ui.top_all())
        start = next((b for b in ui.top_all("Button") if (b.window_text() or "").strip() in ("Start", "Test Run")), None)
        ctx.step(f"Admin Home: 배너 {banner} · 시작 버튼 {start.window_text() if start else None} 활성 {start.is_enabled() if start else None}")
        check(banner, "여유 < 0 인데 Admin Home 에 'Ceiling collision expected' 배너가 없음 (Run Mode 가 Virtual 이면 정상적으로 검사 제외)")
        check(start is not None and not start.is_enabled(), "여유 < 0 인데 Admin 의 시작 버튼이 활성")
        ensure_role(ctx, "doosan")
        rb.open()
    _run(ctx, "Metric", body, saves=True)
    ensure_role(ctx, "Admin")
    go_home(ctx)
    banner = any("Ceiling collision expected" in (e.window_text() or "") for e in ctx.ui.top_all())
    ctx.step(f"원복 후 Admin Home 배너 {banner}")
    check(not banner, "천장 값을 되돌렸는데 배너가 남아 있음")
