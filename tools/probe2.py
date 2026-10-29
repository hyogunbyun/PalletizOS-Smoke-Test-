import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from autotest.ui import UI
ui = UI(); ui.warm_up(); ui.ensure_maximized()

def st(tag):
    s = ui.sides()["Right"]
    L, B = s.layer, s.boxes
    print(f"{tag}: prog={s.progress} layer={L['value']}/{L['max']} [-]{L['minus'].is_enabled():d}[+]{L['plus'].is_enabled():d}"
          f"  boxes={B['value']}/{B['max']} [-]{B['minus'].is_enabled():d}[+]{B['plus'].is_enabled():d}")
    return s

for step in sys.argv[1:]:
    side, key, btn = step.split(".")   # 예: Right.layer.plus
    s = ui.sides()[side]
    ui.click(getattr(s, key)[btn], settle=1.5)
    st(f"after {step}")
if len(sys.argv) == 1:
    st("now")
