"""#1508 SOL-371 Tool Configuration(툴 IO) — v2.0.0-21 변경 TC No 4~9 자동 판정 루틴.

주소·신호 타입 선택은 실제 마우스(앱을 잠깐 앞으로)로만 열린다. 저장이 거부돼야 하는 TC 는 Save 를 눌러
팝업이 그대로 남는지 확인한 뒤 Cancel 로 버린다. 저장이 되는 TC(Blow off Not Used)는 끝나면 원래대로 되돌려 저장한다.
"""
import time

from autotest.flows import NotApplicable, check
from autotest.flows_menus import _io_tab, _open

from .checks import _io_names, _zone_rows, tc_check
from .fginput import real_click
from .helpers import cy, ensure_role, go_home, settings, texts

TITLE = "Tool Configuration"


class ToolCfg:
    def __init__(self, ctx):
        self.ctx, self.ui = ctx, ctx.ui

    def open(self):
        ensure_role(self.ctx, "Admin")
        settings(self.ctx, "Tool")
        self.ui.click(self.ui.top_find("Configuration"), settle=2.5, label="Tool Configuration")
        check(self.ui.wait_for(lambda: TITLE in self.ui.top_names(), 6), "Tool Configuration 팝업이 열리지 않음")

    def is_open(self):
        return TITLE in self.ui.top_names()

    def src_btn(self, label):
        lab = next(t for t in texts(self.ui) if t.window_text() == label and t.rectangle().left < 300)
        return next(b for b in self.ui.top_all("Button") if abs(cy(b) - cy(lab)) < 25 and 360 < b.rectangle().left < 460)

    def _pick_from_list(self, anchor, value):
        """anchor 버튼을 눌러 연 목록에서 value 항목을 고른다 (안 보이면 스크롤)."""
        near = lambda: [i for i in self.ui.top_all("ListItem") if abs(i.rectangle().left - anchor.rectangle().left) < 60]  # noqa: E731
        items = near()
        for _ in range(3):  # 이미 열린 목록을 다시 누르면 닫힘 → 열려 있지 않을 때만 누름 (11-02: 짝수 번 눌러 안 열림)
            if any(i.window_text() == value for i in items):
                break
            if not items:
                real_click(self.ui, anchor, 1.2)
            time.sleep(0.8)  # 목록이 늦게 그려질 때 (11-02 Blow off 복구에서 한 번 놓침)
            items = near()
        it = next((i for i in items if i.window_text() == value), None)
        if it is None:  # 목록 밖(스크롤 아래)일 수 있음
            it = next((i for i in self.ui.top_all("ListItem") if i.window_text() == value
                       and abs(i.rectangle().left - anchor.rectangle().left) < 60), None)
        if it is None:
            real_click(self.ui, anchor, 0.8)  # 목록 닫기
            return False
        try:
            it.iface_scroll_item.ScrollIntoView()
            time.sleep(0.4)
        except Exception:
            pass
        real_click(self.ui, it, 1.2)
        return True

    def options(self, anchor):
        before = {(i.window_text(), i.rectangle().top) for i in self.ui.top_all("ListItem")}
        real_click(self.ui, anchor, 1.2)
        opts = [i.window_text() for i in sorted(self.ui.top_all("ListItem"), key=lambda i: i.rectangle().top)
                if (i.window_text(), i.rectangle().top) not in before and abs(i.rectangle().left - anchor.rectangle().left) < 60]
        real_click(self.ui, anchor, 0.8)
        return opts

    def set_src(self, label, value):
        check(self._pick_from_list(self.src_btn(label), value), f"{label} 신호 타입에 '{value}' 선택지 없음")

    def zone_btn(self, zone, which="vacuum"):
        row = next(r for r in _zone_rows(self.ui) if r[0] == zone)
        return row[1] if which == "vacuum" else row[2]

    def set_addr(self, btn, value):
        check(self._pick_from_list(btn, str(value)), f"주소 {value} 선택지 없음 (잠긴 포트)")

    def section_addr(self, header):
        """오른쪽 'Blow off'·'Reducer' 머리글 아래 첫 주소 버튼."""
        h = next((t for t in texts(self.ui) if t.window_text() == header and t.rectangle().left > 900), None)
        if h is None:
            return None
        below = [b for b in self.ui.top_all("Button") if b.rectangle().top > h.rectangle().bottom
                 and abs(b.rectangle().left - h.rectangle().left) < 40 and b.rectangle().top - h.rectangle().bottom < 120]
        return min(below, key=lambda b: b.rectangle().top) if below else None

    def save_enabled(self):
        sv = [b for b in self.ui.top_all("Button") if b.window_text() == "Save" and 850 < b.rectangle().top < 1000
              and b.rectangle().left > 1400]
        return bool(sv) and sv[-1].is_enabled()

    def save(self):
        """팝업의 Save → (Overwrite 확인이 뜨면 Overwrite) → 팝업이 닫혔는지."""
        sv = [b for b in self.ui.top_all("Button") if b.window_text() == "Save" and 850 < b.rectangle().top < 1000
              and b.rectangle().left > 1400]
        check(sv, "Tool Configuration 의 Save 버튼 없음")
        self.ui.click(sv[-1], settle=0.6, label="Tool Configuration Save")
        # 오류는 화면 위쪽 토스트(error notification)로 잠깐 떴다 사라짐 → 바로 잡아 둠 (11-02: 2.5초 뒤 확인해 놓침)
        self.last_errors = self._toasts()
        time.sleep(1.5)
        self.last_errors += [t for t in self._toasts() if t not in self.last_errors]
        ow = self.ui.top_find("Overwrite")
        if ow is not None:
            self.ui.click(ow, settle=2.5, label="Overwrite")
        self.ui.wait_for(lambda: not self.is_open(), 4)
        return not self.is_open()

    def _toasts(self):
        return [e.window_text() for e in self.ui.wrapper().descendants(control_type="Text")
                if ("more than once" in (e.window_text() or "") or "Failed to save" in (e.window_text() or ""))
                and not (e.window_text() or "").startswith("error notification")]

    def errors(self):
        return list(dict.fromkeys(getattr(self, "last_errors", []) + self._toasts()))

    def cancel(self):
        if self.is_open():
            b = next((b for b in self.ui.top_all("Button") if b.window_text() == "Cancel"), None)
            if b is not None:
                self.ui.click(b, settle=2, label="Cancel (저장 안 함)")


