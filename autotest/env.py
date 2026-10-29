"""실행 환경 준비: 시뮬레이터 → 앱 → 제어기 연결 → PalletizOS 진입. 이미 된 단계는 건너뛴다."""
import os
import subprocess
import time
import winreg

from .ui import EL, SPEED, SPEED_CONNECT, UI, EnvError, set_speed

APP_EXE = r"C:\Dr.Dart-Platform\Dr.Dart-Platform.exe"
APP_DIR = r"C:\Dr.Dart-Platform"
SIM = "dev-simulator"
PF = EL["platform"]


def _docker(*args, timeout=60):
    r = subprocess.run(["wsl.exe", "-d", "rancher-desktop", "-e", "docker", *args],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def docker_ready():
    """Docker 엔진(Rancher Desktop의 WSL)이 응답하는지."""
    try:
        r = subprocess.run(["wsl.exe", "-d", "rancher-desktop", "-e", "docker", "info", "--format", "{{.ServerVersion}}"],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        return False


def wait_docker(log=print, timeout=900):
    """Docker 엔진이 켜질 때까지 대기 (최대 15분). 로그온 직후엔 Rancher Desktop이 몇 분 걸려 켜짐 →
    그 사이 이미지 조회가 빈 값이라 '이미지 없음'으로 오판했음 (2026-10-27 07:46). 켜지면 True."""
    end, told = time.time() + timeout, False
    while time.time() < end:
        if docker_ready():
            return True
        if not told:
            log("Docker 엔진(Rancher Desktop)이 아직 켜지지 않음 → 켜질 때까지 대기 (최대 15분)")
            told = True
        time.sleep(15)
    return False


def _create_simulator(log):
    """컨테이너가 없으면 남아 있는 이미지로 다시 만든다 (elements.yaml의 simulator 설정).

    2026-10-20 실제 발생: PC 재부팅 후 컨테이너·compose 네트워크가 사라지고 이미지만 남음.
    ROBOT_MODEL이 빠지면 DRCF가 rc=139로 1초 만에 죽기를 반복해 unhealthy가 된다.
    시작 명령이 'start_services.sh && bash'라 -it(터미널) 없이 만들면 bash가 바로 끝나 컨테이너가 멈춘다.
    """
    sim = EL.get("simulator", {})
    image = sim.get("image")
    if not image:
        raise EnvError(f"컨테이너 {SIM}이(가) 없고 elements.yaml에 simulator.image가 없어 만들 수 없음")
    if not _docker("images", "-q", image):
        raise EnvError(f"컨테이너 {SIM}이(가) 없고 이미지도 없음: {image} (Dr.Dart 도구로 시뮬레이터를 한 번 받아 두세요)")
    # 재시작 정책은 걸지 않는다: dockerd 재시작 뒤 자동으로 다시 켜진 컨테이너는 DRCF가 rc=139로 죽기를 반복했다
    # (2026-10-20 08:20 실측). 이 이미지는 새 컨테이너만 정상 → ensure_simulator가 지우고 새로 만든다
    args = ["run", "-dit", "--name", SIM]
    for k, v in (sim.get("env") or {}).items():
        args += ["-e", f"{k}={v}"]
    for p in sim.get("ports") or []:
        args += ["-p", str(p)]
    for u in sim.get("ulimits") or []:   # memlock=-1 없으면 DRCF segfault 반복 (2026-10-20 원인 확정)
        args += ["--ulimit", str(u)]
    log(f"시뮬레이터 컨테이너가 없어 새로 만듦 ({sim.get('env', {}).get('ROBOT_MODEL', '?')})")
    _docker(*args, image, timeout=120)


def _drcf_state():
    """(DRCF pid 또는 '', 제어기 포트 12345 대기 여부). 12345 = 0x3039, /proc/net/tcp 상태 0A = LISTEN."""
    out = _docker("exec", SIM, "sh", "-c",
                  "pgrep -x DRCF | head -1; grep -qE ':3039 [0-9A-F:]+ 0A' /proc/net/tcp /proc/net/tcp6 && echo LISTEN")
    lines = out.splitlines()
    pid = lines[0].strip() if lines and lines[0].strip().isdigit() else ""
    return pid, "LISTEN" in out


def _crash_count():
    out = _docker("exec", SIM, "sh", "-c", "grep -c 'rc=139' /home/dra/etc/data/drcf-restart.log 2>/dev/null || echo 0")
    return int(out) if out.isdigit() else 0


def _drcf_stable(timeout, hold=20):
    """DRCF가 '같은 pid로 hold초 이상' 살아 있고 12345를 열고 있으면 True.

    이미지의 healthy는 '검사 순간 DRCF 프로세스가 있나'만 봐서, 1초 만에 죽고 다시 뜨는 충돌 반복 중에도
    healthy로 나온다 (2026-10-20 11:17 실측: healthy인데 rc=139 8회). 그래서 같은 pid 유지 + 포트 대기로 판단한다.
    """
    end = time.time() + timeout
    pid0, since = "", 0.0
    while time.time() < end:
        pid, listening = _drcf_state()
        if pid and pid == pid0:
            if listening and time.time() - since >= hold:
                return True
        else:
            pid0, since = pid, time.time()
        time.sleep(3)
    return False


def ensure_simulator(log=print):
    """제어기(DRCF)가 안정적으로 떠 있으면 그대로 / 없으면 새로 만듦 / 있으면 켜 보고 안 되면 지우고 새로 만듦.

    2026-10-20 실측: 재부팅 후 컨테이너 소실, ROBOT_MODEL 누락 시·dockerd 재시작으로 꺼졌다 켜진 컨테이너에서 DRCF rc=139 반복.
    Rancher 재설치(WSL VM 재기동) 뒤에는 새 컨테이너도 DRCF가 시작 직후 segfault — 원인 미확정(docs/FINDINGS P5 참고).
    """
    if not wait_docker(log):
        raise EnvError("Docker 엔진(Rancher Desktop)이 15분 안에 켜지지 않음 — Rancher Desktop 창에서 상태 확인")
    running = _docker("inspect", "-f", "{{.State.Running}}", SIM) == "true"
    if running and _drcf_stable(timeout=40):
        return
    if _docker("ps", "-a", "-q", "--filter", f"name=^{SIM}$"):
        if not running:
            log("시뮬레이터 시작: " + SIM)
            _docker("start", SIM)
            if _drcf_stable(timeout=150):
                return
        log(f"시뮬레이터 제어기(DRCF)가 안정적으로 뜨지 않음 (충돌 {_crash_count()}회) → 컨테이너를 새로 만듦")
        _docker("rm", "-f", SIM, timeout=60)
    _create_simulator(log)
    if not _drcf_stable(timeout=240):
        raise EnvError(f"새로 만든 시뮬레이터도 제어기(DRCF)가 4분 안에 안정적으로 뜨지 않음 (충돌 {_crash_count()}회, rc=139=segfault). "
                       f"컨테이너 안 /home/dra/etc/data/drcf-restart.log, VM dmesg 확인 — WSL 재시작(wsl --shutdown) 후 재시도 권장")


def platform_version():
    """설치 정보(레지스트리)의 Dr.Dart-Platform 버전."""
    roots = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, path in roots:
        try:
            k = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                sk = winreg.OpenKey(k, winreg.EnumKey(k, i))
                name = winreg.QueryValueEx(sk, "DisplayName")[0]
                if name.startswith("Dr.Dart-Platform"):
                    return winreg.QueryValueEx(sk, "DisplayVersion")[0]
            except OSError:
                continue
    return None


def launch_app():
    """VS Code 등에서 물려받은 ELECTRON_RUN_AS_NODE가 있으면 앱이 창 없이 바로 종료된다 → 제거 후 실행."""
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}
    subprocess.Popen([APP_EXE], cwd=APP_DIR, env=env,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def app_running():
    # 바이트로 받음: tasklist는 한국어 콘솔 인코딩(cp949)으로 출력 → UTF-8 모드(-X utf8)에서 text=True면 해석 실패로 None (2026-10-22)
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Dr.Dart-Platform.exe", "/NH"], capture_output=True)
    return b"Dr.Dart-Platform.exe" in (r.stdout or b"")


def kill_app():
    subprocess.run(["taskkill", "/IM", "Dr.Dart-Platform.exe", "/F"], capture_output=True)
    # 3초 고정 대기 대신 프로세스가 전부 사라질 때까지(최대 20초): 덜 죽은 프로세스가 남으면 다음 실행 앱이
    # 단일 실행 잠금 때문에 뜨자마자 스스로 꺼짐 (2026-10-26 10:37 '앱 창이 안정되지 않음' 추정 원인)
    for _ in range(40):
        if not app_running():
            break
        time.sleep(0.5)
    time.sleep(1)


def ensure_ready(ui: UI, log=print):
    """연결 단계는 speed_connect(느리게), 끝나면 speed(빠르게)로 돌린다."""
    set_speed(SPEED_CONNECT)
    try:
        _ensure_ready(ui, log)
    finally:
        set_speed(SPEED)


def _ensure_ready(ui: UI, log=print):
    ensure_simulator(log)
    if not ui.exists() and app_running():
        # 창은 없는데 프로세스만 남은 앱(이전 실행이 도중에 죽은 경우) → 정리하고 새로 띄움
        log("창 없이 남은 앱 프로세스 정리")
        from .events import ev
        ev("창 없이 남은 Dr.Dart 프로세스 발견 → 정리 후 새로 실행")
        kill_app()
    if not ui.exists():
        from .winutil import foreground, give_back_focus
        fg = foreground()  # 사용자가 지금 쓰고 있는 창
        log("앱 실행")
        launch_app()
        if not ui.win.exists(timeout=90):
            raise EnvError("앱 창이 뜨지 않음")
        if not ui.wait_window_stable(timeout=90):  # 시작 화면 → 본 창 전환이 끝날 때까지
            raise EnvError("앱 창이 안정되지 않음 (떴다 사라짐 반복)")
        if ui.mode == "background":  # 앱이 앞으로 튀어나와 업무 창을 가림 → 포커스 되돌림 (2026-10-22 사용자 요청)
            give_back_focus(fg, ui.hwnd())
    ui.warm_up()
    ui.ensure_maximized()
    _connect_if_needed(ui, log)
    _take_over_if_needed(ui, log)
    _skip_tour(ui)
    _open_palletizos(ui, log)
    ui.check_language()


def _texts(ui):
    return {t.window_text() for t in ui.wrapper().descendants(control_type="Text") if t.window_text()}


def _connect_if_needed(ui, log):
    w = ui.wrapper()
    on_connect = lambda: bool(set(PF["connect_title"]) & _texts(ui))  # noqa: E731
    if not on_connect():
        return
    log("가상 제어기 연결")
    if PF.get("connect_mode", "list") == "manual":
        try:
            _connect_manual(ui, log, on_connect)
            return
        except EnvError as e:
            log(f"  수동 IP 입력으로 연결 못 함 → 목록 방식으로 재시도 ({e})")
    cell = None
    for _ in range(6):  # 앱이 막 떴을 때는 제어기 방송을 못 받았을 수 있음 → 최대 약 30초 새로고침
        ui.click(ui.win_button(PF["refresh"]), settle=5)
        cell = next((d for d in w.descendants(control_type="DataItem") if d.window_text() == PF["sim_ip"]), None)
        if cell is not None:
            break
    if cell is None:
        raise EnvError(f"제어기 목록에 {PF['sim_ip']} 없음")
    ui.click(cell)
    ui.click(ui.win_button(PF["connect"]), settle=3)
    if not ui.wait_for(lambda: not on_connect(), timeout=60):
        raise EnvError("제어기 연결 실패")
    time.sleep(5)
    ui.warm_up()


def _connect_manual(ui, log, on_connect):
    """'수동으로 IP 입력' 라디오 → IP 입력칸(1칸 또는 옥텟 4칸)에 sim_ip → 연결.
    목록 방식은 제어기 방송을 받아야 행이 뜨는데, 방송이 안 오면 새로고침해도 목록이 비어 있음 (2026-10-22 사용자 화면)."""
    w = ui.wrapper()
    names = PF.get("manual_radio", [])
    radios = [r for r in w.descendants(control_type="RadioButton") if r.element_info.rectangle.width() > 0]
    radio = next((r for r in radios if (r.element_info.name or "").strip() in names), None)
    if radio is None and len(radios) == 2:  # 이름이 다르면 두 번째 라디오(첫 번째 = 목록에서 선택)
        radio = sorted(radios, key=lambda r: r.element_info.rectangle.left)[1]
    if radio is None:
        raise EnvError(f"'수동으로 IP 입력' 선택지를 찾지 못함 (라디오 {[r.element_info.name for r in radios]})")
    before = {e.element_info.runtime_id for e in w.descendants(control_type="Edit")}
    ui.click(radio, settle=1.5, label="수동으로 IP 입력")

    def edits():
        es = [e for e in ui.wrapper().descendants(control_type="Edit")
              if e.element_info.rectangle.width() > 0 and e.is_enabled()]
        new = [e for e in es if e.element_info.runtime_id not in before]
        return sorted(new or es, key=lambda e: (e.element_info.rectangle.top, e.element_info.rectangle.left))

    if not ui.wait_for(lambda: bool(edits()), 8):
        raise EnvError("IP 입력칸이 나타나지 않음")
    es, ip = edits(), PF["sim_ip"]
    if len(es) >= 4 and all(e.element_info.rectangle.top == es[0].element_info.rectangle.top for e in es[:4]):
        for e, part in zip(es[:4], ip.split(".")):  # 옥텟 4칸 입력
            ui.set_text(e, part, label=f"IP {part}")
    else:
        ui.set_text(es[0], ip, label=f"IP {ip}")
    btn = ui.win_button(PF["connect"])
    if btn is None or not ui.wait_for(lambda: ui.win_button(PF["connect"]).is_enabled(), 8):
        raise EnvError("IP를 넣었는데 '연결' 버튼이 활성화되지 않음")
    ui.click(ui.win_button(PF["connect"]), settle=3, label="연결")
    if not ui.wait_for(lambda: not on_connect(), timeout=60):
        raise EnvError("수동 IP로 제어기 연결 실패")
    time.sleep(5)
    ui.warm_up()


def _take_over_if_needed(ui, log):
    if not ui.wait_for(lambda: bool(set(PF["takeover_title"]) & _texts(ui)), timeout=8):
        return
    log("제어권 강제 회수 (가상 제어기)")
    ui.click(ui.win_button(PF["takeover_button"]), settle=3)
    if not ui.wait_for(lambda: not (set(PF["takeover_title"]) & _texts(ui)), timeout=30):
        raise EnvError("제어권 회수 실패")
    time.sleep(5)
    ui.warm_up()


def _skip_tour(ui):
    try:
        ui.root()
        return  # PalletizOS가 떠 있으면 투어는 뒤에 가려진 상태 → 건드리지 않는다
    except EnvError:
        pass
    b = ui.win_button(PF["tour_skip"])
    if b is not None and b.is_enabled():
        ui.click(b, settle=1.5)


def _open_palletizos(ui, log):
    try:
        ui.root()
        return
    except EnvError:
        pass
    _login_if_needed(ui, log, wait=1)
    if ui.wait_for(lambda: ui.root() is not None, timeout=2):
        return
    log("PalletizOS 열기")
    w = ui.wrapper()
    tile = next((i for i in w.descendants(control_type="Image") if i.window_text() == PF["palletizos_tile"]), None)
    if tile is None:  # Home 모듈이 안 열려 있으면 메인 화면의 Home 모듈 버튼부터
        def find_home():
            return next((b for b in ui.wrapper().descendants(control_type="Button")
                         if (b.window_text() or "").startswith("home icon " + PF["home_module"])), None)
        # 앱을 막 띄운 직후엔 메인 화면 버튼이 늦게 그려짐 → 바로 찾으면 '없음'으로 환경 오류(2026-10-26 10:12, 10-19 콜드 스타트)
        ui.wait_for(lambda: find_home() is not None, 30, 1)
        home = find_home()
        if home is None:
            raise EnvError("Home 모듈 버튼을 찾지 못함 (30초 대기)")
        ui.click(home, settle=3)
        tile = next((i for i in w.descendants(control_type="Image") if i.window_text() == PF["palletizos_tile"]), None)
    if tile is None:
        raise EnvError("PalletizOS 타일을 찾지 못함")
    for attempt in range(3):  # 다른 층(안내 투어 등)에 가려져 있으면 건너뛰기/ESC 후 다시 (2026-10-27 15:04 실행기 오류)
        try:
            ui.click(tile, settle=5)
            break
        except AssertionError as ex:
            if "가려져" not in str(ex) or attempt == 2:
                raise EnvError(f"PalletizOS 아이콘을 누르지 못함: {ex}")
            log("PalletizOS 아이콘이 다른 화면에 가려짐 → 안내 투어 건너뛰기/ESC 후 다시")
            skip = ui.win_button(PF["tour_skip"]) or ui.win_button(["건너뛰기", "Skip"])
            if skip is not None:
                try:
                    ui.click(skip, settle=1.5)
                except AssertionError:
                    ui.esc()
            else:
                ui.esc()
            tile = next((i for i in ui.wrapper().descendants(control_type="Image") if i.window_text() == PF["palletizos_tile"]), tile)
    # 새 버전을 설치한 직후 첫 실행은 모듈을 처음 불러오느라 로그인 화면이 20초 넘게 늦게 뜸 →
    # 예전엔 20초만 기다리고 넘어가 '화면이 열리지 않음'으로 실패(2026-10-27 08:08·08:11). 최대 3분 동안 로그인 화면/본 화면을 계속 확인
    def opened():
        try:
            return ui.root() is not None
        except EnvError:
            return False
    end, logged = time.time() + 180, False
    while time.time() < end:
        if opened():
            break
        if not logged and ui.win_button(PF["palletizos_login"]["button"]) is not None:
            _login_if_needed(ui, log, wait=1)
            logged = True
        time.sleep(2)
    if not opened():
        raise EnvError("PalletizOS 화면이 3분 안에 열리지 않음 (로그인 화면 " + ("눌렀음" if logged else "안 나타남") + ")")
    time.sleep(3)


def _login_if_needed(ui, log, wait=20):
    """PalletizOS 로그인 화면이면 기본 계정(비밀번호 불필요한 Operator 가정)으로 Log In. 실패하면 중단."""
    button = PF["palletizos_login"]["button"]
    if not ui.wait_for(lambda: ui.win_button(button) is not None, timeout=wait):
        return
    log("PalletizOS 로그인 (기본 계정)")
    ui.click(ui.win_button(button), settle=4)
    if ui.win_button(button) is not None:
        raise EnvError("PalletizOS 로그인 실패 — 기본 계정에 비밀번호가 필요할 수 있음 (Operator로 바꿔 두세요)")
