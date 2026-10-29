"""메뉴 조사: nav:<메뉴> / click:<이름> / tab:<이름> / back(Home) / dump:<파일명>
dump는 PalletizOS 영역 + 그 위에 뜬 층(대화상자·패널)의 보이는 요소와 스크린샷을 남긴다."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from pywinauto import keyboard
from autotest.ui import UI, _layer_ok
SHOT = r"C:\Users\HYOGUN~1.BYU\AppData\Local\Temp\claude\d--hyogun-byun-Desktop-log\68b1dce6-b79f-4b5f-ad52-c7454ea88a25\scratchpad"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menus")
os.makedirs(OUT, exist_ok=True)
ui = UI(); ui.warm_up()

def visible():
    """뒤에 깔린 Platform 층을 뺀 보이는 요소."""
    out = []
    for e in ui.wrapper().descendants():
        ei = e.element_info
        r = ei.rectangle
        if r.width() <= 0 or ei.control_type in ("Pane", "Group", "Image", "Document"):
            continue
        if _layer_ok(e) is not True:
            continue
        try: en = e.is_enabled()
        except Exception: en = None
        val = ""
        try: val = e.iface_value.CurrentValue
        except Exception: pass
        out.append((ei.control_type, (ei.name or "").replace("\n", " ")[:70], r.left, r.top, r.width(), r.height(), en, val))
    return out

def find(name):
    for e in ui.wrapper().descendants():
        if (e.window_text() or "").strip() == name and e.element_info.rectangle.width() > 0 and _layer_ok(e) is True:
            if e.element_info.control_type in ("Button", "TabItem", "ListItem", "MenuItem", "Hyperlink", "CheckBox", "RadioButton", "Text", "DataItem"):
                return e
    raise SystemExit(f"요소 없음: {name}")

for cmd in sys.argv[1:]:
    kind, _, arg = cmd.partition(":")
    if kind in ("nav", "click", "tab"):
        ui.click(find(arg), settle=2.5)
    elif kind == "back":
        ui.click(find("Home"), settle=2.5)
    elif kind == "key":
        keyboard.send_keys(arg); time.sleep(1.5)
    elif kind == "dump":
        items = visible()
        with open(os.path.join(OUT, f"{arg}.txt"), "w", encoding="utf-8") as f:
            for t in items:
                f.write(f"[{t[0]}] {t[1]!r} ({t[2]},{t[3]},{t[4]}x{t[5]}) en={t[6]} {('val=' + repr(t[7])) if t[7] else ''}\n")
        im = ui.wrapper().capture_as_image(); im.thumbnail((1600, 900)); im.save(f"{SHOT}/m_{arg}.png")
        print(f"dump {arg}: {len(items)} elements")
