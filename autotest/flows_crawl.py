"""전체 클릭 점검 (K01~): 메뉴마다 화면에 보이는 버튼·탭·토글·선택지를 하나씩 모두 눌러 본다.
(2026-10-22 사용자 요청: 30개로 제한하지 말고 모든 메뉴의 기능을 한 번씩 눌러 동작하는지 확인)

한 메뉴 안에서
1. 메뉴를 열고 누를 수 있는 요소를 모은다 (좌측 메뉴 바깥 콘텐츠 영역, 맨 위 화면만)
2. 하나씩 누름 → 결과 분류
   - 에러 문구가 새로 뜸 / 앱이 꺼짐            → 문제 (FAIL)
   - 대화상자·드롭다운이 열림                    → 안전한 버튼(Cancel·Close…)이나 ESC로 닫음
   - 화면이 바뀜(탭·하위 메뉴)                    → 그 화면도 깊이 max_depth까지 같은 방식으로 점검
   - 토글                                        → 한 번 더 눌러 원래대로
   - UIA로 누를 수 없음 / 비활성 / 위험 버튼     → 기록만 (FAIL 아님)
3. 끝나면 러너가 Home 값·계정을 원래대로 되돌린다
되돌릴 수 없는 버튼(삭제·저장·내보내기·실행 등)은 elements.yaml crawl.deny로 누르지 않는다.
메뉴 이름은 실행 때 좌측 메뉴에서 찾는다 → 버전마다 메뉴가 바뀌어도(v2.0.0: Recipe·Dashboard·Robot Control) 동작.
"""
import re
import time

from . import env
from .flows import SHORT, NotApplicable, check, flow
from .ui import EL, P

CFG = EL.get("crawl", {})
DENY = [re.compile(p, re.I) for p in CFG.get("deny", [])]
ALLOW = set(CFG.get("allow", []))
CLOSERS = CFG.get("close_buttons", ["Cancel", "Close", "No", "Discard", "취소", "닫기", "아니오"])
MAX_DEPTH = int(CFG.get("max_depth", 2))
MAX_CLICKS = int(CFG.get("max_clicks", 150))
CLICKABLE = ("Button", "TabItem", "CheckBox", "RadioButton", "ListItem", "Hyperlink", "SplitButton", "ComboBox")
DYN_DENY = set()  # 실행 중 파일·시스템 창을 띄운 버튼 (메뉴, key) — 같은 실행에서 다시 누르지 않음
ROLE = re.compile(P.get("nav_role_pattern", r"^[A-Z] \w+$"))


def _nm(e):
    return (e.element_info.name or "").strip()


def _content_left(ui):
    wr = ui.wrapper().rectangle()
    nav = [b.rectangle().right for b in ui.top_all("Button")
           if b.rectangle().left < wr.left + 60 and 0 < b.rectangle().width() < wr.width() / 3]
    return (max(nav) if nav else wr.left) + 5


def _elements(ui):
    """콘텐츠 영역의 누를 수 있는 요소 [(key, 요소)]. key = (종류, 이름, 같은 종류·이름 중 순서).
    화면이 바뀌는 순간엔 종류가 빈 요소 때문에 KeyError(None)가 날 수 있어 최대 3번 다시 읽음 (2026-10-26 K05 실패 원인)"""
    for i in range(3):
        try:
            return _elements_once(ui)
        except KeyError:
            time.sleep(1.0)
    return _elements_once(ui)


