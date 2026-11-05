"""TC 루틴 공통 도우미 — 계정 전환, Settings 하위 화면, 저장 후 되돌리기, 단위 전환.

사용자 허락 범위(2026-11-02, TC 자동평가 툴·가상 제어기 한정): 상위 계정 사용, 저장 후 원래 값으로 되돌림,
숫자 입력·드롭다운은 앱을 잠깐 앞으로 가져와 실제 키보드·마우스로.
"""
import re
import time

from autotest import secret
from autotest.flows import NotApplicable, check
from autotest.ui import EnvError

from .fginput import real_click, type_into

ACCOUNT_TARGET = secret.ACCOUNT_TARGET


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
def _on_home(ui):
    try:
        return ui.on_home()
    except Exception:  # noqa: BLE001  Settings 전체화면이면 root() 가 없음
        return False


def go_home(ctx):
    """어느 화면이든 Home 으로. Settings 전체화면에선 왼쪽 메뉴 맨 위(계정 버튼 다음) 아이콘이 Home."""
    ui = ctx.ui
    if _on_home(ui):
        return
    w = ui.wrapper()
    if "Change Account" in ui.top_names():  # 계정 메뉴가 열려 있으면 닫기
        ui.esc()
    try:
        if ui.expand_nav() and ui.top_find("Home") is not None:  # 접힌 메뉴 → 펼쳐서 이름으로 Home
            ui.click(ui.top_find("Home"), settle=2.5, label="Home")
            discard_if_asked(ctx)
            if _on_home(ui):
                return
    except Exception:  # noqa: BLE001  펼치기 실패 → 아래 아이콘 방식
        pass
    left = w.rectangle().left
    rail = sorted([b for b in ui.top_all("Button") if not b.window_text() and b.rectangle().left - left < 40
                   and b.rectangle().width() > 0 and b.rectangle().top < w.rectangle().top + 650], key=lambda b: b.rectangle().top)
    # 2.0.0-28: 계정 아이콘 위에 이름 없는 '→ 메뉴 펼치기' 버튼이 생겨 rail[0] 이 Home 이 아니게 됨 → 계정 아이콘 아래만
    acct = next((b for b in ui.top_all("Button") if b.rectangle().left - left < 40
                 and re.fullmatch(r"[A-Za-z](?: \S.*)?", b.window_text() or "")), None)
    if acct is not None:
        rail = [b for b in rail if b.rectangle().top > acct.rectangle().bottom - 5]
    if rail:
        ui.click(rail[0], settle=2.5, label="Home")
        discard_if_asked(ctx)
    if not _on_home(ui):
        ui.back_to_home()


def settings(ctx, sub):
    """Settings > sub. 미저장 변경이 남아 있으면 Discard & Exit."""
    ui = ctx.ui
    if ui.top_find(sub) is None:
        go_home(ctx)
        if _on_home(ui):  # Home 의 펼친 메뉴에서 순서를 다시 기억 (다른 화면에서 기억한 순서가 덮여 'Settings 못 찾음' — 11-02)
            ui.remember_nav()
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
    ui.click(ui.acct_button(now) if now else ui.top_all("Button")[0], settle=2, label="계정 메뉴")
    tgt = ui.acct_button(role)
    if tgt is None:  # Change Account 목록에 없는 계정(doosan 등) → 로그아웃 후 로그인 화면에서 계정 이름을 직접 입력
        ui.esc()
        if now not in ("Admin", "doosan") and role != "Admin":
            # Operator 등엔 Settings(로그아웃 버튼)가 없음 → 먼저 Admin 으로 (11-02: 앱 재시작 후 기본 계정 Operator 로 들어와 막힘)
            ensure_role(ctx, "Admin")
        login_typed(ctx, role, pw)
        return
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


def _acc_box(w):
    """'Account' 글자 바로 아래(80px 안) 버튼. 로그인 화면 밑에 Settings 화면 요소가 그대로 남아 있어
    조건이 느슨하면 'Settings' 버튼을 Account 칸으로 잡음 (2026-11-04 11:21·11:33 doosan 로그인 실패 원인)."""
    acc = next(e for e in w.descendants(control_type="Text") if e.window_text() == "Account"
               and e.element_info.rectangle.width() > 0)
    ar = acc.rectangle()
    cand = [b for b in w.descendants(control_type="Button") if b.element_info.rectangle.width() > 0
            and 0 <= b.rectangle().top - ar.bottom < 80 and abs(b.rectangle().left - ar.left) < 30]
    return min(cand, key=lambda b: b.rectangle().top - ar.bottom)


