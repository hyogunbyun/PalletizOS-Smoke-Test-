"""Dr.Dart-Platform / PalletizOS 화면 접근 계층 (pywinauto UIA).

요소는 좌표가 아니라 이름표("Current Layer" 등)를 기준으로 같은 열·같은 행의 컨트롤을 찾는다.
창 크기·모니터가 바뀌어도 동작하게 하기 위함이다.
"""
import ctypes
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

ctypes.windll.shcore.SetProcessDpiAwareness(2)

import yaml  # noqa: E402
from pywinauto import Desktop, mouse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EL = yaml.safe_load((ROOT / "elements.yaml").read_text(encoding="utf-8"))
P = EL["palletizos"]
SPEED = max(0.5, float(EL.get("speed", 1.0)))            # 연결 이후 (평가 단계)
SPEED_CONNECT = max(0.5, float(EL.get("speed_connect", SPEED)))  # 연결 단계
_speed = [SPEED]  # 현재 적용 중인 배수 (env.ensure_ready 동안만 SPEED_CONNECT)


def set_speed(v):
    _speed[0] = max(0.5, float(v))
# background: UIA 명령으로 조작 (마우스·포커스 사용 안 함 → 실행 중 다른 업무 가능)
# mouse: 실제 마우스 클릭 (사람과 같은 입력 경로, 실행 중 PC 사용 불가)
MODE = EL.get("input_mode", "background")


STOP_FILE = ROOT / "results" / "stop.flag"  # 오버레이의 '자동화 종료' 버튼이 만든다


class StopRequested(BaseException):
    """사용자가 종료를 요청함. 흐름의 일반 예외 처리(except Exception)에 걸리지 않고 러너까지 올라가게 BaseException."""


PAUSE_FILE = ROOT / "results" / "pause.flag"  # 시나리오 녹화기가 녹화하는 동안 만든다


_STARTED = time.time()


def _stop_requested():
    """종료 요청이 이 프로세스가 시작된 뒤에 생긴 것인지. 그 전 것은 지난 실행의 잔여물이라 지우고 무시한다.
    2026-10-29: 10-27 18:23 의 stop.flag 가 남아 감시기·시작 팝업의 설치가 시작 직후 StopRequested 로 조용히 죽음
    (run_smoke 는 설치가 끝난 뒤에야 flag 를 지웠고, 감시기는 지우지 않았음)."""
    try:
        if STOP_FILE.stat().st_mtime < _STARTED - 2:
            STOP_FILE.unlink(missing_ok=True)
            return False
        return True
    except OSError:
        return False


def check_stop():
    if _stop_requested():
        raise StopRequested("사용자가 자동화 종료를 눌렀음")
    while PAUSE_FILE.exists():  # 녹화 중: 같은 앱을 동시에 조작하지 않게 대기 (종료 요청은 계속 확인)
        if _stop_requested():
            raise StopRequested("사용자가 자동화 종료를 눌렀음")
        time.sleep(0.5)


def pause(sec):
    """고정 대기. elements.yaml의 speed 배수만큼 줄인다 (2.0 → 절반). 대기 앞뒤로 종료 요청 확인."""
    check_stop()
    time.sleep(sec / _speed[0])
    check_stop()


class EnvError(Exception):
    """제품 결함이 아니라 실행 환경 문제 (언어, 창 없음, 사용자 개입 등)."""


class UserInterference(EnvError):
    pass


