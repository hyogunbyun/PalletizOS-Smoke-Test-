"""오버레이 미리보기: 가짜 상태로 오버레이만 띄우고 앱 창 우측 상단을 캡처 (마우스 조작 없음)."""
import ctypes, json, os, subprocess, sys, time
from pathlib import Path
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from PIL import ImageGrab
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "autotest"))
from winutil import app_rect
st = ROOT / "results" / "preview_status.json"
st.write_text(json.dumps({"badge": "ING", "index": 4, "total": 9, "flow": "P04 · Current Layer +/−",
    "desc": "층 [+]는 다음 층 경계로, [−]는 이전 경계로. 끝에서 버튼 비활성. 진행률 일치",
    "step": "층 [+] → 완료 박스 N 20→40, 진행률 50% 기대", "action": "클릭: Right 층 [+]",
    "chip_labels": {"P01": "P01 진입", "P02": "P02 토글", "P03": "P03 레시피", "P04": "P04 층±", "P05": "P05 박스±",
                    "P06": "P06 속도", "P07": "P07 Enable", "P09": "P09 진공·홈", "P10": "P10 메뉴"},
    "chips": [["P01","pass"],["P02","pass"],["P03","fail"],["P04","run"],["P05",None],["P06",None],["P07",None],["P09",None],["P10",None]]},
    ensure_ascii=False), encoding="utf-8")
p = subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"), str(ROOT / "autotest" / "overlay.py"), str(st), str(os.getpid())])
time.sleep(3)
r = app_rect()
if r is None:  # 앱 창이 없으면 오버레이는 주 모니터 우측 상단에 뜬다
    sw, sh = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
    box = (sw // 2, 0, sw, sh // 2)
else:
    w, h = r.right - r.left, r.bottom - r.top
    box = (r.right - w // 2, r.top, r.right, r.top + h // 2)
ImageGrab.grab(bbox=box, all_screens=True).save(sys.argv[1])
p.kill(); st.unlink()
print("capture box:", box)