def _keys(s):
    return "".join("{%s}" % c if c in "{}+^%~()" else c for c in s)


def _login_by_value(ui, account, pw):
    """로그인 화면을 UIA 값 입력으로 (앞 창 불필요, 2026-11-05 실측).
    Account 버튼은 ExpandCollapse 전용 → Expand 하면 그 자리에 입력칸(Edit, 현재 계정 이름)과 화상 키보드가 뜸.
    입력칸에 SetValue(account) → 목록이 'D doosan' 처럼 걸러짐 → 그 항목 Select → Password SetValue → Log In Invoke.
    (목록엔 Admin·Operator 만 보여 doosan 은 고를 수 없음 — 이름을 입력해야 나옴)"""
    w = ui.wrapper()
    want = account.lower()
    box = _acc_box(w)
    ar = box.rectangle()
    try:
        if box.iface_expand_collapse.CurrentExpandCollapseState == 0:
            box.iface_expand_collapse.Expand()
    except Exception as e:  # noqa: BLE001
        return f"Account 펼치기 실패 ({e})"
    time.sleep(1.0)
    ed = next((e for e in w.descendants(control_type="Edit") if e.element_info.rectangle.width() > 0
               and abs(e.rectangle().top - ar.top) < 40 and ar.left - 5 <= e.rectangle().left <= ar.right), None)
    if ed is None:
        return "Account 를 펼쳤는데 이름 입력칸이 안 보임"
    ed.iface_value.SetValue(account)
    time.sleep(1.2)
    it = next((e for e in w.descendants(control_type="ListItem") if e.element_info.rectangle.width() > 0
               and re.fullmatch(rf"(?:\S\s+)?(?:\(\w+\)\s+)?{re.escape(want)}", (e.window_text() or "").strip().lower())), None)
    if it is not None:
        try:
            it.iface_selection_item.Select()
        except Exception:  # noqa: BLE001
            it.click_input()
        time.sleep(1.0)
    if (_acc_box(w).window_text() or "").strip().lower() != want:
        return f"Account 칸이 '{_acc_box(w).window_text()}' 로 남음 (목록 항목 {'있음' if it is not None else '없음'})"
    pwd_lab = next(e for e in w.descendants(control_type="Text") if e.window_text() == "Password")
    pwd = min((e for e in w.descendants(control_type="Edit") if e.rectangle().top > pwd_lab.rectangle().bottom - 5),
              key=lambda e: e.rectangle().top)
    pwd.iface_value.SetValue(pw or "")
    time.sleep(0.5)
    if len(pwd.iface_value.CurrentValue or "") != len(pw or ""):
        return "비밀번호 칸에 값이 안 들어감"
    next(b for b in w.descendants(control_type="Button") if b.window_text() == "Log In").iface_invoke.Invoke()
    time.sleep(4)
    if ui.wait_for(lambda: (ui.current_role() or "").lower() == want, 30):
        return True
    still = any(b.window_text() == "Log In" for b in w.descendants(control_type="Button"))
    return "Log In 뒤에도 로그인 화면 그대로 (비밀번호 틀림?)" if still else f"Log In 뒤 계정 표시가 '{ui.current_role()}'"


def login_screen(ui, account, pw):
    """PalletizOS 로그인 화면(Account 드롭다운 · Password · Log In)에서 account 로 로그인. 성공하면 True.
    먼저 _login_by_value(백그라운드 값 입력), 안 되면 아래 앞 창 클릭·키 입력 방식."""
    why = []
    for i in range(3):  # 로그아웃 직후엔 로그인 화면이 덜 그려져 있을 수 있음 → 잠깐 기다렸다 다시
        try:
            r = _login_by_value(ui, account, pw)
        except Exception as e:  # noqa: BLE001
            r = f"{type(e).__name__}: {e}"[:120]
        if r is True:
            return True
        why.append(f"{i + 1}차 {r}")
        if "비밀번호 틀림" in str(r):
            break
        try:
            ui.esc()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3)
    from autotest.events import ev
    ev(f"{account} 로그인(값 입력 방식) 실패: " + " / ".join(why) + " → 키 입력 방식으로 시도")
    return _login_by_keys(ui, account, pw)


