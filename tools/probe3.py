"""범용 조사: toggle:Left / name:Release Vacuum / recipe:Right / key:{ESC} / shot:파일명 / snap"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from pywinauto import keyboard
from autotest.ui import UI
SHOT = r"C:\Users\HYOGUN~1.BYU\AppData\Local\Temp\claude\d--hyogun-byun-Desktop-log\68b1dce6-b79f-4b5f-ad52-c7454ea88a25\scratchpad"
ui = UI(); ui.warm_up(); ui.ensure_maximized()

def allnames():
    out = set()
    for e in ui.win.descendants():
        ei = e.element_info
        if ei.name and ei.rectangle.width() > 0 and ei.control_type in ("Text", "Button", "ListItem", "MenuItem", "Edit", "CheckBox", "RadioButton"):
            out.add(f"{ei.control_type}:{ei.name.strip()[:60]}")
    return out

for cmd in sys.argv[1:]:
    kind, _, arg = cmd.partition(":")
    before = allnames()
    if kind == "toggle":
        ui.click(ui.sides()[arg].toggle, settle=2)
    elif kind == "name":
        b = ui.by_name(arg) or ui.by_name(arg, root=ui.win.wrapper_object())
        ui.click(b, settle=2.5)
    elif kind == "recipe":
        ui.click(ui.sides()[arg].recipe, settle=2)
    elif kind == "key":
        keyboard.send_keys(arg); time.sleep(1.5)
    elif kind == "shot":
        im = ui.wrapper().capture_as_image(); im.thumbnail((1600, 900)); im.save(f"{SHOT}/{arg}.png"); continue
    elif kind == "snap":
        print(json.dumps(ui.snapshot(), ensure_ascii=False)); continue
    after = allnames()
    print(f"== {cmd}\n   + {sorted(after - before)}\n   - {sorted(before - after)}")
