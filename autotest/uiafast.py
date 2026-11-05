"""pywinauto UIA 조회 가속 — 트리를 읽을 때 속성을 한 번에 받아 둔다 (UIA CacheRequest).

2026-11-04 측정(H04·R01·K02, 102초): 요소 속성을 하나씩 앱에 묻는 데 약 47초(종류 16 · 위치 14 · 핸들 10 · 이름 4 · 클래스 3).
요소 하나에 속성 하나마다 프로세스 간 호출이 일어나서다. FindAllBuildCache 로 트리를 읽을 때 같이 받아 두면 호출이 한 번으로 줄어든다.

안정성 규칙
- 종류·핸들·클래스: 요소가 살아 있는 동안 바뀌지 않음 → 받아 둔 값을 계속 쓴다.
- 이름·위치: 화면 상태에 따라 바뀜 → 받아 둔 지 FRESH_SEC 이내이고 그 사이 입력(클릭·키·값 입력)이 없을 때만 쓴다.
  그 밖에는 지금처럼 앱에 직접 묻는다. 입력은 ui.py 가 invalidate() 로 알린다.
- 캐시 조회가 실패하면 원래 방식(FindAll)으로 되돌아간다. SMOKE_UIA_CACHE=0 이면 전체를 끈다.
"""
import os
import time

from comtypes import COMError
from pywinauto import uia_element_info as uei
from pywinauto.uia_defines import IUIA
from pywinauto.win32structures import RECT

FRESH_SEC = 0.5
_gen = [0]  # 입력 세대 — 클릭·키 입력마다 1 증가
_req = [None]


def invalidate():
    """입력이 일어남 → 이름·위치 캐시와 직전 트리 결과를 낡은 것으로."""
    _gen[0] += 1
    _walks.clear()


def _cache_request():
    if _req[0] is None:
        u = IUIA()
        cr = u.iuia.CreateCacheRequest()
        for pid in (u.UIA_dll.UIA_ControlTypePropertyId, u.UIA_dll.UIA_NamePropertyId,
                    u.UIA_dll.UIA_BoundingRectanglePropertyId, u.UIA_dll.UIA_NativeWindowHandlePropertyId,
                    u.UIA_dll.UIA_ClassNamePropertyId):
            cr.AddProperty(pid)
        _req[0] = cr
    return _req[0]


def _prefetch(info, el):
    """캐시된 속성을 info._pf 에 (정적 값은 영구, 이름·위치는 세대·시각과 함께)."""
    try:
        r = el.CachedBoundingRectangle
        info._pf = {"ct": el.CachedControlType, "h": el.CachedNativeWindowHandle, "cls": el.CachedClassName,
                    "name": el.CachedName, "rect": (r.left, r.top, r.right, r.bottom), "gen": _gen[0], "t": time.monotonic()}
    except COMError:
        pass


def _fresh(info):
    pf = getattr(info, "_pf", None)
    return pf is not None and pf["gen"] == _gen[0] and time.monotonic() - pf["t"] < FRESH_SEC


_orig_get_elements = uei.UIAElementInfo._get_elements
_orig_ct = uei.UIAElementInfo._get_current_control_type
_orig_h = uei.UIAElementInfo._get_current_handle
_orig_cls = uei.UIAElementInfo._get_current_class_name
_orig_name = uei.UIAElementInfo._get_current_name
_orig_rect = uei.UIAElementInfo.rectangle


def _get_elements(self, tree_scope, cond=None, cache_enable=False):
    cond = IUIA().true_condition if cond is None else cond
    try:
        arr = self._element.FindAllBuildCache(tree_scope, cond, _cache_request())
    except (COMError, ValueError):
        return _orig_get_elements(self, tree_scope, cond, cache_enable)
    out = []
    for n in range(arr.Length):
        try:
            el = arr.GetElement(n)
            info = uei.UIAElementInfo(el, cache_enable)
        except COMError:
            continue
        _prefetch(info, el)
        out.append(info)
    return out


WALK_FRESH_SEC = 0.3  # 같은 요소의 트리를 입력 없이 이 시간 안에 다시 읽으면 직전 결과를 쓴다
_walks = {}  # (runtime id, control_type 또는 None) -> (세대, 시각, [UIAElementInfo])
_orig_desc = uei.UIAElementInfo.descendants


def _descendants(self, **kwargs):
    """같은 순간 같은 화면을 여러 번 읽는 중복 제거 (클릭 1회에 트리 10번 안팎 읽음, 2026-11-04 측정).
    control_type 외 조건이 있으면 원래대로. 입력이 있었거나 WALK_FRESH_SEC 이 지나면 새로 읽는다."""
    if set(kwargs) - {"control_type"}:
        return _orig_desc(self, **kwargs)
    try:
        rid = tuple(self._element.GetRuntimeId())
    except (COMError, ValueError, TypeError):
        return _orig_desc(self, **kwargs)
    ct = kwargs.get("control_type")
    now = time.monotonic()

    def fresh(key):
        hit = _walks.get(key)
        return hit[2] if hit and hit[0] == _gen[0] and now - hit[1] < WALK_FRESH_SEC else None

    if ct:
        got = fresh((rid, ct))
        if got is not None:
            return list(got)
        full = fresh((rid, None))
        if full is not None and all(getattr(e, "_pf", None) for e in full):  # 방금 전체를 읽었으면 그 안에서 종류만 거른다
            want = IUIA().known_control_types[ct]
            got = [e for e in full if e._pf["ct"] == want]
            _walks[(rid, ct)] = (_gen[0], now, got)
            return list(got)
    else:
        got = fresh((rid, None))
        if got is not None:
            return list(got)
    got = _orig_desc(self, **kwargs)
    if len(_walks) > 200:
        _walks.clear()
    _walks[(rid, ct)] = (_gen[0], now, got)
    return list(got)


def _ct(self):
    pf = getattr(self, "_pf", None)
    if pf is None:
        return _orig_ct(self)
    return IUIA().known_control_type_ids[pf["ct"]]  # 모르는 종류면 원래처럼 KeyError (호출부가 다시 읽음)


def _h(self):
    pf = getattr(self, "_pf", None)
    return _orig_h(self) if pf is None else (pf["h"] or None)


def _cls(self):
    pf = getattr(self, "_pf", None)
    return _orig_cls(self) if pf is None else (pf["cls"] or "")


def _name(self):
    if _fresh(self):
        return self._pf["name"] or ""
    return _orig_name(self)


def _rect(self):
    if _fresh(self):
        r = RECT()
        r.left, r.top, r.right, r.bottom = self._pf["rect"]
        return r
    return _orig_rect.fget(self)


def _wrap_input(mod, name):
    f = getattr(mod, name, None)
    if f is None or getattr(f, "_uiafast", False):
        return

    def g(*a, **k):
        invalidate()
        try:
            return f(*a, **k)
        finally:
            invalidate()
    g._uiafast = True
    setattr(mod, name, g)


def install():
    if os.environ.get("SMOKE_UIA_CACHE", "1") == "0":
        return False
    from pywinauto import keyboard, mouse
    for n in ("click", "double_click", "right_click", "press", "release", "scroll", "move"):
        _wrap_input(mouse, n)
    _wrap_input(keyboard, "send_keys")
    c = uei.UIAElementInfo
    c._get_elements = _get_elements
    c.descendants = _descendants
    c._get_current_control_type = _ct
    c._get_current_handle = _h
    c._get_current_class_name = _cls
    c._get_current_name = _name
    c.rectangle = property(_rect)
    return True
