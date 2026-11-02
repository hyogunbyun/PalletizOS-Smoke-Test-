"""개발용 화면 조사: python tc_autotest/dev/xp.py <스크립트.py>
스크립트 안에서 ui, find(name, ctype=None), btns(), dump(tag), click(elem_or_name) 사용."""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")
from autotest.ui import UI, _layer_ok  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps")
os.makedirs(OUT, exist_ok=True)
ui = UI()
ui.warm_up()


def visible():
    out = []
    for e in ui.wrapper().descendants():
        ei = e.element_info
        r = ei.rectangle
        if r.width() <= 0 or ei.control_type in ("Pane", "Group", "Image", "Document"):
            continue
        if _layer_ok(e) is not True:
            continue
        try:
            en = e.is_enabled()
        except Exception:
            en = None
        val = ""
        try:
            val = e.iface_value.CurrentValue
        except Exception:
            pass
        out.append((ei.control_type, (ei.name or "").replace("\n", " ")[:80], r.left, r.top, r.width(), r.height(), en, val))
    return out


def dump(tag, only_top=None):
    items = visible()
    if only_top is not None:
        items = [t for t in items if t[2] >= only_top]
    lines = [f"[{t[0]}] {t[1]!r} ({t[2]},{t[3]},{t[4]}x{t[5]}) en={t[6]}" + (f" val={t[7]!r}" if t[7] else "") for t in items]
    open(os.path.join(OUT, f"{tag}.txt"), "w", encoding="utf-8").write("\n".join(lines))
    print(f"--- {tag}: {len(items)}")
    print("\n".join(lines))


def find(name, ctype=None):
    for e in ui.wrapper().descendants():
        if (e.window_text() or "").strip() == name and e.element_info.rectangle.width() > 0 and _layer_ok(e) is True:
            if ctype is None or e.element_info.control_type == ctype:
                return e
    raise SystemExit(f"요소 없음: {name}")


def click(x, settle=2.0):
    ui.click(find(x) if isinstance(x, str) else x, settle=settle)


exec(open(sys.argv[1], encoding="utf-8").read())
