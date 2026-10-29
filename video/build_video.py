"""설명 영상: '실행 상태 표시창(오른쪽 위)' 사용법. assets/의 실제 캡처로 장면을 그려 H.264 MP4로 인코딩한다.

python video/build_video.py  → video/PalletizOS_상태표시창_설명.mp4 + video/contact_sheet.png
인코딩: imageio-ffmpeg 번들 ffmpeg에 raw RGB 파이프, libx264 CRF19 (cv2 VideoWriter는 쓰지 않음)
"""
import math
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
A = HERE / "assets"
SHOTS = Path(r"C:\Users\HYOGUN~1.BYU\AppData\Local\Temp\claude\d--hyogun-byun-Desktop-log\68b1dce6-b79f-4b5f-ad52-c7454ea88a25\scratchpad")
OUT = HERE / "PalletizOS_상태표시창_설명.mp4"
W, H, FPS = 1920, 1080, 30

BG = (15, 20, 32)
PANEL = (27, 33, 46)
INK = (243, 244, 246)
SUB = (154, 163, 178)
ACC = (124, 196, 255)
BLUE, GREEN, RED, AMBER, GRAY, STOPC = (47, 111, 214), (31, 157, 85), (214, 69, 69), (216, 150, 20), (107, 114, 128), (180, 83, 9)
HL = (255, 196, 0)

F = r"C:\Windows\Fonts\NotoSansKR-{}.otf"


def font(size, w="Regular"):
    return ImageFont.truetype(F.format(w), size)


def sym(size):
    """✔ ✥ 같은 기호는 Noto Sans KR에 없어 네모로 나옴 → Windows 기호 글꼴"""
    return ImageFont.truetype(r"C:\Windows\Fonts\seguisym.ttf", size)


# ---------------------------------------------------------------- 표시창 요소 위치 (ov_*.png 550×536 기준, 실측)
OV = {
    1: ("배지", (14, 14, 132, 78)),
    2: ("진행 표시", (136, 18, 350, 44)),
    3: ("현재 항목", (136, 46, 340, 80)),
    4: ("항목 설명", (16, 92, 490, 142)),
    5: ("▶ 지금 확인하는 내용", (16, 150, 250, 180)),
    6: ("방금 보낸 동작", (16, 180, 140, 206)),
    7: ("직전 결과", (16, 210, 536, 238)),
    8: ("결과 칩·범례", (14, 246, 536, 476)),
    9: ("아래 상태줄", (16, 484, 350, 520)),
    10: ("■ 자동화 종료", (402, 12, 536, 56)),
    11: ("＋ 추가", (452, 484, 536, 522)),
    12: ("드래그 이동", (0, 0, 550, 536)),
}


def ov(name):
    return Image.open(A / f"ov_{name}.png").convert("RGB")


# ---------------------------------------------------------------- 그리기 도구
def wrap(d, text, f, width):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if d.textlength(cur + ch, font=f) > width and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def text(d, xy, s, f, fill=INK, width=None, gap=1.35):
    x, y = xy
    lines = wrap(d, s, f, width) if width else s.split("\n")
    for ln in lines:
        d.text((x, y), ln, font=f, fill=fill)
        y += int(f.size * gap)
    return y


