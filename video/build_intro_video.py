"""소개 영상 (자막 포함): PalletizOS 스모크 자동화 소개 자료(judgment_doc/소개.html) 카드 + 상태 표시창 캡처 + 실제 자동 설치 기록.

python video/build_intro_video.py → video/PalletizOS_스모크자동화_소개영상.mp4 (자막 + 한국어 음성, .srt, intro_contact.png)
음성: Windows 음성 합성(Microsoft Heami, 오프라인). 문장을 읽는 시간이 자막 구간보다 길면 그 구간을 늘림
재료: video/intro_assets/card1~7.png (소개.html 2배 해상도 캡처에서 카드별로 자름), video/assets/ov_s3_running.png
인코딩: imageio-ffmpeg 번들 ffmpeg에 raw RGB 파이프, libx264 CRF19
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
IA, A = HERE / "intro_assets", HERE / "assets"
OUT = HERE / "PalletizOS_스모크자동화_소개영상.mp4"
SRT = OUT.with_suffix(".srt")
W, H, FPS = 1920, 1080, 30
BG, PANEL, INK, SUB, ACC = (238, 241, 245), (255, 255, 255), (20, 36, 58), (74, 90, 112), (194, 86, 16)
NAVY, HL = (27, 58, 92), (255, 176, 0)
F = r"C:\Windows\Fonts\NotoSansKR-{}.otf"


def font(size, w="Regular"):
    return ImageFont.truetype(F.format(w), size)


def wrap(d, text, f, width):
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=f) > width and cur:
            cut = cur.rfind(" ")
            if cut > len(cur) * 0.6:
                lines.append(cur[:cut])
                cur = cur[cut + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def header(d, kicker, title):
    d.rectangle((0, 0, W, 112), fill=NAVY)
    d.text((60, 22), kicker, font=font(24, "Medium"), fill=(157, 182, 208))
    d.text((60, 50), title, font=font(44, "Bold"), fill=(255, 255, 255))


def fit(img, max_w, max_h):
    s = min(max_w / img.width, max_h / img.height)
    return img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS), s


def base(kicker, title):
    im = Image.new("RGB", (W, H), BG)
    header(ImageDraw.Draw(im), kicker, title)
    return im


def card_scene(n, kicker, title, max_w=1500, max_h=760):
    im = base(kicker, title)
    c, s = fit(Image.open(IA / f"card{n}.png").convert("RGB"), max_w, max_h)
    x, y = (W - c.width) // 2, 128 + (max_h - c.height) // 2
    shadow = Image.new("RGB", (c.width + 16, c.height + 16), (210, 216, 225))
    im.paste(shadow, (x - 4, y + 4))
    im.paste(c, (x, y))
    return im, (x, y, s)


# ---------------------------------------------------------------- 장면 정의: (길이, 바탕 그림, 강조 [(시작,끝,박스)], 자막 [(시작,끝,문장)])
def svg_box(origin, b):
    """평가 프로세스 카드(card1) 안 SVG 좌표 → 화면 좌표. card1 = 2배 캡처, SVG는 카드 안 (16, 68) css px에서 1.004배."""
    x, y, s = origin
    k = 2 * s  # css px → 화면
    return (x + (16 + b[0] * 1.004) * k, y + (68 + b[1] * 1.004) * k,
            x + (16 + (b[0] + b[2]) * 1.004) * k, y + (68 + (b[1] + b[3]) * 1.004) * k)


def scenes():
    out = []
    # 1. 제목
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    d.text((W // 2, 360), "PalletizOS", font=font(72, "Black"), fill=(255, 199, 154), anchor="mm")
    d.text((W // 2, 460), "스모크 자동화 소개", font=font(88, "Black"), fill=(255, 255, 255), anchor="mm")
    d.text((W // 2, 580), "데일리 빌드 → 자동 설치 → 무인 스모크 → 리포트", font=font(38, "Medium"), fill=(201, 214, 228), anchor="mm")
    d.text((W // 2, 660), "Dr.Dart-Platform 3.7.0 · PalletizOS v2.0.0 · 2026-10-26 · QVE", font=font(28), fill=(157, 182, 208), anchor="mm")
    out.append((7, im, [], [(0, 3.5, "PalletizOS 스모크 자동화를 소개합니다."),
                            (3.5, 7, "새 빌드가 나오면 사람 손 없이 설치하고, 기본 기능을 자동으로 확인합니다.")]))
    # 2. 평가 프로세스
    im, o = card_scene(1, "1 · PROCESS", "평가 프로세스 — 스모크 테스트 → PASS → 매뉴얼 테스트", max_w=1820, max_h=760)
    out.append((24, im, [(0, 6, svg_box(o, (10, 6, 205, 92))), (6, 11, svg_box(o, (245, 10, 260, 84))),
                         (11, 15, svg_box(o, (535, 10, 510, 84))), (15, 20, svg_box(o, (440, 170, 340, 66))), (15, 20, svg_box(o, (300, 280, 260, 62))),
                         (20, 24, svg_box(o, (870, 170, 290, 66))), (20, 24, svg_box(o, (660, 280, 290, 62)))],
                [(0, 6, "데일리 빌드가 GitHub에 릴리스되면, 감시기가 30분마다 확인해 새 버전만 내려받아 자동 설치합니다."),
                 (6, 11, "설치가 끝나면 스모크 자동 테스트 42개 항목이 무인으로 실행됩니다. 실측 약 76분입니다."),
                 (11, 15, "전체 판정이 PASS면 매뉴얼 테스트로 넘어가고, 사람은 스모크가 못 보는 영역에 집중합니다."),
                 (15, 20, "FAIL이면 메시지·스크린샷·화면 구조로 원인을 보고, 제품 결함이면 JIRA 이슈로 등록합니다."),
                 (20, 24, "환경 문제나 화면 변경이면 조치하거나 자동화를 고친 뒤 스모크를 다시 돌립니다.")]))
    # 3~5, 7, 9: 카드
    im, _ = card_scene(2, "2 · WHY", "왜 스모크 테스트부터 — 관문(Gate) 역할")
    out.append((10, im, [], [(0, 5, "스모크 테스트는 이 빌드가 매뉴얼 테스트를 시작할 만큼 기본이 살아 있는지 확인하는 관문입니다."),
                             (5, 10, "깨진 빌드에 사람 공수를 쓰지 않고, 매번 같은 기준으로 확인하고 증거를 남깁니다.")]))
    im, _ = card_scene(3, "3 · SCOPE", "무엇을 확인하나 — 42개 항목")
    out.append((11, im, [], [(0, 5.5, "확인 항목은 42개입니다. Home·Recipe·IO·Log·Settings의 핵심 기능 30개,"),
                             (5.5, 11, "메뉴의 모든 버튼을 한 번씩 눌러 보는 전체 클릭 8개, 사람이 녹화한 시나리오 4개입니다.")]))
    im, _ = card_scene(4, "4 · HOW IT WORKS", "구성과 동작 원리")
    out.append((11, im, [], [(0, 5.5, "마우스를 쓰지 않고 Windows 접근성 정보로 버튼을 찾아 누르기 때문에, 실행 중에도 PC로 다른 일을 할 수 있습니다."),
                             (5.5, 11, "실패하면 원래대로 되돌린 뒤 한 번 더 시도하고, 항목마다 바꾼 값을 시작 상태로 되돌립니다.")]))
    # 6. 실행 방법 + 상태 표시창 실제 캡처
    im = base("5 · HOW TO RUN", "실행 방법 · 실행 중 상태 표시창")
    c, _ = fit(Image.open(IA / "card5.png").convert("RGB"), 1120, 740)
    im.paste(c, (60, 140))
    ov, _ = fit(Image.open(A / "ov_s3_running.png").convert("RGB"), 620, 740)
    ox = 60 + c.width + 60
    d = ImageDraw.Draw(im)
    d.text((ox, 140), "실제 상태 표시창", font=font(26, "Bold"), fill=INK)
    im.paste(ov, (ox, 182))
    out.append((13, im, [(6.5, 13, (ox - 6, 182 + ov.height * 0.43, ox + ov.width + 6, 182 + ov.height * 0.9))],
                [(0, 6.5, "실행은 바탕화면 아이콘 하나로 시작합니다. 앱 오른쪽 위 상태 표시창에 진행 상황이 보입니다."),
                 (6.5, 13, "칩 색이 항목 결과이고, 칩을 두 번 누르면 그 항목만 바로 다시 실행합니다.")]))
    im, _ = card_scene(6, "6 · DECISION", "판정 결과 → 다음 단계")
    out.append((10, im, [], [(0, 5, "판정이 통과면 매뉴얼 테스트, 보류면 FAIL 분석, 재실행 필요면 환경을 고친 뒤 다시 실행합니다."),
                             (5, 10, "리포트의 이슈 등록 버튼으로 스크린샷과 로그를 붙여 JIRA에 바로 올릴 수 있습니다.")]))
    # 8. 실제 자동 설치 기록 (results/watch.log · 앱 로그, 2026-10-26)
    im = base("CI/CD 연계 · CT 자동 설치", "실제 자동 설치 기록 — 2026-10-26")
    d = ImageDraw.Draw(im)
    rows = [("13:30:33", "새 버전 발견", "릴리스 2.0.0-20 > 설치된 2.0.0-17"),
            ("13:30:47", "다운로드", "GitHub 릴리스 → com.dart.module.palletizos_2.0.0-20_signed.dm (48.5 MB)"),
            ("13:31:47", "자동 설치", "Platform Settings → Installed Module List → Install from File → 파일 선택"),
            ("13:31:57", "설치 성공", "앱 로그: [Updater] Successfully updated the PalletizOS"),
            ("13:34:30", "스모크 시작", "42개 항목 전체 실행 (기대 버전 2.0.0-20)")]
    for i, (t, k, v) in enumerate(rows):
        y = 180 + i * 140
        d.rounded_rectangle((120, y, 1800, y + 112), 18, fill=PANEL, outline=(220, 226, 234), width=2)
        d.text((160, y + 32), t, font=font(40, "Bold"), fill=NAVY)
        d.text((400, y + 18), k, font=font(34, "Bold"), fill=ACC)
        d.text((400, y + 64), v, font=font(26), fill=SUB)
    out.append((14, im, [(0, 3, (120, 180, 1800, 292)), (3, 6, (120, 320, 1800, 432)), (6, 9, (120, 460, 1800, 572)),
                         (9, 11.5, (120, 600, 1800, 712)), (11.5, 14, (120, 740, 1800, 852))],
                [(0, 6, "오늘 실제 기록입니다. 13시 30분, 감시기가 GitHub에서 새 빌드 2.0.0-20을 찾아 내려받았습니다."),
                 (6, 11.5, "Install from File로 설치해 1분 30초 만에 업데이트 성공을 확인했습니다. 사람은 아무것도 누르지 않았습니다."),
                 (11.5, 14, "설치가 끝나면 이어서 스모크 전체 실행을 시작합니다.")]))
    im, _ = card_scene(7, "7 · STATUS", "현재 상태 · 한계 · 주의사항")
    out.append((11, im, [], [(0, 5.5, "10월 26일 v2.0.0 기준 42개 중 29개 통과, 6개 실패입니다."),
                             (5.5, 11, "실패는 자동화 쪽 한계, 이미 고친 실행기 오류, 다시 녹화할 시나리오로 분류됐고, 제품 결함으로 분류된 것은 없습니다.")]))
    # 10. 마무리
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    d.text((W // 2, 430), "PalletizOS 스모크 자동화", font=font(76, "Black"), fill=(255, 255, 255), anchor="mm")
    d.text((W // 2, 540), "새 빌드 → 자동 설치 → 무인 확인 → 리포트 · JIRA", font=font(36, "Medium"), fill=(201, 214, 228), anchor="mm")
    d.text((W // 2, 620), "자세한 내용: dart_autotest\\MANUAL.md · 소개 자료 PDF", font=font(28), fill=(157, 182, 208), anchor="mm")
    out.append((6, im, [], [(0, 6, "새 빌드가 나올 때마다 자동으로 설치하고 확인합니다. 감사합니다.")]))
    return out


# ---------------------------------------------------------------- 렌더
SUBF = font(38, "Medium")


def subtitle(im, text):
    d = ImageDraw.Draw(im, "RGBA")
    lines = wrap(d, text, SUBF, 1640)
    lh = 54
    h = lh * len(lines) + 34
    y0 = H - 40 - h
    d.rounded_rectangle((120, y0, W - 120, H - 40), 16, fill=(10, 16, 28, 215))
    for i, ln in enumerate(lines):
        d.text((W // 2, y0 + 17 + i * lh + lh // 2), ln, font=SUBF, fill=(255, 255, 255), anchor="mm")


def frame(base_im, hls, subs, t):
    im = base_im.copy()
    d = ImageDraw.Draw(im)
    for a, b, box in hls:
        if a <= t < b:
            for k in range(4):
                d.rounded_rectangle((box[0] - 6 - k, box[1] - 6 - k, box[2] + 6 + k, box[3] + 6 + k), 14, outline=HL)
    for a, b, s in subs:
        if a <= t < b:
            subtitle(im, s)
    return im


def ts(sec):
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


TTS_DIR = IA / "tts"
WAV = HERE / "intro_narration.wav"
RATE = 22050


def tts_all(texts):
    """자막 문장을 Windows 음성(Microsoft Heami, 한국어)으로 읽어 tts/NN.wav로 저장 (오프라인, 외부 전송 없음).
    반환: 각 파일의 길이(초)."""
    import json
    import wave
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    jf = TTS_DIR / "texts.json"
    jf.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$t = Get-Content -Raw -Encoding UTF8 '" + str(jf) + "' | ConvertFrom-Json;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1;"
        "$s.SelectVoice($v.VoiceInfo.Name); $s.Rate = 1;"
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(" + str(RATE) + ", [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
        "for ($i = 0; $i -lt $t.Count; $i++) { $f = '" + str(TTS_DIR) + "\\{0:D2}.wav' -f $i;"
        " $s.SetOutputToWaveFile($f, $fmt); $s.Speak([string]$t[$i]); $s.SetOutputToNull() }"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    out = []
    for i in range(len(texts)):
        with wave.open(str(TTS_DIR / f"{i:02}.wav")) as w:
            out.append(w.getnframes() / w.getframerate())
    return out


def retime(sc, lens):
    """음성 길이에 맞춰 자막 구간을 늘린다 (구간 = max(원래 길이, 음성 + 0.6초)). 강조 구간도 같은 비율로 옮긴다."""
    k, out = 0, []
    for dur, im, hls, subs in sc:
        old, new = [0.0], [0.0]
        for a, b, s_ in subs:
            ln = max(b - a, lens[k] + 0.6)
            old.append(b)
            new.append(new[-1] + (a - old[-2]) + ln)
            k += 1
        tail = dur - old[-1]
        old.append(dur)
        new.append(new[-1] + max(tail, 0.4))

        def m(t, old=old, new=new):
            for i in range(1, len(old)):
                if t <= old[i] + 1e-9:
                    o0, o1, n0, n1 = old[i - 1], old[i], new[i - 1], new[i]
                    return n0 + (t - o0) * (n1 - n0) / max(o1 - o0, 1e-9)
            return new[-1]
        out.append((new[-1], im, [(m(a), m(b), bx) for a, b, bx in hls], [(m(a), m(b), s_) for a, b, s_ in subs]))
    return out


def render():
    import wave
    sc = scenes()
    texts = [s_ for _, _, _, subs in sc for _, _, s_ in subs]
    lens = tts_all(texts)
    sc = retime(sc, lens)
    # 내레이션 트랙: 각 자막 시작 시점 + 0.15초에 해당 음성
    total = sum(d for d, _, _, _ in sc)
    buf = bytearray(int((total + 1) * RATE) * 2)
    t0, k = 0.0, 0
    for dur, _, _, subs in sc:
        for a, b, s_ in subs:
            with wave.open(str(TTS_DIR / f"{k:02}.wav")) as w:
                data = w.readframes(w.getnframes())
            pos = int((t0 + a + 0.15) * RATE) * 2
            buf[pos:pos + len(data)] = data
            k += 1
        t0 += dur
    with wave.open(str(WAV), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(buf))
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(WAV), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(OUT)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    srt, n, t0, thumbs = [], 1, 0.0, []
    for dur, im, hls, subs in sc:
        for a, b, s_ in subs:
            srt.append(f"{n}\n{ts(t0 + a)} --> {ts(t0 + b)}\n{s_}\n")
            n += 1
        frames = int(dur * FPS)
        last_key = None
        for i in range(frames):
            t = i / FPS
            key = (tuple(j for j, h in enumerate(hls) if h[0] <= t < h[1]), tuple(j for j, x in enumerate(subs) if x[0] <= t < x[1]))
            if key != last_key:
                cur = frame(im, hls, subs, t)
                last_key = key
            fr = cur
            fade = min(1.0, t / 0.35, (dur - t) / 0.35)  # 장면 앞뒤 0.35초 페이드
            if fade < 1.0:
                fr = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), cur, max(0.0, fade))
            p.stdin.write(fr.tobytes())
            if i == int(min(dur * 0.6, dur - 1) * FPS):
                thumbs.append(cur.resize((480, 270)))
        t0 += dur
    p.stdin.close()
    p.wait()
    SRT.write_text("\n".join(srt), encoding="utf-8-sig")
    sheet = Image.new("RGB", (480 * 5, 270 * 2), (0, 0, 0))
    for i, th in enumerate(thumbs[:10]):
        sheet.paste(th, ((i % 5) * 480, (i // 5) * 270))
    sheet.save(HERE / "intro_contact.png")
    print(OUT, f"{t0:.0f}s", OUT.stat().st_size // 1024, "KB", "· 음성", f"{sum(lens):.0f}s")


if __name__ == "__main__":
    render()
