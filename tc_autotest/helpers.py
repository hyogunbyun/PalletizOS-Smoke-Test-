"""TC 루틴 공통 도우미 — 계정 전환, Settings 하위 화면, 저장 후 되돌리기, 단위 전환.

사용자 허락 범위(2026-11-02, TC 자동평가 툴·가상 제어기 한정): 상위 계정 사용, 저장 후 원래 값으로 되돌림,
숫자 입력·드롭다운은 앱을 잠깐 앞으로 가져와 실제 키보드·마우스로.
"""
import time

from autotest import secret
from autotest.flows import NotApplicable, check
from autotest.ui import EnvError

from .fginput import real_click, type_into

ACCOUNT_TARGET = {"Admin": secret.TARGET, "doosan": "PalletizOS-Smoke-Account-doosan"}


def cy(e):
    r = e.rectangle()
    return (r.top + r.bottom) // 2


def texts(ui):
    return [t for t in ui.top_all("Text") if t.rectangle().width() > 0]


def text_el(ui, name, min_left=0):
    return next((t for t in texts(ui) if t.window_text() == name and t.rectangle().left >= min_left), None)


def right_of(ui, label_el, ctype):
    """라벨과 같은 줄, 라벨 오른쪽의 첫 컨트롤."""
    row = [e for e in ui.top_all(ctype) if abs(cy(e) - cy(label_el)) <= 25 and e.rectangle().left > label_el.rectangle().right]
    return min(row, key=lambda e: e.rectangle().left) if row else None


# ---------------------------------------------------------------- 화면 이동
def go_home(ctx):
    ui = ctx.ui
    try:
        if ui.on_home():
            return
    except Exception:
        pass
    ui.back_to_home()


def settings(ctx, sub):
    """Settings > sub. 미저장 변경이 남아 있으면 Discard & Exit."""
    ui = ctx.ui
    if ui.top_find(sub) is None:
        go_home(ctx)
        ui.goto("Settings")
        check(ui.wait_for(lambda: ui.top_find("General") is not None, 8), "Settings 화면이 열리지 않음")
    ui.click(ui.top_find(sub), settle=2.5, label=f"Settings {sub}")
    discard_if_asked(ctx)


def discard_if_asked(ctx, button="Discard & Exit"):
    ui = ctx.ui
    if "Unsaved Changes" in ui.top_names():
        ui.click(ui.top_find(button), settle=2.5, label=f"이탈 팝업 {button}")
        return True
    return False


def save(ctx, timeout=10):
    """Save 누르고 Save 가 다시 비활성이 될 때까지."""
    ui = ctx.ui
    sv = [b for b in ui.top_all("Button") if b.window_text() == "Save"]
    check(sv and sv[-1].is_enabled(), "Save 가 비활성 — 바뀐 값이 없음")
    ui.click(sv[-1], settle=2.5, label="Save")
    for c in ("Confirm", "OK", "Yes"):  # 확인창이 뜨는 화면
        b = ui.top_find(c)
        if b is not None:
            ui.click(b, settle=2, label=f"저장 확인 {c}")
            break
    check(ui.wait_for(lambda: not [b for b in ui.top_all("Button") if b.window_text() == "Save"][-1].is_enabled(), timeout),
          "Save 후에도 Save 가 계속 활성 (저장 실패?)")


def save_enabled(ui):
    sv = [b for b in ui.top_all("Button") if b.window_text() == "Save"]
    return bool(sv) and sv[-1].is_enabled()


# ---------------------------------------------------------------- 계정
def current_role(ui):
    r = ui.current_role()
    if r:
        return r
    b = next((e for e in ui.top_all("Button") if len(e.window_text() or "") == 1 and e.rectangle().top < 140), None)
    if b is None:
        return None
    ui.click(b, settle=1.5, label="계정 메뉴")
    name = None
    for t in texts(ui):
        if t.window_text() == "Lv. ":
            row = [x for x in texts(ui) if abs(x.rectangle().bottom - t.rectangle().top) < 12]
            name = row[0].window_text() if row else None
    ui.esc()
    return name


def ensure_role(ctx, role):
    """계정 전환 (Admin·doosan). 비밀번호는 Windows 자격 증명에서만."""
    ui = ctx.ui
    go_home(ctx)
    now = ui.wait_role()
    if now == role:
        return
    pw = secret.load(ACCOUNT_TARGET.get(role, ""))
    if not pw:
        raise NotApplicable(f"{role} 계정 비밀번호가 Windows 자격 증명에 없음")
    ui.click(ui.top_find(f"{now[0]} {now}") if now else ui.top_all("Button")[0], settle=2, label="계정 메뉴")
    tgt = next((b for b in ui.top_all("Button") if (b.window_text() or "").lower() == f"{role[0]} {role}".lower()), None)
    if tgt is None:
        ui.esc()
        raise NotApplicable(f"계정 목록에 {role} 없음")
    ui.click(tgt, settle=2, label=f"계정 {role}")
    prompt = next((t for t in texts(ui) if (t.window_text() or "").startswith("Please enter the password")), None)
    if prompt is not None:
        edit = min((e for e in ui.top_all("Edit") if e.rectangle().top >= prompt.rectangle().bottom - 5),
                   key=lambda e: e.rectangle().top)
        ui.set_text(edit, pw, label="비밀번호 입력")
        ui.click(ui.top_find("Confirm"), settle=3, label="Confirm")
    if not ui.wait_for(lambda: ui.current_role() == role, 12):
        raise EnvError(f"{role} 로그인 실패")
    ui.remember_nav()