def _login_by_keys(ui, account, pw):
    """(예전 방식) 앞 창으로 가져와 클릭·키 입력.

    Account 칸은 이름이 현재 계정인 버튼(드롭다운, 11-04 실측 'Button Admin'). ① 펼쳐서 목록의 account 항목 클릭
    ② 목록에 없으면 칸에 이름 입력 + Enter. 어느 쪽이든 칸 글자가 account 로 바뀐 것을 확인한 뒤에만 비밀번호 입력."""
    from pywinauto import keyboard

    from .fginput import Foreground
    w = ui.wrapper()
    want = account.lower()
    picked = lambda: (_acc_box(w).window_text() or "").strip().lower() == want  # noqa: E731
    with Foreground(ui):
        for how in ("list", "type"):
            if picked():
                break
            box = _acc_box(w)
            r = box.rectangle()
            before = {e.element_info.runtime_id for e in w.descendants()}
            box.click_input(coords=(r.width() // 3, r.height() // 2))
            time.sleep(1.0)
            opt = next((e for e in w.descendants() if e.element_info.runtime_id not in before
                        and (e.window_text() or "").strip().lower() == want and e.element_info.rectangle.width() > 0), None)
            if how == "list" and opt is not None:
                opt.click_input()
            elif how == "type":
                keyboard.send_keys("^a{BACKSPACE}", pause=0.03)
                keyboard.send_keys(_keys(account), pause=0.05)
                time.sleep(0.8)
                opt = next((e for e in w.descendants() if (e.window_text() or "").strip().lower() == want
                            and e.element_info.rectangle.width() > 0 and e.rectangle().top > r.bottom - 5), None)
                if opt is not None:
                    opt.click_input()
                else:
                    keyboard.send_keys("{ENTER}")
            else:
                keyboard.send_keys("{ESC}")
            time.sleep(1.0)
        if not picked():
            keyboard.send_keys("{ESC}")
            return False
        pwd_lab = next(e for e in w.descendants(control_type="Text") if e.window_text() == "Password")
        pwd = min((e for e in w.descendants(control_type="Edit") if e.rectangle().top > pwd_lab.rectangle().bottom - 5),
                  key=lambda e: e.rectangle().top)
        pwd.click_input()
        time.sleep(0.3)
        keyboard.send_keys("^a{BACKSPACE}", pause=0.03)
        keyboard.send_keys(_keys(pw), pause=0.04)
        time.sleep(0.3)
        next(b for b in w.descendants(control_type="Button") if b.window_text() == "Log In").click_input()
        time.sleep(4)
    return ui.wait_for(lambda: (ui.current_role() or "").lower() == want, 30)


def login_typed(ctx, account, pw):
    """Settings > General > Log Out → 로그인 화면에서 account 로 로그인 (login_screen).
    (Admin 의 Change Account 목록엔 Operator 만 있고 doosan 은 없음 — 11-02 실측)"""
    ui = ctx.ui
    settings(ctx, "General")
    ui.click(ui.top_find("Log Out"), settle=3, label="Log Out")
    for c in ("Log Out", "Confirm", "OK", "Yes"):
        b = ui.top_find(c)
        if b is not None and b.rectangle().top > 300:
            ui.click(b, settle=3, label=f"로그아웃 확인 {c}")
            break
    w = ui.wrapper()
    check(ui.wait_for(lambda: any(b.window_text() == "Log In" for b in w.descendants(control_type="Button")), 15),
          "로그인 화면이 나오지 않음")
    if not login_screen(ui, account, pw):
        # 로그인 화면에 멈춰 있지 않게 (11-04 11:21: doosan 입력 실패 → Admin 선택·비번 빈 채로 멈춤) → Admin 으로라도 다시 들어감
        apw = secret.load(ACCOUNT_TARGET["Admin"])
        if account != "Admin" and apw and login_screen(ui, "Admin", apw):
            raise EnvError(f"{account} 로그인 실패 (로그인 화면 Account 에서 '{account}' 를 고르지 못함) → Admin 으로 다시 로그인함")
        raise EnvError(f"{account} 로그인 실패 (계정·비밀번호 확인)")
    ui.remember_nav()
