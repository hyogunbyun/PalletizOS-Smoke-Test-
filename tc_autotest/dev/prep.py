"""개발용: 앱을 PalletizOS Home + Admin 으로 준비 (독립 프로세스로 실행, 결과는 prep.log)."""
import os, sys, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
out = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prep.log"), "w", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = out
try:
    from autotest import env, secret
    from autotest.ui import UI
    ui = UI()
    env.ensure_ready(ui, print)
    if ui.current_role() != "Admin":
        ui.login_as("Admin", secret.load())
    print("ROLE", ui.current_role())
    print("RAIL", [r.window_text() for r in ui.rail()])
    print("DONE")
except BaseException:
    traceback.print_exc()
    print("FAILED")