def _rejected(ctx, cfg, what):
    closed = cfg.save()
    errs = cfg.errors()
    ctx.step(f"Save 후 팝업 {'닫힘' if closed else '유지'} · 오류 문구 {errs}")
    if closed:  # 저장돼 버림 → 원래대로 되돌리고 실패
        _restore_default(ctx)
        check(False, f"{what} 인데 저장됨 (기대: 저장 거부, 팝업 유지) — 기본 배치로 되돌려 둠")
    return errs


def _restore_default(ctx):
    """기본 배치(DO5~8 / Flange 1~4 / DO12 / DO13, Single)로 되돌려 저장."""
    cfg = ToolCfg(ctx)
    cfg.open()
    try:
        for src, val in (("Vacuum", "Digital IO"), ("Sensor", "Flange IO"), ("Blow off", "Digital IO"), ("Reducer", "Digital IO")):
            if cfg.src_btn(src).window_text() != val:
                cfg.set_src(src, val)
        single = cfg.ui.top_find("Single", "RadioButton")
        if single is not None:
            cfg.ui.click(single, settle=1, label="Single")
        rows = _zone_rows(cfg.ui)
        for n, v, s, row in rows:
            if n <= 4:
                if v is not None and v.window_text() != str(4 + n):
                    cfg.set_addr(v, 4 + n)
                if s is not None and s.window_text() != str(n):
                    cfg.set_addr(cfg.zone_btn(n, "sensor"), n)
        for label, addr in (("Blow off", 12), ("Reducer", 13)):  # 신호 타입을 되돌리면 주소가 비므로 다시 넣음 (11-02: 빠뜨려 Not Used 로 남음)
            b = cfg.section_addr(label)
            if b is not None and b.window_text() != str(addr):
                cfg.set_addr(b, addr)
        if cfg.save_enabled():
            check(cfg.save(), f"기본 배치로 되돌려 저장하지 못함 (오류 {cfg.errors()}) — Tool Configuration 수동 확인 필요")
    finally:
        cfg.cancel()


@tc_check("TIO_04", "Sensor 주소 미입력 시 저장 불가",
          "Add Zone 으로 만든 빈 Zone(진공·센서 주소 없음) 상태로 Save → 저장되지 않고 팝업 유지",
          [("sensor 주소 미입력",)], admin=False)
def tio_04(ctx):
    cfg = ToolCfg(ctx)
    cfg.open()
    try:
        add = cfg.ui.top_find("Add Zone")
        if add is None or not add.is_enabled():
            raise NotApplicable("Add Zone 이 비활성 — 빈 주소 Zone 을 만들 수 없음 (화면에 빈 주소 선택지 없음)")
        n0 = len(_zone_rows(cfg.ui))
        cfg.ui.click(add, settle=1.5, label="Add Zone")
        rows = _zone_rows(cfg.ui)
        check(len(rows) == n0 + 1, f"Add Zone 후 Zone 수 {len(rows)} (기대 {n0 + 1})")
        new = rows[-1]
        ctx.step(f"Zone{new[0]} 진공 {new[1].window_text() if new[1] else None!r} · 센서 {new[2].window_text() if new[2] else None!r}")
        _rejected(ctx, cfg, "센서 주소가 빈 Zone")
        ctx.note = "빈 주소 Zone 저장 거부·팝업 유지 확인 (TC 의 'Zone2 센서 비우기'는 화면에 빈 주소 선택지가 없어 Add Zone 빈 칸으로 대체)"
    finally:
        cfg.cancel()