def _elements_once(ui):
    wr, x0 = ui.wrapper().rectangle(), _content_left(ui)
    es = []
    for e in ui.top_all():
        ei = e.element_info
        r = ei.rectangle
        if ei.control_type not in CLICKABLE or r.width() < 8 or r.height() < 8:
            continue
        if r.left < x0 or r.right > wr.right + 2 or r.bottom > wr.bottom + 2:
            continue
        if r.width() > 0.9 * wr.width() and r.height() > 0.8 * wr.height():
            continue  # 화면 전체 크기의 컨테이너 버튼
        es.append(e)
    es.sort(key=lambda e: (e.element_info.rectangle.top // 10, e.element_info.rectangle.left))
    out, count = [], {}
    for e in es:
        k = (e.element_info.control_type, _nm(e))
        count[k] = count.get(k, -1) + 1
        out.append(((k[0], k[1], count[k]), e))
    return out


def _find(ui, key):
    return next((e for k, e in _elements(ui) if k == key), None)


def _label(key):
    t, n, i = key
    return f"{t} '{n}'" + (f" #{i + 1}" if i else "") if n else f"{t}(이름 없음) #{i + 1}"


def _denied(name):
    if name in ALLOW:
        return False
    return bool(ROLE.match(name)) or any(p.search(name) for p in DENY)


def _sim(a, b):
    return len(a & b) / max(1, len(a | b))


def _is_selected(e):
    try:
        return bool(e.iface_selection_item.CurrentIsSelected)
    except Exception:
        return None


def _toggle_state(e):
    try:
        return e.iface_toggle.CurrentToggleState
    except Exception:
        return None


class Crawler:
    def __init__(self, ctx, menu):
        self.ctx, self.ui, self.menu = ctx, ctx.ui, menu
        self.rows, self.clicks, self.fails = [], 0, []
        self.pages = []
        self.nav_keys = set()  # '화면 전환'을 일으킨 버튼 (하위 화면에서 다시 누르지 않음)

    # ---------- 화면 열기 (메뉴 → 경로대로 누름) ----------
    def open(self, path):
        ui = self.ui
        ui.back_to_home()
        if self.menu != P.get("home_menu", "Home"):
            ui.goto(self.menu)
            time.sleep(0.5)
        for key in path:
            e = None
            ui.wait_for(lambda: _find(ui, key) is not None, 5)
            e = _find(ui, key)
            check(e is not None, f"[{self.menu}] 경로 요소를 다시 찾지 못함: {_label(key)}")
            ui.click(e, settle=1.5, label=f"[{self.menu}] {_label(key)}")

    def close_popup(self, base):
        """대화상자·드롭다운 닫기: 새로 뜬 안전한 버튼 → ESC. 원래 화면(base)과 비슷해지면 성공."""
        ui = self.ui
        for _ in range(3):
            names = ui.top_names()
            if _sim(names, base) > 0.85 and not ui.top_all("MenuItem"):
                return True
            btn = next((ui.top_find(c) for c in CLOSERS if c in names - base and ui.top_find(c)), None)
            if btn is not None:
                try:
                    ui.click(btn, settle=1.2, label=f"닫기 '{_nm(btn)}'")
                    continue
                except AssertionError:
                    pass
            ui.esc()
        return _sim(ui.top_names(), base) > 0.85

    # ---------- 한 화면 점검 ----------
    def crawl_page(self, path, queue):
        ui = self.ui
        self.open(path)
        base = ui.top_names()
        where = " > ".join([self.menu] + [_label(k) for k in path])
        if any(_sim(base, p) > 0.9 for p in self.pages):
            return  # 이미 점검한 화면 (다른 경로로 같은 화면)
        self.pages.append(base)
        els = _elements(ui)
        keys = [k for k, _ in els]
        # 라디오 원복 기준 = 이 화면에 들어왔을 때 선택돼 있던 것 (직전 선택 기준이면 Imperial→Metric 순으로 누른 뒤
        # Imperial로 '원복'해 단위가 바뀐 채 남았고, 저장 안 된 변경 때문에 Settings를 못 나가 앱 재시작 — 2026-10-22 15:23)
        self.radio_orig = [k for k, x in els if k[0] == "RadioButton" and _is_selected(x)]
        self.ctx.step(f"{where}: 요소 {len(keys)}개")
        for key in keys:
            if self.clicks >= MAX_CLICKS:
                self.rows.append((where, "-", f"상한 {MAX_CLICKS}회 도달 → 나머지 생략"))
                return
            name = key[1]
            if path and key in self.nav_keys:
                # 옆 하위 메뉴(General·Pallet·Tool…) — 이미 첫 화면에서 들어가 점검함. 하위 화면마다 다시 들어가면
                # 조합이 폭증(2026-10-26 K05 한 항목 35분) → 건너뜀
                self.rows.append((where, _label(key), "건너뜀 (하위 메뉴 이동 — 이미 점검)"))
                continue
            if (self.menu, key) in DYN_DENY:
                self.rows.append((where, _label(key), "건너뜀 (파일·시스템 창을 여는 버튼)"))
                continue
            if _denied(name):
                self.rows.append((where, _label(key), "건너뜀 (되돌릴 수 없는 버튼)"))
                continue
            if _sim(ui.top_names(), base) < 0.7:  # 앞 클릭 때문에 화면이 바뀌어 있으면 다시 열기
                self.open(path)
            e = _find(ui, key)
            if e is None:
                self.rows.append((where, _label(key), "다시 찾지 못함 (화면 변화)"))
                continue
            if not e.is_enabled():
                self.rows.append((where, _label(key), "비활성 (누르지 않음)"))
                continue
            self.press(where, path, key, e, base, queue)

    def press(self, where, path, key, e, base, queue):
        ui = self.ui
        before_txt, tog, layers0 = ui.window_texts(), _toggle_state(e), len(ui.top_layers())
        self.ctx.step(f"{where}: {_label(key)} 누르기 ({self.clicks + 1})")
        try:
            ui.click(e, settle=1.0, label=f"[{self.menu}] {_label(key)}")
        except AssertionError as ex:
            self.rows.append((where, _label(key), f"누를 수 없음 ({str(ex)[:60]})"))
            return
        self.clicks += 1
        if not env.app_running():
            self.fails.append(f"{where} {_label(key)}: 누른 뒤 앱이 꺼짐")
            self.rows.append((where, _label(key), "문제: 앱이 꺼짐"))
            raise AssertionError(f"{_label(key)}을(를) 누른 뒤 앱이 꺼짐 ({where})")
        time.sleep(0.3)
        from .winutil import close_native_dialogs
        native = close_native_dialogs()
        if native:
            # 파일 열기·저장 같은 Windows 기본 창: 앱 화면 밖이라 그대로 두면 열린 채 남음 → 취소로 닫고 이 버튼은 다시 안 누름
            # (2026-10-26 K02 Recipe 아이콘이 '열기' 창을 띄워 남아 있었음 — 사용자 요청: 안 뜨게)
            DYN_DENY.add((self.menu, key))
            self.rows.append((where, _label(key), f"파일·시스템 창 열림 {native} → 취소로 닫음 (이 버튼은 이후 누르지 않음)"))
            return
        errs = ui.error_texts(before_txt, ui.window_texts())
        after = ui.top_names()
        added, removed = after - base, base - after
        if errs:
            self.fails.append(f"{where} {_label(key)}: 에러 문구 {errs}")
            result = f"문제: 에러 문구 {errs}"
        elif ui.top_all("MenuItem") or len(ui.top_layers()) > layers0:
            # 새 층(대화상자·패널·드롭다운)이 생김 — 탭 전환처럼 같은 층 안의 내용 변화는 여기에 안 걸림 (2026-10-22 IO 탭 오분류 수정)
            ok = self.close_popup(base)
            result = f"열림 → {'닫음' if ok else '닫지 못함(화면 다시 열기)'} (+{len(added)})"
        elif ui.top_find("Home") is None and len(ui.rail()) < 4:
            # 'Home' 이름 버튼도 없고 접힌 아이콘 메뉴(Settings)도 없을 때만 전체 화면으로 봄 (2026-10-22 회귀 수정)
            # 좌측 메뉴가 사라진 전체 화면(편집기·모듈)으로 들어감 → 안쪽은 점검하지 않고 바로 빠져나옴
            ui.back_to_home()
            result = "전체 화면 열림 → 닫음 (안쪽은 점검 안 함)"
        elif _sim(after, base) < 0.6 or len(added) >= 10:
            result = f"화면 전환 (+{len(added)}/−{len(removed)})"
            self.nav_keys.add(key)
            if len(path) < MAX_DEPTH and key[0] in ("Button", "TabItem", "ListItem", "RadioButton"):
                queue.append(path + [key])
                result += " → 이 화면도 점검"
        elif added or removed:
            result = f"표시 변화 (+{len(added)}/−{len(removed)})"
        else:
            result = "반응 확인 (변화 없음)"
        # 토글·라디오는 원래대로
        if tog is not None and key[0] == "CheckBox":
            x = _find(ui, key)
            if x is not None and _toggle_state(x) != tog:
                ui.click(x, settle=1.0, label=f"원래대로 {_label(key)}")
                result += " · 원복"
        if key[0] == "RadioButton":
            if not getattr(self, "radio_orig", None):
                result += " · 원래 선택을 읽지 못해 원복 못 함"
            for rk in self.radio_orig:
                x = _find(ui, rk)
                if x is not None and not _is_selected(x):
                    ui.click(x, settle=1.0, label=f"원래 선택 {_label(rk)}")
                    result += f" · 원복({rk[1]})"
        self.rows.append((where, _label(key), result))

    def run(self):
        queue = [[]]
        while queue:
            path = queue.pop(0)
            try:
                self.crawl_page(path, queue)
            except (AssertionError, KeyError) as ex:
                if "앱이 꺼짐" in str(ex):
                    raise
                self.rows.append((" > ".join([self.menu] + [_label(k) for k in path]), "-", f"점검 중단: {ex}"))
        return self.rows


def _write(ctx, tc, rows, clicks, fails):
    p = ctx.outdir / f"{tc}_clicks.txt"
    lines = [f"{tc} 전체 클릭 점검 — 누름 {clicks}회, 문제 {len(fails)}건", ""]
    lines += [f"{w}\t{k}\t{r}" for w, k, r in rows]
    p.write_text("\n".join(lines), encoding="utf-8")
    ctx.files["detail"] = p.name


def _nav_names(ui):
    try:
        return [b.window_text() for b in ui.nav_items() if not ROLE.match(b.window_text() or "")]
    except Exception:
        return []


def _make(tc, cands):
    def fn(ctx):
        ui = ctx.ui
        if tc == "K99":  # 목록에 없는 새 메뉴 전부
            known = {n for _, c in MENUS for n in c} | set(CFG.get("skip_menus", []))
            menus = [n for n in _nav_names(ui) if n not in known and n not in P.get("nav_exclude", [])]
            if not menus:
                raise NotApplicable("목록 밖의 새 메뉴 없음")
        else:
            nav = _nav_names(ui) + [P.get("home_menu", "Home")]
            menus = [next((c for c in cands if c in nav), None)]
            if menus[0] is None:
                raise NotApplicable(f"이 버전에는 메뉴 없음 ({'/'.join(cands)})")
        rows, clicks, fails = [], 0, []
        for m in menus:
            cr = Crawler(ctx, m)
            try:
                cr.run()
            finally:
                rows += cr.rows
                clicks += cr.clicks
                fails += cr.fails
                _write(ctx, tc, rows, clicks, fails)
        kinds = {}
        for _, _, r in rows:
            k = r.split(" ")[0].rstrip(":")
            kinds[k] = kinds.get(k, 0) + 1
        ctx.note = f"{', '.join(menus)}: 누름 {clicks}회 · " + " · ".join(f"{k} {n}" for k, n in kinds.items())
        check(not fails, f"문제 {len(fails)}건: " + " / ".join(fails[:3]))
        check(clicks > 0, "누를 수 있는 요소를 하나도 누르지 못함")
    return fn


MENUS = [(m["tc"], m["names"]) for m in CFG.get("menus", [])]
CHIP_NAME = {"Home": "전체Home", "Recipe": "전체Recipe", "IO": "전체IO", "Log": "전체Log", "Settings": "전체설정",
             "Dashboard": "전체대시", "Robot Control": "전체로봇", "Quick Log": "전체QLog"}
for _tc, _names in MENUS + [("K99", [])]:
    _title = f"전체 클릭: {_names[0]}" if _names else "전체 클릭: 새 메뉴"
    flow(_tc, _title, "메뉴의 모든 버튼·탭·토글을 한 번씩 눌러 에러 문구·앱 종료가 없는지 확인 (위험 버튼 제외, 대화상자는 닫고 토글은 원복)",
         admin=True)(_make(_tc, _names))
    SHORT[_tc] = CHIP_NAME.get(_names[0] if _names else "", "새메뉴")  # 칩 폭(약 12자)에 맞춘 짧은 이름
