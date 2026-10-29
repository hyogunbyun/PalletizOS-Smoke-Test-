"""실행 중 화면 캡처 (오버레이 확인용): 앱 창이 있는 모니터 전체를 지정 시각마다 저장."""
import sys, time, ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from PIL import ImageGrab
out, times = sys.argv[1], [float(t) for t in sys.argv[2:]]
t0 = time.time()
for i, t in enumerate(times):
    time.sleep(max(0, t - (time.time() - t0)))
    im = ImageGrab.grab(all_screens=True)
    im.crop((0, 0, 3840, 2160)).resize((1920, 1080)).save(f"{out}_{i}.png")  # 가상 화면 왼쪽 = 4K 모니터