@tc_check("TIO_05", "Reducer 주소 미입력 시 저장 불가", "Reducer 주소를 비울 선택지가 화면에 없음 → 판정 대상 아님",
          [("reducer 주소 미입력",)], admin=False)
def tio_05(ctx):
    raise NotApplicable("Reducer 주소 목록에 '빈 값' 선택지가 없음 — 화면에서 만들 수 없는 상태 (TC 수정 필요)")


@tc_check("TIO_06", "Blow off Not Used",
          "Blow off 를 Not Used 로 → 주소 행 사라짐 → 저장 → IO 탭 DO12 이름 비워짐 (끝나면 기본으로 되돌림)",
          [("blow off not used",)], admin=False)
def tio_06(ctx):
    cfg = ToolCfg(ctx)
    cfg.open()
    try:
        cfg.set_src("Blow off", "Not Used")
        row_gone = not [t for t in texts(cfg.ui) if t.window_text() == "Blow off" and t.rectangle().left > 900]
        ctx.step(f"Not Used 후 Blow off 주소 행 {'사라짐' if row_gone else '남아 있음'}")
        check(row_gone, "Not Used 로 바꿨는데 Blow off 주소 행이 남아 있음")
        check(cfg.save(), f"Not Used 저장이 되지 않음 (오류 {cfg.errors()})")
    finally:
        cfg.cancel()
    try:
        go_home(ctx)
        _open(ctx, "IO", "Modbus Master")
        _io_tab(ctx, "Digital Output")
        names = _right_column_names(ctx.ui)
        ctx.step(f"IO DO12 이름 {names.get(12)!r}")
        check(not names.get(12), f"Blow off Not Used 인데 DO12 이름 {names.get(12)!r} (기대: 빈 이름)")
    finally:
        _restore_default(ctx)


def _right_column_names(ui):
    """DO 탭 오른쪽 열(9~16번): {포트: 이름}."""
    ports = [t for t in texts(ui) if (t.window_text() or "").isdigit() and t.rectangle().left > 1100 and t.rectangle().left < 1200]
    names = [t for t in texts(ui) if 1200 < t.rectangle().left < 1600 and not (t.window_text() or "").isdigit()]
    out = {}
    for p in ports:
        same = [n.window_text() for n in names if abs(cy(n) - cy(p)) <= 20 and n.window_text() not in ("Name", "Value", "Test")]
        out[int(p.window_text())] = same[0] if same else ""
    return out


@tc_check("TIO_07", "같은 주소 중복",
          "Zone2 진공 주소를 Zone1 과 같은 5 로 → Save → 'The same address is used more than once.' + 저장 안 됨",
          [("같은 주소 중복",)], admin=False)
def tio_07(ctx):
    cfg = ToolCfg(ctx)
    cfg.open()
    try:
        cfg.set_addr(cfg.zone_btn(2), 5)
        errs = _rejected(ctx, cfg, "주소 중복")
        check(any("The same address is used more than once." in e for e in errs),
              f"중복 오류 문구가 없음 (보인 문구 {errs})")
    finally:
        cfg.cancel()


@tc_check("TIO_08", "Double acting 저장 불가",
          "Acting Double → Release I/O 열 표시 → Save → 저장되지 않음",
          [("double acting",)], admin=False)
def tio_08(ctx):
    cfg = ToolCfg(ctx)
    cfg.open()
    try:
        cfg.ui.click(cfg.ui.top_find("Double", "RadioButton"), settle=1.5, label="Acting Double")
        check("Release I/O" in cfg.ui.top_names(), "Double 인데 'Release I/O' 열이 없음")
        _rejected(ctx, cfg, "Double acting")
        ctx.note = "Release I/O 열 표시·저장 거부 확인 (화면에서 고를 수 있는데 저장이 안 되는 것이 의도인지는 TC 메모대로 개발 확인)"
    finally:
        cfg.cancel()


@tc_check("TIO_09", "미지원 신호 타입 조합",
          "Vacuum 신호 타입을 Flange IO 로 → Save → 저장되지 않음 (출력은 Digital IO, 입력은 Flange IO 만 저장)",
          [("미지원 신호 타입",)], admin=False)
def tio_09(ctx):
    cfg = ToolCfg(ctx)
    cfg.open()
    try:
        opts = cfg.options(cfg.src_btn("Vacuum"))
        ctx.step(f"Vacuum 선택지 {opts}")
        cfg.set_src("Vacuum", "Flange IO")
        _rejected(ctx, cfg, "Vacuum = Flange IO")
        ctx.note = f"Vacuum 선택지 {opts} 중 Flange IO 저장 거부 확인"
    finally:
        cfg.cancel()
