"""버튼을 하나씩 눌러 전후 화면 문구 차이를 기록하는 조사 도구."""
import sys, json, time
sys.stdout.reconfigure(encoding="utf-8"); sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from autotest.ui import UI, _toggle
SHOT = r"C:\Users\HYOGUN~1.BYU\AppData\Local\Temp\claude\d--hyogun-byun-Desktop-log\68b1dce6-b79f-4b5f-ad52-c7454ea88a25\scratchpad"
ui = UI(); ui.warm_up(); ui.ensure_maximized()

def act(label, fn, settle=1.5):
    before = ui.visible_texts()
    fn(); time.sleep(settle)
    after = ui.visible_texts()
    print(f"== {label}\n   + {sorted(after-before)}\n   - {sorted(before-after)}")

def shot(name):
    im = ui.wrapper().capture_as_image(); im.thumbnail((1600, 900)); im.save(f"{SHOT}/{name}.png")

steps = sys.argv[1]
if steps == "counters":
    s = ui.sides()["Right"]
    act("Right layer minus (1/1)", lambda: ui.click(s.layer["minus"]))
    s = ui.sides()["Right"]; print("   layer now", s.layer["value"], s.layer["max"], "minus", s.layer["minus"].is_enabled(), "plus", s.layer["plus"].is_enabled())
    shot("p_layer_minus")
    if s.layer["plus"].is_enabled():
        act("Right layer plus", lambda: ui.click(s.layer["plus"]))
        s = ui.sides()["Right"]; print("   layer now", s.layer["value"], s.layer["max"])
    s = ui.sides()["Right"]
    act("Right boxes minus (20/20)", lambda: ui.click(s.boxes["minus"]))
    s = ui.sides()["Right"]; print("   boxes now", s.boxes["value"], s.boxes["max"], "minus", s.boxes["minus"].is_enabled(), "plus", s.boxes["plus"].is_enabled())
    if s.boxes["plus"].is_enabled():
        act("Right boxes plus", lambda: ui.click(s.boxes["plus"]))
        s = ui.sides()["Right"]; print("   boxes now", s.boxes["value"], s.boxes["max"])
elif steps == "toggle":
    s = ui.sides()["Left"]
    act("Left toggle ON", lambda: ui.click(s.toggle), settle=2.5)
    shot("p_left_on")
    print(json.dumps(ui.snapshot()["Left"], ensure_ascii=False))
