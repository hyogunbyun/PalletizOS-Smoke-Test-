"""PalletizOS 화면의 UIA 트리를 텍스트로 덤프한다 (요소 이름 조사용)."""
import ctypes, sys, time
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from pywinauto import Desktop

sys.stdout.reconfigure(encoding="utf-8")
win = Desktop(backend="uia").window(title="Dr.Dart-Platform")
win.descendants(); time.sleep(1.5)
w = win.wrapper_object()
print("WINDOW", w.rectangle())


def val(e):
    out = []
    try:
        v = e.iface_value.CurrentValue
        if v: out.append(f"value={v!r}")
    except Exception: pass
    try: out.append(f"toggle={e.iface_toggle.CurrentToggleState}")
    except Exception: pass
    try:
        if not e.is_enabled(): out.append("DISABLED")
    except Exception: pass
    return " ".join(out)


def walk(e, d=0):
    for c in e.children():
        ei = c.element_info
        r = ei.rectangle
        off = c.element_info.element.CurrentIsOffscreen
        if r.width() > 0 and not off:
            name = (ei.name or "").replace("\n", " ")[:70]
            print(f"{'  '*d}[{ei.control_type}] '{name}' ({r.left},{r.top},{r.width()}x{r.height()}) {val(c)}")
        walk(c, d + 1)

walk(w)