def rrect(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def canvas():
    return Image.new("RGB", (W, H), BG)


def header(d, kicker, title):
    d.text((90, 64), kicker, font=font(26, "Medium"), fill=ACC)
    d.text((90, 104), title, font=font(52, "Bold"), fill=INK)


def paste_scaled(img, src, box_w, xy, shadow=True):
    s = box_w / src.width
    sc = src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS)
    if shadow:
        sh = Image.new("RGBA", (sc.width + 60, sc.height + 60), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((30, 34, sc.width + 30, sc.height + 34), 14, fill=(0, 0, 0, 150))
        sh = sh.filter(ImageFilter.GaussianBlur(14))
        img.paste(sh, (xy[0] - 30, xy[1] - 30), sh)
    img.paste(sc, xy)
    return s


def badge_num(d, n, cx, cy, r=22, fill=HL):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    f = font(int(r * 1.15), "Bold")
    t = str(n)
    d.text((cx - d.textlength(t, font=f) / 2, cy - r * 0.78), t, font=f, fill=(20, 20, 20))


def mapbox(box, s, xy, pad=4):
    x0, y0, x1, y1 = box
    return (xy[0] + x0 * s - pad, xy[1] + y0 * s - pad, xy[0] + x1 * s + pad, xy[1] + y1 * s + pad)


def bullets(d, x, y, items, width=760, size=30):
    f, fb = font(size), font(size, "Bold")
    for it in items:
        if isinstance(it, tuple):
            head, body = it
            d.text((x, y), "•", font=fb, fill=ACC)
            d.text((x + 30, y), head, font=fb, fill=INK)
            y += int(size * 1.4)
            y = text(d, (x + 30, y), body, f, SUB, width - 30) + 14
        else:
            d.text((x, y), "•", font=fb, fill=ACC)
            y = text(d, (x + 30, y), it, f, INK, width - 30) + 12
    return y


# ---------------------------------------------------------------- 장면 (각각: 고정 이미지 + 강조 상자 목록 + 길이)
SCENES = []


def scene(sec, hl=None):
    def deco(fn):
        SCENES.append((fn, sec, hl or []))
        return fn
    return deco


@scene(5)
def s_title():
    img = canvas()
    d = ImageDraw.Draw(img)
    d.text((140, 340), "PalletizOS 스모크 자동화", font=font(40, "Medium"), fill=ACC)
    d.text((140, 400), "실행 상태 표시창 사용법", font=font(96, "Bold"), fill=INK)
    d.text((140, 540), "실행하면 앱 창 오른쪽 위에 뜨는 표시창의 각 부분과 버튼을 설명합니다", font=font(34), fill=SUB)
    o = ov("s3_running")
    paste_scaled(img, o, 520, (1260, 280))
    return img, []


@scene(9)
def s_where():
    img = canvas()
    d = ImageDraw.Draw(img)
    app = Image.open(SHOTS / "bg_ready.png").convert("RGB")
    s = paste_scaled(img, app, 1500, (90, 120))
    o = ov("s3_running")
    ow = 360
    ox, oy = 90 + int(1500) - ow - 30, 120 + 70
    paste_scaled(img, o, ow, (ox, oy), shadow=True)
    d.text((90, 40), "어디에 뜨나요?", font=font(44, "Bold"), fill=INK)
    y = 120 + int(app.height * s) + 26
    text(d, (90, y), "실행을 시작하면 Dr.Dart-Platform 앱 창의 오른쪽 위에 자동으로 뜹니다. 앱 창이 움직이면 따라가고, "
                     "앱 버튼을 가리더라도 자동화는 마우스를 쓰지 않으므로 방해하지 않습니다.", font(30), SUB, 1700)
    return img, [(ox - 8, oy - 8, ox + ow + 8, oy + int(o.height * ow / o.width) + 8)]


@scene(13)
def s_overview():
    img = canvas()
    d = ImageDraw.Draw(img)
    header(d, "구성 한눈에", "표시창의 12가지 요소")
    o = ov("s3_running")
    xy = (150, 250)
    s = paste_scaled(img, o, 760, xy)
    right_edge = xy[0] + int(o.width * s)
    for n, (name, box) in OV.items():
        if n == 12:
            continue
        b = mapbox(box, s, xy, 2)
        d.rounded_rectangle(b, 6, outline=HL, width=3)
        cy = int((b[1] + b[3]) / 2)
        if n == 1:          # 배지는 ②③과 높이가 겹쳐 위쪽에 번호
            cx = int((b[0] + b[2]) / 2)
            d.line((cx, xy[1] - 18, cx, b[1]), fill=HL, width=2)
            badge_num(d, n, cx, xy[1] - 38, 19)
        elif n in (10, 11):   # 오른쪽 버튼은 표시창 오른쪽 바깥에 번호
            d.line((b[2], cy, right_edge + 22, cy), fill=HL, width=2)
            badge_num(d, n, right_edge + 44, cy, 19)
        else:               # 나머지는 왼쪽 바깥에 번호
            d.line((xy[0] - 22, cy, b[0], cy), fill=HL, width=2)
            badge_num(d, n, xy[0] - 44, cy, 19)
    x, y = 1090, 250
    f, fb = font(31), font(31, "Bold")
    for n, (name, _) in OV.items():
        badge_num(d, n, x + 20, y + 22, 20)
        d.text((x + 56, y), name, font=fb, fill=INK)
        y += 62
    return img, []


def detail(num, title, src, crop_key, items, extra=None, crop_pad=30, zoom_w=820):
    img = canvas()
    d = ImageDraw.Draw(img)
    header(d, f"{num}", title)
    o = ov(src)
    # 왼쪽 위: 전체 표시창 축소 + 위치 강조
    s = paste_scaled(img, o, 380, (90, 210))
    hl = []
    for k in (crop_key if isinstance(crop_key, (list, tuple)) else [crop_key]):
        hl.append(mapbox(OV[k][1], s, (90, 210), 3))
    # 왼쪽 아래: 확대
    boxes = [OV[k][1] for k in (crop_key if isinstance(crop_key, (list, tuple)) else [crop_key])]
    x0 = max(0, min(b[0] for b in boxes) - crop_pad)
    y0 = max(0, min(b[1] for b in boxes) - crop_pad)
    x1 = min(o.width, max(b[2] for b in boxes) + crop_pad)
    y1 = min(o.height, max(b[3] for b in boxes) + crop_pad)
    crop = o.crop((x0, y0, x1, y1))
    zw = min(zoom_w, int(crop.width * 2.6))
    zh = int(crop.height * zw / crop.width)
    if zh > 420:
        zw = int(zw * 420 / zh)
    if extra is None:
        paste_scaled(img, crop, zw, (90, 210 + int(o.height * s) + 40))
    else:
        extra(img, d, (90, 210 + int(o.height * s) + 40))
    bullets(d, 1000, 220, items, width=830)
    return img, hl


@scene(10)
def s_badge():
    def strip(img, d, xy):
        x, y = 520, 210
        for st, lab, desc in (("s1_prepare", "ING", "진행 중"), ("s2_wait", "WAIT", "입력 대기"),
                              ("s6_pass", "PASS", "전체 통과"), ("s7_fail", "FAIL", "보류/재실행"),
                              ("s5_stop", "STOP", "사용자 종료")):
            o = ov(st)
            col, x1 = o.getpixel((24, 21)), 24  # 글자가 없는 배지 윗부분 줄에서 색 영역 끝 찾기
            while x1 < 300 and sum(abs(a - b) for a, b in zip(o.getpixel((x1, 21)), col)) < 40:
                x1 += 1
            c = o.crop((14, 14, x1 + 4, 78))
            paste_scaled(img, c, 170, (x, y), shadow=False)
            d.text((x + 190, y + 12), desc, font=font(28, "Medium"), fill=INK)
            y += 112
    img, hl = detail("①  배지", "지금 상태를 한 단어로", "s3_running", 1, [
        ("ING (파랑)", "실행 중에는 항상 ING. 항목 하나가 끝나도 바뀌지 않습니다."),
        ("WAIT (회색)", "Admin 비밀번호 입력을 기다리는 중 (저장된 비밀번호가 없을 때만)."),
        ("PASS (초록) / FAIL (빨강)", "모두 끝난 뒤 전체 판정. FAIL = 보류 또는 재실행 필요."),
        ("STOP (주황)", "'자동화 종료'를 눌러 멈춘 상태. 원래 값으로 되돌린 뒤 끝납니다."),
    ], extra=lambda *a: None)
    d = ImageDraw.Draw(img)
    strip(img, d, None)
    return img, hl


@scene(9)
def s_progress():
    return detail("②③  진행 표시 · 현재 항목", "몇 번째 항목을 하고 있나", "s3_running", [2, 3], [
        ("PalletizOS 스모크 · 11/31", "전체 31개(기본 30 + 녹화 C01) 중 11번째를 실행 중. 환경 준비·종료 때는 숫자가 없습니다."),
        ("R03 · 레시피 검색", "지금 평가 중인 항목의 번호와 이름. H=Home, R=Recipes, I=IO, L=Log, S=Settings, J/Q/V=Jog+/Quick Log/Recovery, C=녹화 시나리오."),
    ], crop_pad=6)


@scene(10)
def s_step():
    return detail("④⑤⑥  설명 · 확인 내용 · 동작", "무엇을, 어떻게 확인하나", "s3_running", [4, 5, 6], [
        ("④ 항목 설명 (회색)", "이 항목 전체가 확인하는 내용과 PASS 기준."),
        ("⑤ ▶ 지금 확인하는 내용 (하늘색)", "바로 이 순간의 단계와 기대값. 예: '1006' 검색 → 2개 기대."),
        ("⑥ 클릭: … (작은 회색)", "자동화가 방금 누른 버튼이나 입력한 값. 마우스는 움직이지 않고 버튼에 직접 명령을 보냅니다."),
    ])


@scene(10)
def s_last():
    def two(img, d, xy):
        x, y = xy
        for st, lab in (("s3_running", "통과한 경우"), ("s3b_fail", "실패한 경우 — 이유까지 표시")):
            c = ov(st).crop((0, 200, 550, 246))
            d.text((x, y), lab, font=font(26, "Medium"), fill=SUB)
            paste_scaled(img, c, 820, (x, y + 40), shadow=False)
            y += 40 + int(46 * 820 / 550) + 30
    return detail("⑦  직전 결과", "방금 끝난 항목의 결과", "s3b_fail", 7, [
        ("직전: 항목 → PASS / FAIL", "항목이 끝날 때마다 이 줄만 바뀝니다. 큰 배지는 계속 ING."),
        ("FAIL이면 이유 함께", "예: '메뉴 항목 누락'. 자동으로 한 번 더 시도하고, 그래도 실패하면 FAIL로 확정됩니다."),
        ("PASS (불안정)", "1차 실패 후 재시도에서 통과한 경우. 자주 나오면 elements.yaml의 speed를 낮추세요."),
    ], extra=two)


@scene(11)
def s_chips():
    return detail("⑧  결과 칩 · 범례", "전체 항목의 진행 현황", "s3b_fail", 8, [
        ("한 칸 = 한 항목", "번호 + 짧은 이름. 5개씩 줄을 지어 실행 순서대로 놓입니다."),
        ("색 = 결과", "초록 통과 · 빨강 실패 · 노랑 주의(새 로그 에러/불안정) · 흰색 지금 실행 중 · 어두운 회색 대기 또는 해당없음."),
        ("해당없음 예", "H06 3D확대는 큰 모니터(2D 화면)에서는 컨트롤이 없어 회색으로 남습니다."),
    ], zoom_w=820, crop_pad=4)


@scene(9)
def s_foot():
    def two(img, d, xy):
        x, y = xy
        for st, lab in (("s3_running", "평소"), ("s4_record", "시나리오 녹화 중 (자동화 일시정지)")):
            o = ov(st)
            c = o.crop((0, o.height - 60, 550, o.height))
            d.text((x, y), lab, font=font(26, "Medium"), fill=SUB)
            paste_scaled(img, c, 820, (x, y + 40), shadow=False)
            y += 40 + int(60 * 820 / 550) + 30
    return detail("⑨  아래 상태줄", "지금 지켜야 할 것", "s4_record", 9, [
        ("백그라운드 실행 중", "다른 프로그램은 써도 됩니다. 단, 앱 창을 최소화하거나 닫지 마세요 (닫으면 앱을 다시 띄우느라 1~2분 지연)."),
        ("● 시나리오 녹화 중 (빨강)", "녹화 창이 녹화하는 동안 자동화가 멈춰 기다립니다. 녹화를 끝내면 이어서 진행."),
        ("자동화 종료 · 20초 뒤 사라짐", "모두 끝난 뒤. 리포트가 브라우저로 열립니다."),
    ], extra=two)


@scene(10)
def s_stop():
    def flow(img, d, xy):
        x, y = xy
        a = ov("s3_running").crop(OV[10][1])
        b = ov("s5_stop").crop((0, 0, 370, 90))
        paste_scaled(img, a, 260, (x, y + 20), shadow=False)
        d.text((x + 290, y + 30), "3초 안에 두 번", font=font(28, "Bold"), fill=HL)
        d.text((x + 290, y + 74), "→", font=font(40, "Bold"), fill=INK)
        paste_scaled(img, b, 420, (x + 300, y + 130), shadow=False)
    return detail("⑩  ■ 자동화 종료", "실행을 안전하게 멈추기", "s3_running", 10, [
        ("두 번 눌러야 종료", "한 번 누르면 '한 번 더 = 종료'로 바뀌고, 3초 안에 다시 누르면 멈춥니다 (실수 방지)."),
        ("멈춘 뒤 원상복구", "진행 중이던 항목을 멈추고 토글·레시피·층/박스·Enable·계정을 시작 전 상태로 되돌립니다. 배지는 STOP."),
        ("리포트는 '중단'", "실행하지 못한 항목은 '실행되지 않음'으로 남습니다. 결함으로 세지 않습니다."),
    ], extra=flow)


@scene(12)
def s_add():
    img = canvas()
    d = ImageDraw.Draw(img)
    header(d, "⑪  ＋ 추가", "시나리오 녹화 → 관리")
    o = ov("s3_running")
    s = paste_scaled(img, o, 330, (90, 210))
    hl = [mapbox(OV[11][1], s, (90, 210), 3)]
    rec = Image.open(A / "win_recorder.png").convert("RGB")
    mgr = Image.open(A / "win_manager.png").convert("RGB")
    paste_scaled(img, rec, 520, (480, 210))
    paste_scaled(img, mgr, 720, (1110, 210))
    d.text((480, 170), "녹화 창 (예: C01 '111' 녹화 중)", font=font(24, "Medium"), fill=SUB)
    d.text((1110, 170), "시나리오 관리 창", font=font(24, "Medium"), fill=SUB)
    y = 210 + int(mgr.height * 720 / mgr.width) + 50
    y = max(y, 210 + int(rec.height * 520 / rec.width) + 50)
    bullets(d, 90, y, [
        ("녹화", "이름 → ● 녹화 시작 → 앱에서 직접 누름(누른 버튼 이름이 목록에 쌓임) → 완료 → '끝났을 때 보여야 할 문구' 선택 → 저장. 다음 실행부터 C01, C02…로 포함."),
        ("관리", "이름·실행 포함 여부·단계 순서/삭제·입력값·확인 문구 편집, 삭제(휴지통), '▶ 이 시나리오만 실행'으로 바로 확인."),
    ], width=1740, size=28)
    return img, hl


@scene(9)
def s_drag():
    img, hl = detail("⑫  드래그 이동 · 투명도", "보기 편한 곳으로", "s3_running", 12, [
        ("끌어서 옮기기", "버튼이 아닌 빈 곳·글자를 누른 채 끌면 옮겨집니다. 위치는 앱 창 기준으로 기억되어, 앱 창이 움직여도 따라가고 다음 실행에도 유지됩니다."),
        ("투명도", "elements.yaml의 overlay_alpha (0.3~1.0, 기본 0.72). 낮을수록 투명합니다."),
        ("실제 마우스 방식(--mode mouse)", "이때는 클릭이 표시창을 통과해야 하므로 버튼·드래그가 없습니다."),
    ], extra=lambda img, d, xy: (d.text((xy[0], xy[1] + 6), "✥", font=sym(40), fill=HL),
                                 d.text((xy[0] + 56, xy[1] + 10), "표시창 아무 곳(버튼 제외)을 잡고 끌기", font=font(32, "Bold"), fill=HL)))
    return img, hl


@scene(15)
def s_timeline():
    img = canvas()
    d = ImageDraw.Draw(img)
    header(d, "실행 흐름", "단계마다 표시창은 이렇게 바뀝니다")
    steps = [("s1_prepare", "1. 환경 준비", "앱 실행·제어기 연결·로그인"), ("s2_wait", "2. 비밀번호 대기", "저장분 없을 때만"),
             ("s3_running", "3. 평가 중", "항목별 진행"), ("s4_record", "4. 녹화 중", "자동화 일시정지"),
             ("s6_pass", "5. 끝 (PASS)", "리포트 열림")]
    x = 70
    for i, (st, lab, sub) in enumerate(steps):
        o = ov(st)
        paste_scaled(img, o, 330, (x, 300))
        d.text((x, 220), lab, font=font(30, "Bold"), fill=INK)
        d.text((x, 262), sub, font=font(22), fill=SUB)
        if i < len(steps) - 1:
            d.text((x + 338, 520), "›", font=font(60, "Bold"), fill=ACC)
        x += 362
    text(d, (90, 940), "끝나면 배지가 PASS/FAIL로 바뀌고 20초 뒤 사라집니다. 실패 단계·이유·스크린샷은 자동으로 열리는 리포트에서 확인하세요.",
         font(28), SUB, 1760)
    return img, []


@scene(7)
def s_end():
    img = canvas()
    d = ImageDraw.Draw(img)
    d.text((140, 330), "정리", font=font(40, "Medium"), fill=ACC)
    y = 400
    for ln in ("배지는 전체 상태, '직전' 줄은 방금 끝난 항목, 칩은 전체 진행",
               "멈출 때는 ■ 자동화 종료 두 번 — 원래 상태로 되돌린 뒤 끝남",
               "＋ 추가로 시나리오 녹화, 관리 창에서 편집·삭제·바로 실행",
               "실행 중엔 다른 업무 가능 · 앱 창만 최소화하거나 닫지 않기"):
        d.text((140, y + 2), "✔", font=sym(38), fill=GREEN)
        d.text((200, y), ln, font=font(38, "Medium"), fill=INK)
        y += 78
    d.text((140, 800), "자세한 내용: dart_autotest\\MANUAL.md", font=font(30), fill=SUB)
    return img, []


# ---------------------------------------------------------------- 렌더링
def render():
    built = []
    for fn, sec, _ in SCENES:
        img, hl = fn()
        built.append((img, hl, sec))
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)], stdin=subprocess.PIPE)
    sheet = []
    (HERE / "frames").mkdir(exist_ok=True)
    black = Image.new("RGB", (W, H), BG)
    fade = int(0.45 * FPS)
    for si, (img, hl, sec) in enumerate(built):
        n = int(sec * FPS)
        for i in range(n):
            t = i / FPS
            fr = img
            if hl:
                fr = img.copy()
                d = ImageDraw.Draw(fr)
                pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 1.4)
                wdt = 3 + int(3 * pulse)
                for b in hl:
                    d.rounded_rectangle(b, 8, outline=HL, width=wdt)
            if i < fade:
                fr = Image.blend(black, fr, i / fade)
            elif i > n - fade:
                fr = Image.blend(black, fr, max(0.0, (n - i) / fade))
            proc.stdin.write(fr.tobytes())
            if i == n // 2:
                sheet.append(fr.resize((480, 270)))
                fr.save(HERE / "frames" / f"scene_{si:02d}.png")
    proc.stdin.close()
    proc.wait()
    cols = 4
    rows = math.ceil(len(sheet) / cols)
    cs = Image.new("RGB", (cols * 480, rows * 270), (0, 0, 0))
    for i, s in enumerate(sheet):
        cs.paste(s, ((i % cols) * 480, (i // cols) * 270))
    cs.save(HERE / "contact_sheet.png")
    total = sum(s for _, _, s in built)
    print(f"done: {OUT} ({total}s, {OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    render()