# ---------------------------------------------------------------- 단위 (Settings > General)
def unit_now(ctx):
    from autotest.flows_menus import _selected
    ui = ctx.ui
    settings(ctx, "General")
    m = ui.top_find("Metric (mm, kg)", "RadioButton")
    return "Metric" if _selected(m) else "Imperial"


def set_unit(ctx, unit):
    """Metric / Imperial 로 바꿔 저장. 바꿨으면 원래 단위를 돌려줌 (finally 에서 set_unit 으로 복구)."""
    ui = ctx.ui
    before = unit_now(ctx)
    if before == unit:
        return None
    name = "Metric (mm, kg)" if unit == "Metric" else "Imperial (inch, lbs)"
    ui.click(ui.top_find(name, "RadioButton"), settle=1.5, label=f"Unit {unit}")
    save(ctx)
    return before


# ---------------------------------------------------------------- Slipsheet
SLIP_FIELDS = ("Width", "Length", "Thickness")


class Slip:
    def __init__(self, ctx):
        self.ctx, self.ui = ctx, ctx.ui

    def open(self):
        settings(self.ctx, "Slipsheet")
        check(self.ui.wait_for(lambda: text_el(self.ui, "Thickness") is not None, 6), "Slipsheet 화면이 열리지 않음")

    def toggle(self):
        title = next(t for t in texts(self.ui) if t.window_text() == "Slipsheet" and t.rectangle().left > 900)
        return right_of(self.ui, title, "CheckBox")

    def is_on(self):
        return bool(self.toggle().get_toggle_state())

    def set_on(self, on):
        if self.is_on() != on:
            self.ui.click(self.toggle(), settle=1.5, label=f"Slipsheet 토글 {'On' if on else 'Off'}")

    def edit(self, label):
        return right_of(self.ui, text_el(self.ui, label, 900), "Edit")

    def value(self, label):
        return self.edit(label).iface_value.CurrentValue

    def type(self, label, v):
        type_into(self.ui, self.edit(label), v)
        return self.value(label)

    def color_button(self):
        return right_of(self.ui, text_el(self.ui, "Color", 900), "Button")

    def color(self):
        return self.color_button().window_text()

    def color_items(self):
        real_click(self.ui, self.color_button(), 1.2)
        items = sorted([e for e in self.ui.top_all("ListItem") if e.window_text() in COLORS], key=lambda e: e.rectangle().top)
        return items

    def pick_color(self, name):
        items = self.color_items()
        it = next((e for e in items if e.window_text() == name), None)
        check(it is not None, f"Color 목록에 {name} 없음")
        real_click(self.ui, it, 1.2)

    def type_selected(self):
        from autotest.flows_menus import _selected
        for n in ("Paper", "Cardboard"):
            r = self.ui.top_find(n, "RadioButton")
            if r is not None and _selected(r):
                return n
        return None

    def set_type(self, n):
        if self.type_selected() != n:
            self.ui.click(self.ui.top_find(n, "RadioButton"), settle=1.5, label=f"Type {n}")

    def snapshot(self):
        return {"on": self.is_on(), "type": self.type_selected(), "color": self.color(),
                **{f: self.value(f) for f in SLIP_FIELDS}}

    def apply(self, want, do_save=True):
        """want: snapshot 형식(일부만 줘도 됨). 다르면 바꾸고 저장."""
        self.set_on(True)
        if want.get("type"):
            self.set_type(want["type"])
        if want.get("color") and self.color() != want["color"]:
            self.pick_color(want["color"])
        for f in SLIP_FIELDS:
            if want.get(f) is not None and _num(self.value(f)) != _num(want[f]):
                self.type(f, want[f])
        if "on" in want:
            self.set_on(want["on"])
        if do_save and save_enabled(self.ui):
            save(self.ctx)


COLORS = ("Warm Gray", "Teal", "Violet", "Pink", "Amber")


def _num(s):
    try:
        return round(float(str(s).replace(",", "")), 2)
    except ValueError:
        return s


def leave_and(ctx, button):
    """좌측 Settings 메뉴(General)를 눌러 이탈 → 팝업에서 button."""
    ui = ctx.ui
    ui.click(ui.top_find("General"), settle=2, label="다른 화면(General)")
    check("Unsaved Changes" in ui.top_names(), "미저장 변경이 있는데 'Unsaved Changes' 팝업이 뜨지 않음")
    ui.click(ui.top_find(button), settle=2.5, label=f"팝업 {button}")


def wait(sec):
    time.sleep(sec)