def _center(r):
    return ((r.left + r.right) // 2, (r.top + r.bottom) // 2)


def _cursor():
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


import ctypes.wintypes  # noqa: E402


@dataclass
class Side:
    """Left/Right 한쪽 열의 컨트롤 묶음."""
    name: str
    toggle: object = None
    recipe: object = None
    progress: str = ""
    layer: dict = field(default_factory=dict)
    boxes: dict = field(default_factory=dict)


class UI:
    def __init__(self):
        self.win = Desktop(backend="uia").window(title=EL["window_title"])
        self._last_mouse = None
        self.on_click = None  # 러너가 연결: 클릭한 요소 이름을 오버레이에 표시
        self.mode = MODE

    # ---------- 기본 ----------
    def exists(self):
        return self.win.exists(timeout=1)

    def warm_up(self):
        """Chromium 접근성 트리는 첫 조회 때 비어 있고 두 번째부터 채워진다."""
        for _ in range(3):
            self.win.descendants()
            pause(0.8)
            if any(t.window_text() for t in self.win.descendants(control_type="Text")):
                return
        raise EnvError("접근성 트리가 채워지지 않음")

    def wrapper(self):
        return self.win.wrapper_object()

    def hwnd(self):
        from .winutil import app_hwnd
        return app_hwnd(EL["window_title"])

    def image(self):
        """앱 창 이미지. background 모드는 PrintWindow(가려져 있어도 앱 화면), mouse 모드는 화면 캡처."""
        if self.mode == "background":
            from .winutil import capture
            return capture(self.hwnd())[0]
        return self.wrapper().capture_as_image()

    def screenshot(self, path):
        self.image().save(path)

    def dump_tree(self, path):
        lines = []
        for e in self.root().descendants():
            ei = e.element_info
            r = ei.rectangle
            lines.append(f"[{ei.control_type}] {ei.name!r} ({r.left},{r.top},{r.width()}x{r.height()})"
                         f" enabled={e.is_enabled()}")
        Path(path).write_text("\n".join(lines), encoding="utf-8")

    def wait_window_stable(self, timeout=90, hold=5):
        """앱 창이 hold초 동안 계속 있고 화면 요소가 읽힐 때까지 대기. 앱을 막 띄우면 시작 화면이 닫히고 본 창이 뜨는 사이
        창이 잠깐 없어짐 → 곧바로 조작하면 '창 없음'으로 실행기 오류(2026-10-26 10:33 실측). 안정되면 True."""
        end, since = time.time() + timeout, None
        while time.time() < end:
            check_stop()
            ok = False
            try:
                ok = self.exists() and len(self.wrapper().descendants()) > 20
            except Exception:
                ok = False
            if ok:
                since = since or time.time()
                if time.time() - since >= hold:
                    return True
            else:
                since = None
            time.sleep(0.5)
        return False

    def ensure_maximized(self):
        if self.mode == "background":
            from .winutil import is_minimized, maximize_keep_focus, show_no_activate
            h = self.hwnd()
            if is_minimized(h):  # 최소화되면 Chromium이 화면 갱신을 멈춤 → 포커스 없이 복원
                show_no_activate(h)
                pause(1.5)
            if not self.wrapper().is_maximized():
                maximize_keep_focus(h)
                pause(1.5)
            return
        w = self.wrapper()
        if not w.is_maximized():
            w.maximize()
            pause(1.5)
        w.set_focus()

    # ---------- 입력 (실제 마우스) ----------
    def check_interference(self):
        if self._last_mouse:
            cx, cy = _cursor()
            lx, ly = self._last_mouse
            if abs(cx - lx) > 4 or abs(cy - ly) > 4:  # 좌표 반올림 오차(1px) 허용
                raise UserInterference(f"실행 중 마우스가 움직임 (사용자 개입) {self._last_mouse}->{(cx, cy)}")

    def click(self, elem, settle=1.0, label=None):
        if self.mode == "background":
            return self._act_timed(elem, settle, label)
        self.check_interference()
        if elem is None:
            raise AssertionError("클릭할 요소를 찾지 못함")
        if not elem.is_enabled():
            raise AssertionError(f"비활성 요소 클릭 시도: {elem.window_text()!r}")
        x, y = _center(elem.rectangle())
        top = _layer_ok(elem, lp=self._lp())
        if top is not True:
            # 다른 화면 뒤에 가려진 요소를 누르면 위에 있는 엉뚱한 버튼이 눌린다 (실제 사고: 투어 Skip → Enable Robot)
            raise AssertionError(f"요소가 가려져 있어 클릭하지 않음: {elem.window_text()!r} (맨 위: {top!r})")
        if self.on_click:
            self.on_click(label or elem.window_text() or elem.element_info.control_type)
        mouse.click(coords=(x, y))
        self._last_mouse = (x, y)
        pause(settle)

    ACT_TIMEOUT = 20  # 누르기 명령 하나의 최대 대기(초)

    def _act_timed(self, elem, settle, label):
        """UIA 누르기 명령에 시간 제한. 앱이 명령에 응답하지 않으면 실행기 전체가 멈춰 있었음
        (2026-10-27 15:21 K01 레시피 선택 화면 이름 없는 버튼 #59: 18분 넘게 CPU 0, 종료 버튼도 안 먹음)
        → 20초 넘으면 AssertionError로 이 항목을 실패 처리하고 복구 절차(필요하면 앱 재시작)로 넘어감.
        막힌 명령은 별도 스레드에 남지만, 복구 때 앱을 재시작하면 같이 풀린다."""
        import threading
        box = {}

        def run():
            try:
                import comtypes
                comtypes.CoInitialize()  # 새 스레드에서 COM 사용 (STA). 메인 스레드 설정과 무관
            except Exception:
                pass
            try:
                self._act(elem, 0, label)
                box["ok"] = True
            except BaseException as e:  # noqa: BLE001
                box["err"] = e
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(self.ACT_TIMEOUT)
        if t.is_alive():
            try:
                from .events import ev
                ev(f"누르기 명령이 {self.ACT_TIMEOUT}초 동안 응답 없음: {label or elem.window_text()!r} → 이 항목 실패 처리")
            except Exception:
                pass
            raise AssertionError(f"누르기 명령이 {self.ACT_TIMEOUT}초 동안 응답 없음 (앱이 멈췄을 수 있음): {label or ''}")
        if "err" in box:
            raise box["err"]
        pause(settle)

    def _act(self, elem, settle, label):
        """UIA 명령으로 '누름'. Invoke → 기본 동작(DoDefaultAction) → Toggle → Select 순, 안 되면 부모로."""
        if elem is None:
            raise AssertionError("클릭할 요소를 찾지 못함")
        if not elem.is_enabled():
            raise AssertionError(f"비활성 요소 클릭 시도: {elem.window_text()!r}")
        top = _layer_ok(elem, lp=self._lp())
        if top is not True:
            raise AssertionError(f"요소가 가려져 있어 누르지 않음: {elem.window_text()!r} (맨 위: {top!r})")
        if self.on_click:
            self.on_click(label or elem.window_text() or elem.element_info.control_type)
        # 1차: 요소→부모 순으로 명시적 동작(Invoke·Toggle·Select)을 찾는다.
        #      표 셀처럼 기본 동작('두 번 클릭')만 있는 요소는 그걸 실행해도 선택되지 않음 → 행(부모)의 Invoke가 맞다 (실측)
        # 2차: 어디에도 없으면 기본 동작(DoDefaultAction)
        for legacy in (False, True):
            node = elem
            for _ in range(4):
                if _uia_press(node, legacy=legacy):
                    pause(settle)
                    return
                node = node.parent()
                if node is None:
                    break
        raise AssertionError(f"UIA로 누를 수 없는 요소: {elem.window_text()!r} ({elem.element_info.control_type})")

    def set_text(self, edit, text, label=None):
        """입력칸에 값 넣기 (background: ValuePattern, mouse: 클릭 후 타이핑)."""
        if self.on_click:
            self.on_click(label or f"입력: {text!r}")
        if self.mode == "background":
            edit.iface_value.SetValue(text)
        else:
            from pywinauto import keyboard
            self.click(edit, settle=0.3, label=label)
            keyboard.send_keys("^a{BACKSPACE}")
            if text:
                keyboard.send_keys(_escape_keys(text), pause=0.04, with_spaces=True)
        pause(1.2)

    def esc(self):
        """ESC 한 번 (background: 앱 창에 키 메시지 직접 전송 — 포커스 불필요)."""
        if self.mode == "background":
            from .winutil import post_key
            post_key(self.hwnd(), 0x1B)
        else:
            from pywinauto import keyboard
            keyboard.send_keys("{ESC}")
        pause(1.0)

    def click_xy(self, x, y, settle=1.0):
        self.check_interference()
        mouse.click(coords=(x, y))
        self._last_mouse = (x, y)
        pause(settle)

    # ---------- 탐색 ----------
    def root(self):
        """PalletizOS 영역 = 'v1.1.0' 버전 텍스트의 부모 그룹. 뒤에 깔린 Platform 화면과 분리한다."""
        for t in self.win.descendants(control_type="Text"):
            if re.fullmatch(r"v\d+\.\d+\.\d+", t.window_text() or ""):
                return t.parent()
        raise EnvError("PalletizOS 화면이 열려 있지 않음")

    def version(self):
        for t in self.root().children(control_type="Text"):
            if re.fullmatch(r"v\d+\.\d+\.\d+", t.window_text() or ""):
                return t.window_text()

    def _all(self, root=None, ctype=None):
        root = root or self.root()
        for i in range(3):
            try:
                return root.descendants(control_type=ctype) if ctype else root.descendants()
            except KeyError:
                # 앱 화면이 막 다시 그려지는 중엔 종류(control type)가 없는 요소가 섞여 pywinauto가 KeyError(None)
                # (2026-10-22 앱 재시작 직후 실측) → 잠깐 뒤 다시
                time.sleep(1.0)
        return root.descendants(control_type=ctype) if ctype else root.descendants()

    def by_name(self, name, ctype="Button", root=None):
        hits = [e for e in self._all(root, ctype) if (e.window_text() or "") == name]
        return hits[0] if hits else None

    def texts(self, root=None):
        return [t.window_text() for t in self._all(root, "Text") if t.window_text()]

    def visible_texts(self):
        """판정용: 현재 PalletizOS 영역에서 보이는 문구 + 버튼 이름 집합."""
        out = set()
        for e in self._all():
            ei = e.element_info
            if ei.control_type in ("Text", "Button") and ei.name and ei.rectangle.width() > 0:
                out.add(ei.name.strip())
        return out

    def check_language(self):
        have = set(self.texts())
        missing = [a for a in EL["language_anchors"] if a not in have]
        if missing:
            raise EnvError(f"UI 언어가 English가 아님 (없는 문구: {missing})")

    # ---------- 맨 위 화면 (메뉴 페이지·편집기·Recovery 등 어디서나) ----------
    def _lp(self):
        """층 부모 Group (캐시). 앱이 다시 뜨면 무효가 되므로 실패 시 다시 찾는다."""
        lp = getattr(self, "_lp_cache", None)
        try:
            if lp is not None and lp.rectangle().width() > 0:
                return lp
        except Exception:
            pass
        self._lp_cache = _layer_parent(self.win)
        return self._lp_cache

    def top_layers(self):
        """화면 전체를 덮는 형제 중 마지막(맨 위 화면)과 그 뒤에 붙은 작은 층(대화상자·패널·알림)."""
        lp = self._lp()
        sibs, wr = lp.children(), lp.rectangle()
        full = [i for i, x in enumerate(sibs)
                if x.rectangle().width() >= 0.9 * wr.width() and x.rectangle().height() >= 0.8 * wr.height()]
        out = sibs[(max(full) if full else 0):]
        # 드롭다운·⋮ 메뉴 같은 팝업은 층 구조 밖(문서 끝)에 따로 붙는다(포털) → 그것도 맨 위로 본다
        try:
            tiny = lp.parent()
            rid = tiny.element_info.runtime_id
            out += [c for c in tiny.parent().children() if c.element_info.runtime_id != rid]
        except Exception:
            pass
        return out

    def top_all(self, ctype=None):
        out = []
        for s in self.top_layers():
            out += s.descendants(control_type=ctype) if ctype else s.descendants()
        return out

    def top_find(self, name, ctype="Button", startswith=False):
        for e in self.top_all(ctype):
            n = (e.element_info.name or "").strip()
            if (n.startswith(name) if startswith else n == name) and e.element_info.rectangle.width() > 0:
                return e
        return None

    def top_names(self):
        return {(e.element_info.name or "").strip() for e in self.top_all()
                if e.element_info.name and e.element_info.rectangle.width() > 0}

    def on_home(self):
        n = self.top_names()
        return P["current_layer"] in n and "Select Recipe" not in n

    # ---------- 좌측 메뉴 이동 (펼친 메뉴: 이름 / Settings 화면처럼 접힌 메뉴: 아이콘 순서) ----------
    def remember_nav(self):
        """펼친 메뉴에서 순서를 기억해 둔다 (접힌 아이콘 메뉴에는 이름이 없음). 첫 항목은 역할 버튼."""
        try:
            self._nav_order = [b.window_text() for b in self.nav_items()]
        except Exception:
            pass

    def rail(self):
        """접힌 아이콘 메뉴 버튼들 (위에서 아래 순, Recovery·Enable 아이콘 포함)."""
        wr = self.wrapper().rectangle()
        return sorted([b for b in self.top_all("Button") if b.rectangle().right < wr.left + 110
                       and b.rectangle().width() > 0], key=lambda b: b.rectangle().top)

    def has_menu(self, name):
        """이 버전의 좌측 메뉴에 name(또는 별칭)이 있는지. 메뉴 순서를 아직 못 읽었으면 None."""
        order = getattr(self, "_nav_order", None)
        if not order:
            return None
        return any(c in order for c in P.get("menu_alias", {}).get(name, [name]))

    def goto(self, name, settle=2.5):
        for c in P.get("menu_alias", {}).get(name, [name]):  # 버전마다 바뀐 메뉴 이름
            if c in (getattr(self, "_nav_order", None) or []) or self.top_find(c) is not None:
                name = c
                break
        b = self.top_find(name)
        if b is not None and b.rectangle().right < self.wrapper().rectangle().left + 300:
            self.click(b, settle=settle, label=f"메뉴 {name}")
            return
        order = getattr(self, "_nav_order", None)
        if not order or name not in order:
            raise AssertionError(f"메뉴 '{name}'을(를) 찾을 수 없음 (메뉴 순서 미확인)")
        r = self.rail()
        idx = order.index(name)
        if idx >= len(r):
            raise AssertionError(f"접힌 메뉴에서 '{name}' 아이콘을 찾지 못함")
        self.click(r[idx], settle=settle, label=f"메뉴 {name}(아이콘)")

    def back_to_home(self):
        """어느 화면(메뉴·패널·대화상자·편집기·Recovery)에 있든 PalletizOS Home으로 돌아온다."""
        try:  # 앱이 띄운 Windows 파일·시스템 창이 남아 있으면 먼저 취소로 닫음
            from .winutil import close_native_dialogs
            close_native_dialogs()
        except Exception:
            pass
        for _ in range(6):
            n = self.top_names()
            if P["current_layer"] in n and not ({"Select Recipe", "Jog +", "Quick Log"} & n) \
                    and not any(e.element_info.control_type == "MenuItem" for e in self.top_all("MenuItem")):
                return True
            leave = next((c for c in ("Discard & Exit", "Discard", "Discard Changes", "Don't Save", "Leave", "Leave without saving",
                                      "Exit without saving", "저장 안 함", "나가기") if c in n), None)
            if leave is not None and self.top_find(leave) is not None:
                # 저장 안 된 변경이 있어 화면을 못 나갈 때 뜨는 확인창 → 저장하지 않는 쪽 (2026-10-22 Settings 복귀 실패 대응)
                self.click(self.top_find(leave), settle=1.5, label=f"저장 안 함 '{leave}'")
                continue
            if "Exit Recovery Module" in n:
                self.click(self.top_find("Exit Recovery Module"), settle=3)
            elif "Select Recipe" in n:
                self.click(self.top_find("Cancel"), settle=1.5)
            elif "Jog +" in n and self.close_panel("Jog +"):
                pass
            elif "Quick Log" in n and self.close_panel("Quick Log"):
                pass
            elif self.top_all("MenuItem"):
                self.esc()
            elif {"Box", "Stack"} <= n:   # 레시피 편집기(v1) → 왼쪽 위 X
                self._close_fullscreen()
            else:
                try:  # 일반 메뉴 화면: 펼친 메뉴의 'Home' 또는 접힌 아이콘 메뉴(Settings)로 이동
                    self.goto("Home")
                except AssertionError:
                    # 좌측 메뉴가 아예 없는 전체 화면(v2.0.0 레시피 편집기 등)일 때만 X로 닫는다.
                    # 2026-10-22 회귀: 'Home' 이름 버튼이 없다는 이유만으로 X를 누르게 했더니, 메뉴가 아이콘으로 접힌
                    # Settings 화면에서 로고를 눌러 Home 복귀 실패 → 항목마다 앱 재시작(S01~S04) → 메뉴 이동을 먼저 시도하도록 수정
                    self._close_fullscreen()
        if not self.on_home():
            raise AssertionError("Home 화면으로 돌아오지 못함")
        return True

    def _close_fullscreen(self):
        """좌측 메뉴가 없는 전체 화면(편집기) 닫기: 왼쪽 위 이름 없는 X → '저장 안 함' 확인창. X가 없으면 ESC."""
        wr = self.wrapper().rectangle()
        x = [b for b in self.top_all("Button") if b.rectangle().left < wr.left + 120
             and b.rectangle().top < wr.top + 150 and not b.window_text() and b.rectangle().width() > 0]
        if not x:
            self.esc()
            return
        self.click(x[0], settle=2, label="전체 화면 닫기(X)")
        for c in ("Discard & Exit", "Discard", "Don't Save", "Leave", "No"):  # '저장 안 하고 나갈까요?' 류 확인창 — 저장하지 않는 쪽만
            d = self.top_find(c)
            if d is not None:
                self.click(d, settle=1.5, label=f"저장 안 함 '{c}'")
                break

    # ---------- 계정 ----------
    def current_role(self):
        for b in self.top_all("Button"):
            m = re.fullmatch(r"([A-Z]) (\w+)", b.window_text() or "")
            if m and b.rectangle().right < self.wrapper().rectangle().left + 300:
                return m.group(2)
        return None

    def wait_role(self, timeout=20):
        """로그인 직후엔 좌측 역할 버튼이 몇 초 늦게 그려진다(2026-10-21 실측: 로그인 6초 뒤에도 없음) → 보일 때까지 대기."""
        found = []
        self.wait_for(lambda: found.append(self.current_role()) or found[-1] is not None, timeout)
        return found[-1] if found else None

    def login_as(self, role, password=None):
        """좌측 역할 버튼 → Change Account → 역할 선택 → (비밀번호) Confirm."""
        now = self.wait_role()
        if now == role:
            return
        if now is None:
            raise EnvError("좌측 계정(역할) 버튼을 찾지 못함 — 화면이 아직 로딩 중이거나 팝업이 가리고 있음")
        cur = self.top_find(f"{now[0]} {now}")
        self.click(cur, settle=2, label="계정 메뉴")
        target = self.top_find(f"{role[0]} {role}")
        if target is None:
            raise EnvError(f"계정 '{role}'이(가) 목록에 없음")
        self.click(target, settle=2, label=f"계정 {role}")
        prompt = next((t for t in self.top_all("Text") if (t.window_text() or "").startswith("Please enter the password")), None)
        if prompt is not None:
            if not password:
                self.click(self.top_find("Cancel"), settle=1.5)
                raise EnvError(f"{role} 비밀번호가 필요함 (실행 시 입력하세요)")
            pr = prompt.rectangle()
            edit = min((e for e in self.top_all("Edit") if e.rectangle().top >= pr.bottom - 5),
                       key=lambda e: e.rectangle().top)
            self.set_text(edit, password, label="비밀번호 입력")
            self.click(self.top_find("Confirm"), settle=3, label="Confirm")
        if not self.wait_for(lambda: self.current_role() == role, 10):
            raise EnvError(f"{role} 로그인 실패 (비밀번호 확인)")
        self.remember_nav()

    # ---------- 레이아웃별 버튼 ----------
    def go_home_button(self):
        """'Go To Home Position' — 큰 화면은 이름 있는 버튼, 작은 화면(3D 뷰)은 Release Vacuum 왼쪽 아이콘 2개 중 아래."""
        b = self.by_name(P["go_home"])
        if b is not None:
            return b
        rv = self.by_name(P["release_vacuum"])
        if rv is None:
            return None
        rr = rv.rectangle()
        # Release Vacuum 바로 왼쪽(간격 30px 이내)에 붙은 아이콘 2개만. 더 왼쪽의 Left 열 −/+ 버튼을 잡지 않게 (실측)
        icons = sorted([x for x in self._all(None, "Button") if not x.window_text()
                        and 0 <= rr.left - x.rectangle().right <= 30
                        and rr.top - 10 <= x.rectangle().top <= rr.bottom and x.rectangle().width() < rr.width()],
                       key=lambda x: x.rectangle().top)
        return icons[-1] if len(icons) >= 2 else None

    # ---------- Left / Right 열 해석 ----------
    def sides(self):
        root = self.root()
        allx = list(self._all(root))
        texts = [e for e in allx if e.element_info.control_type == "Text"]
        labels = {n: next((t for t in texts if t.window_text() == n), None) for n in P["side_labels"]}
        checks = [e for e in allx if e.element_info.control_type == "CheckBox"]
        buttons = [e for e in allx if e.element_info.control_type == "Button"]
        edits = [e for e in allx if e.element_info.control_type == "Edit"]
        result = {}
        for n, lab in labels.items():
            if lab is None:
                raise EnvError(f"'{n}' 열 이름표 없음")
            lr = lab.rectangle()
            s = Side(n)
            # 토글: 이름표 바로 왼쪽, 같은 행
            s.toggle = min((c for c in checks if abs(_center(c.rectangle())[1] - _center(lr)[1]) < lr.height()
                            and c.rectangle().right <= lr.left + 5),
                           key=lambda c: lr.left - c.rectangle().right, default=None)
            # 레시피 드롭다운: 이름표 아래 첫 번째 넓은 버튼 → 이 버튼의 좌우 폭이 곧 열의 범위
            cand = [b for b in buttons if b.rectangle().top > lr.bottom and b.rectangle().width() > 4 * lr.width()
                    and b.rectangle().left - 60 <= lr.left <= b.rectangle().right]
            s.recipe = min(cand, key=lambda b: b.rectangle().top, default=None)
            if s.recipe is None:
                raise EnvError(f"'{n}' 열 레시피 버튼 없음")
            colL, colR = s.recipe.rectangle().left - 40, s.recipe.rectangle().right + 40
            incol = lambda e: colL <= _center(e.rectangle())[0] <= colR  # noqa: E731
            ctexts = [t for t in texts if incol(t)]
            s.progress = self._right_of(ctexts, P["progress"])
            for key, label in (("layer", P["current_layer"]), ("boxes", P["boxes_on_layer"])):
                s.__dict__[key] = self._counter(label, ctexts, [b for b in buttons if incol(b)],
                                                [e for e in edits if incol(e)])
            result[n] = s
        return result

    @staticmethod
    def _right_of(ctexts, label):
        lab = next((t for t in ctexts if t.window_text() == label), None)
        if not lab:
            return None
        lr = lab.rectangle()
        row = [t for t in ctexts if t is not lab and abs(_center(t.rectangle())[1] - _center(lr)[1]) < lr.height()
               and t.rectangle().left > lr.right]
        row.sort(key=lambda t: t.rectangle().left)
        return row[0].window_text() if row else None

    @staticmethod
    def _counter(label, ctexts, cbuttons, cedits):
        """'Current Layer' 같은 이름표 아래의 [값 입력칸] / [최대값] [−] [+] 한 줄."""
        lab = next((t for t in ctexts if t.window_text() == label), None)
        if not lab:
            return {}
        lr = lab.rectangle()
        edit = min((e for e in cedits if e.rectangle().top >= lr.bottom - 5),
                   key=lambda e: e.rectangle().top, default=None)
        if edit is None:
            return {}
        er = edit.rectangle()
        cy, h = _center(er)[1], er.height()
        row_btn = sorted((b for b in cbuttons if abs(_center(b.rectangle())[1] - cy) < h / 2
                          and b.rectangle().left >= er.right - 5), key=lambda b: b.rectangle().left)
        row_txt = sorted((t for t in ctexts if abs(_center(t.rectangle())[1] - cy) < h / 2),
                         key=lambda t: t.rectangle().left)
        try:
            value = edit.iface_value.CurrentValue
        except Exception:
            value = ""
        seq = [t.window_text() for t in row_txt]
        mx = seq[seq.index("/") + 1] if "/" in seq and seq.index("/") + 1 < len(seq) else None
        return {
            "edit": edit, "value": value, "max": mx,
            "minus": row_btn[0] if len(row_btn) >= 1 else None,
            "plus": row_btn[1] if len(row_btn) >= 2 else None,
        }

    # ---------- 상태 스냅샷 ----------
    def snapshot(self):
        """복구 확인용 화면 값. 위젯 객체가 아니라 비교 가능한 값만 담는다."""
        sides = self.sides()
        snap = {}
        for n, s in sides.items():
            snap[n] = {
                "on": _toggle(s.toggle),
                "recipe": s.recipe.window_text(),
                "recipe_enabled": s.recipe.is_enabled(),
                "progress": s.progress,
                "layer": (s.layer.get("value"), s.layer.get("max")),
                "boxes": (s.boxes.get("value"), s.boxes.get("max")),
            }
        snap["status"] = self.robot_status()
        snap["enable_button"] = self.enable_button_name()
        return snap

    def robot_status(self):
        """상단 가운데 상태 문구 (예: 'Robot Not Enabled')."""
        sides = self.sides()
        lr = self.by_name(P["side_labels"][0], "Text").rectangle()
        left_end = sides["Left"].recipe.rectangle().right
        right_start = sides["Right"].recipe.rectangle().left
        for t in self._all(None, "Text"):
            r = t.rectangle()
            if left_end < _center(r)[0] < right_start and abs(_center(r)[1] - _center(lr)[1]) < lr.height():
                return t.window_text()
        return None

    def enable_button_name(self):
        """좌측 하단 Enable Robot 자리 버튼의 현재 이름 (누르면 바뀔 수 있음)."""
        rec = self.by_name(P["recovery"])
        if rec is None:
            return None
        rr = rec.rectangle()
        below = [b for b in self._all(None, "Button") if b.rectangle().top >= rr.bottom - 5
                 and abs(b.rectangle().left - rr.left) < 20]
        below.sort(key=lambda b: b.rectangle().top)
        return below[0].window_text() if below else None

    def nav_items(self):
        """좌측 메뉴(역할에 따라 개수가 다름). 버전 텍스트 아래, Recovery 위의 버튼들."""
        root = self.root()
        ver = next(t for t in root.children(control_type="Text") if re.fullmatch(r"v\d+\.\d+\.\d+", t.window_text()))
        vr = ver.rectangle()
        rec = self.by_name(P["recovery"])
        out = []
        for b in root.children(control_type="Button"):
            r = b.rectangle()
            name = b.window_text() or ""
            if (r.top > vr.bottom and (rec is None or r.bottom <= rec.rectangle().top)
                    and abs(r.left - vr.left) < 60 and name):
                out.append(b)
        return out

    def nav_targets(self):
        pat = re.compile(P["nav_role_pattern"])
        return [b.window_text() for b in self.nav_items()
                if b.window_text() not in P["nav_exclude"] and not pat.match(b.window_text())]


    # ---------- 진행 상태 모델 ----------
    # 화면의 층/박스/진행률은 '완료 박스 총개수 N' 하나로 설명된다 (2026-10-19 실측):
    #   N = (층-1)*층당박스 + 현재층박스, 진행률 = round(100*N/전체)
    #   층 [+]/[−] = N을 다음/이전 층 경계로, 박스 [+]/[−] = N±1, [−]는 N=0, [+]는 N=전체에서만 비활성
    def counter(self, side):
        s = self.sides()[side]
        L, B = s.layer, s.boxes
        layers, bm = int(L["max"]), int(B["max"])
        n = (int(L["value"]) - 1) * bm + int(B["value"])
        return {
            "n": n, "total": layers * bm, "bm": bm, "layers": layers,
            "progress": s.progress,
            "en": {"layer-": L["minus"].is_enabled(), "layer+": L["plus"].is_enabled(),
                   "boxes-": B["minus"].is_enabled(), "boxes+": B["plus"].is_enabled()},
            "side": s,
        }

    def press(self, side, key, settle=0.9):
        """key: 'layer+', 'layer-', 'boxes+', 'boxes-'"""
        s = self.sides()[side]
        grp = s.layer if key.startswith("layer") else s.boxes
        kor = {"layer": "층", "boxes": "박스"}[key[:-1]]
        self.click(grp["plus" if key.endswith("+") else "minus"], settle=settle, label=f"{side} {kor} [{key[-1]}]")

    def set_n(self, side, target):
        """N을 target으로 맞춘다 (층 버튼으로 크게, 박스 버튼으로 잘게)."""
        for _ in range(400):
            c = self.counter(side)
            n, bm = c["n"], c["bm"]
            if n == target:
                return
            if target > n:
                key = "layer+" if (n // bm + 1) * bm <= target and c["en"]["layer+"] else "boxes+"
            else:
                prev = (n - 1) // bm * bm if n % bm else n - bm
                key = "layer-" if prev >= target and c["en"]["layer-"] else "boxes-"
            self.press(side, key, settle=0.6)
        raise AssertionError(f"{side} N을 {target}으로 맞추지 못함")

    # ---------- 레시피 대화상자 ----------
    def dialog_open(self, title="Select Recipe"):
        return any(t.window_text() == title for t in self.wrapper().descendants(control_type="Text"))

    def recipe_items(self):
        """열린 Select Recipe 대화상자의 목록 [(이름, 버튼, 오류아이콘여부)]."""
        w = self.wrapper()
        title = next(t for t in w.descendants(control_type="Text") if t.window_text() == "Select Recipe")
        tr = title.rectangle()
        btns = self.top_all("Button")  # 뒤에 깔린 Platform 화면 버튼 제외
        apply_r = next(b for b in btns if b.window_text() == "Apply").rectangle()
        img = self.image()
        wr = w.rectangle()
        # 대화상자 영역(제목 아래 ~ Apply 위) 안의 이름 있는 버튼 중, 왼쪽 끝이 나란한 가장 큰 묶음 = 목록 항목.
        # 화면 크기에 따라 항목 안에 이름 없는 버튼이 들어 있거나 'Close dialog'가 창 전체(배경)로 잡혀서
        # 자식 유무·닫기 버튼 위치는 기준으로 쓰지 않는다 (2026-10-19 1920×1080 실측)
        cand = [b for b in btns if (b.window_text() or "").strip() and tr.bottom < b.rectangle().top and b.rectangle().left >= tr.left - 20
                and b.rectangle().bottom < apply_r.top and b.rectangle().right <= apply_r.right + 20
                and b.window_text() not in ("Apply", "Cancel", "Close dialog")]
        groups = {}
        for b in cand:
            groups.setdefault(b.rectangle().left // 8, []).append(b)
        items = max(groups.values(), key=len) if groups else []
        out = []
        for b in sorted(items, key=lambda x: x.rectangle().top):
            out.append((b.window_text(), b, _has_red(img, b.rectangle(), wr)))
        return out

    def win_button(self, name):
        """창 전체에서 이름으로 버튼 찾기. name은 문자열 또는 후보 목록(한·영)."""
        names = [name] if isinstance(name, str) else list(name)
        return next((b for b in self.wrapper().descendants(control_type="Button") if b.window_text() in names), None)

    # ---------- 떠 있는 패널 / 팝업 ----------
    def close_panel(self, title):
        """'Jog +' 같은 떠 있는 패널을 제목 오른쪽의 X(Close)로 닫는다."""
        w = self.wrapper()
        t = next((x for x in w.descendants(control_type="Text") if x.window_text() == title), None)
        if t is None:
            return False
        tr = t.rectangle()
        closes = [b for b in w.descendants(control_type="Button") if b.window_text() == "Close"
                  and b.rectangle().left > tr.right and abs(_center(b.rectangle())[1] - _center(tr)[1]) < 3 * tr.height()]
        if not closes:
            return False
        self.click(min(closes, key=lambda b: b.rectangle().left), settle=1.2)
        return True

    def window_texts(self):
        return {(e.window_text() or "").strip() for e in self.wrapper().descendants()
                if e.element_info.control_type in ("Text", "Button") and e.window_text()}

    @staticmethod
    def error_texts(before, after):
        """새로 나타난 문구 중 에러로 보이는 것 (무시 목록 제외)."""
        words = [w.lower() for w in EL["error_words"]]
        ign = set(EL["ignore_texts"])
        return sorted(t for t in after - before
                      if t not in ign and any(w in t.lower() for w in words))

    def wait_for(self, cond, timeout=10, step=0.1):
        end = time.time() + timeout
        while time.time() < end:
            check_stop()
            try:
                if cond():
                    return True
            except Exception:
                pass
            time.sleep(step)
        return False


def _escape_keys(s):
    """pywinauto send_keys의 특수문자(+^%~(){}[])를 글자 그대로 입력되게 감싼다."""
    return "".join("{" + c + "}" if c in "+^%~(){}[]" else c for c in s)


def _layer_parent(win):
    """Platform 화면들이 형제로 붙는 '층 부모' Group (Document → 2x2 Group → 가장 큰 Group)."""
    doc = win.descendants(control_type="Document")[0]
    tiny = doc.children()[0]
    return max(tiny.children(), key=lambda g: g.rectangle().width() * g.rectangle().height())


def _layer_ok(elem, win=None, lp=None):
    """맨 위 화면보다 뒤에 깔린 층의 요소면 그 설명을, 아니면 True.

    Chromium의 ElementFromPoint는 바깥 Document를 돌려줘 가림을 판정할 수 없다 (실측).
    대신 DOM 순서를 쓴다: 층 부모 아래에서 '화면 전체를 덮는 형제' 중 마지막 것이 맨 위 화면이고,
    그보다 앞쪽 형제(Platform 홈·투어·하단바 등)는 가려져 있다. 그 뒤에 붙은 작은 층(대화상자·패널·알림)은 허용.
    실제 사고: 가려진 Platform 투어 'Skip'을 누르자 위에 있던 PalletizOS 'Enable Robot'이 눌림.
    """
    from pywinauto import Desktop
    if lp is None:  # UI.click은 캐시된 층 부모를 넘겨 클릭마다 전체 트리를 훑지 않는다
        win = win or Desktop(backend="uia").window(title=EL["window_title"])
        try:
            lp = _layer_parent(win)
        except Exception:
            return True
    wr = lp.rectangle()
    sibs = lp.children()
    ids = [x.element_info.runtime_id for x in sibs]
    full = [i for i, x in enumerate(sibs)
            if x.rectangle().width() >= 0.9 * wr.width() and x.rectangle().height() >= 0.8 * wr.height()]
    top = max(full) if full else 0
    lp_id = lp.element_info.runtime_id
    node = elem
    for _ in range(80):
        p = node.parent()
        if p is None:
            return True  # 층 부모 밖(포털 등) → 위에 뜬 층으로 본다
        if p.element_info.runtime_id == lp_id:
            rid = node.element_info.runtime_id
            idx = ids.index(rid) if rid in ids else top
            return True if idx >= top else f"맨 위 화면(#{top}) 뒤 층 요소 #{idx}"
        node = p
    return True


def _uia_press(elem, legacy=False):
    """요소 하나에 UIA '누름' 시도. legacy=False면 명시적 패턴만, True면 기본 동작(DoDefaultAction)만. 성공하면 True."""
    from pywinauto.uia_defines import get_elem_interface
    el = elem.element_info.element
    ct = elem.element_info.control_type
    if legacy:
        order = ["Legacy"]
    elif ct == "CheckBox":
        order = ["Toggle", "Invoke", "SelectionItem"]
    elif ct == "RadioButton":
        order = ["SelectionItem", "Invoke"]
    else:
        order = ["Invoke", "Toggle", "SelectionItem"]
    for pat in order:
        try:
            if pat == "Legacy":
                acc = get_elem_interface(el, "LegacyIAccessible")
                if not (acc.CurrentDefaultAction or "").strip():
                    continue  # 기본 동작이 없는 요소(그냥 글자)는 건너뜀 → 부모로
                acc.DoDefaultAction()
            elif pat == "Invoke":
                get_elem_interface(el, "Invoke").Invoke()
            elif pat == "Toggle":
                get_elem_interface(el, "Toggle").Toggle()
            else:
                get_elem_interface(el, "SelectionItem").Select()
            return True
        except Exception:
            continue
    return False


def _has_red(img, r, wr):
    """목록 항목 왼쪽 부분에 빨간 오류 아이콘이 있는지 픽셀로 판단 (UIA에 아이콘이 노출되지 않음)."""
    box = (r.left - wr.left, r.top - wr.top, r.left - wr.left + min(120, r.width()), r.bottom - wr.top)
    crop = img.crop(box).convert("RGB")
    red = sum(1 for (R, G, B) in crop.getdata() if R > 190 and G < 80 and B < 80)
    return red > 30


def _toggle(cb):
    if cb is None:
        return None
    try:
        return bool(cb.iface_toggle.CurrentToggleState)
    except Exception:
        return None
