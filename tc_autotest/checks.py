"""TC·체크리스트 자동 판정 루틴.

각 루틴은 엑셀 행의 글자(Function·Description·Expect 등)에 `match` 의 낱말 묶음이 모두 들어 있으면 그 행을 맡는다.
루틴은 기존 스모크 엔진(ctx.ui, check, NotApplicable)을 그대로 쓰고, 화면을 읽거나 팝업을 열었다가 Cancel/닫기만 한다.
Save·Start·Move To·Restore·Initialize·업로드는 누르지 않는다 (스모크와 같은 안전 규칙).

근거 값은 GitHub palletizingsolution 소스(en.json·toolIo.types.ts 등)와 2026-11-02 v2.0.0-25 화면 실측.
"""
import json
import re

from autotest.flows import NotApplicable, check
from autotest.flows_menus import _io_tab, _open, _selected, _settings

CHECKS = []


def tc_check(key, title, desc, match, admin=True):
    """match: [("낱말", "낱말"), ...] — 묶음 하나의 낱말이 행 글자에 모두 있으면(대소문자 무시) 이 루틴이 맡음."""
    def deco(fn):
        CHECKS.append({"key": key, "title": title, "desc": desc, "match": match, "fn": fn, "admin": admin})
        return fn
    return deco


# ---------------------------------------------------------------- 공통 도우미
def _cy(e):
    r = e.rectangle()
    return (r.top + r.bottom) // 2


def _row(elems, ref, tol=25):
    return sorted([e for e in elems if abs(_cy(e) - _cy(ref)) <= tol], key=lambda e: e.rectangle().left)


def _texts(ui):
    return [t for t in ui.top_all("Text") if t.rectangle().width() > 0]


def _names(ui):
    return set(ui.top_names())


def _open_tool_config(ctx):
    ui = ctx.ui
    _settings(ctx, "Tool")
    ui.click(ui.top_find("Configuration"), settle=2.5, label="Tool Configuration")
    check(ui.wait_for(lambda: "Tool Configuration" in ui.top_names(), 6), "Tool Configuration 팝업이 열리지 않음")


def _cancel(ctx):
    ui = ctx.ui
    b = ui.top_find("Cancel")
    if b is not None:
        ui.click(b, settle=2, label="Cancel (저장 안 함)")


def _zone_rows(ui):
    """Tool Configuration 의 Zone 행: [(번호, 진공 주소 버튼, 센서 주소 버튼, 행 버튼들)]"""
    btns = [b for b in ui.top_all("Button") if b.rectangle().width() > 0]
    rows = []
    for t in _texts(ui):
        m = re.fullmatch(r"Zone(\d+)", t.window_text() or "")
        if not m:
            continue
        row = [b for b in _row(btns, t) if b.rectangle().left > t.rectangle().right]
        nums = [b for b in row if re.fullmatch(r"\d+", b.window_text() or "")]
        rows.append((int(m.group(1)), nums[0] if nums else None, nums[-1] if len(nums) > 1 else None, row))
    return sorted(rows, key=lambda r: r[0])


def _value_right_of(ui, label, ctype="Button"):
    """'Vacuum'·'Sensor' 같은 왼쪽 라벨과 같은 줄의 첫 버튼 이름."""
    lab = next((t for t in _texts(ui) if t.window_text() == label and t.rectangle().left < 300), None)
    if lab is None:
        return None
    row = [b for b in _row(ui.top_all(ctype), lab) if b.rectangle().left > lab.rectangle().right]
    return row[0].window_text() if row else None


# ---------------------------------------------------------------- #1508 Tool Configuration
@tc_check("CFG_DEFAULT", "Tool Configuration 기본 배치",
          "Vacuum Digital IO·Single, Sensor Flange IO, Zone1~4 진공 5~8·센서 1~4, Blow off 12, Reducer 13",
          [("tool configuration", "기본 배치"), ("tool configuration", "default")])
def cfg_default(ctx):
    ui = ctx.ui
    _open_tool_config(ctx)
    try:
        got = {k: _value_right_of(ui, k) for k in ("Vacuum", "Sensor", "Blow off", "Reducer")}
        ctx.step(f"신호 타입 {got}")
        check(got["Vacuum"] == "Digital IO", f"Vacuum 신호 타입 {got['Vacuum']!r} (기대 Digital IO)")
        check(got["Sensor"] == "Flange IO", f"Sensor 신호 타입 {got['Sensor']!r} (기대 Flange IO)")
        check(got["Blow off"] == "Digital IO", f"Blow off 신호 타입 {got['Blow off']!r} (기대 Digital IO)")
        check(got["Reducer"] == "Digital IO", f"Reducer 신호 타입 {got['Reducer']!r} (기대 Digital IO)")
        single = ui.top_find("Single", "RadioButton")
        check(single is not None and _selected(single), "Acting 이 Single 로 선택돼 있지 않음")
        rows = _zone_rows(ui)
        addr = [(n, v.window_text() if v else None, s.window_text() if s else None) for n, v, s, _ in rows]
        ctx.step(f"Zone 주소 {addr}")
        check([a[0] for a in addr] == [1, 2, 3, 4], f"Zone 행이 1~4 가 아님: {[a[0] for a in addr]}")
        check([a[1] for a in addr] == ["5", "6", "7", "8"], f"Zone1~4 진공 주소 {[a[1] for a in addr]} (기대 5·6·7·8)")
        check([a[2] for a in addr] == ["1", "2", "3", "4"], f"Zone1~4 센서 주소 {[a[2] for a in addr]} (기대 1·2·3·4)")
        names = [b.window_text() for b in ui.top_all("Button")]
        check("12" in names and "13" in names, "Blow off 12 · Reducer 13 주소 버튼이 없음")
    finally:
        _cancel(ctx)


@tc_check("CFG_ADDZONE", "Add Zone 상한 4",
          "Zone 4개에서 Add Zone 비활성 + 'Max zone number: 4' (v2.0.0-21 소스 TOOL_IO_ADDABLE_ZONE_COUNT = 4)",
          [("add zone", "상한"), ("add zone", "max zone")])
def cfg_addzone(ctx):
    ui = ctx.ui
    _open_tool_config(ctx)
    try:
        n = len(_zone_rows(ui))
        if n != 4:
            raise NotApplicable(f"Zone 이 {n}개 — 4개(기본) 상태에서만 판정 가능")
        add = ui.top_find("Add Zone")
        hint = next((t.window_text() for t in _texts(ui) if (t.window_text() or "").startswith("Max zone number")), None)
        ctx.step(f"Add Zone 활성={add.is_enabled() if add else None} · 안내 {hint!r}")
        check(add is not None, "Add Zone 버튼 없음")
        check(hint == "Max zone number: 4", f"안내 문구 {hint!r} (기대 'Max zone number: 4')")
        check(not add.is_enabled(), "Zone 4개인데 Add Zone 이 활성 (기대: 비활성)")
    finally:
        _cancel(ctx)


@tc_check("CFG_NODEL", "Zone1~4 삭제 버튼 없음",
          "기본 Zone1~4 행에는 삭제(Delete zone) 버튼이 없다 (5번째 이후만)",
          [("zone", "삭제 버튼"), ("delete zone",)])
def cfg_nodelete(ctx):
    ui = ctx.ui
    _open_tool_config(ctx)
    try:
        dels = [b for b in ui.top_all("Button") if (b.window_text() or "") in ("Delete zone", "Delete")]
        rows = _zone_rows(ui)
        hit = [n for n, _, _, row in rows if n <= 4 and any(b in dels for b in row)]
        ctx.step(f"Zone 행 {[r[0] for r in rows]} · 삭제 버튼 있는 행 {hit}")
        check(not hit, f"Zone {hit} 행에 삭제 버튼이 있음")
    finally:
        _cancel(ctx)


# ---------------------------------------------------------------- #1516 Lift 신호 (Lift 미사용)
def _io_names(ui):
    """DO/DI 탭 왼쪽 열(1~8번) 이름: {포트: 이름}. 행 위치는 Value 열의 On/Off 글자로 잡는다
    (DI 탭엔 Test 버튼이 없음 — 2026-11-02 첫 실행에서 'DI 0행')."""
    ons = sorted([t for t in _texts(ui) if t.window_text() in ("On", "Off") and 700 < t.rectangle().left < 1100],
                 key=lambda t: t.rectangle().top)
    texts = [t for t in _texts(ui) if 380 < t.rectangle().left < 760]
    out = {}
    for i, on in enumerate(ons[:8], 1):
        same = [t.window_text() for t in texts if abs(_cy(t) - _cy(on)) <= 20]
        out[i] = same[0] if same else ""
    return out


@tc_check("IO_LIFT_OFF", "Lift 미사용 시 DO3·DO4·DI4·DI5 이름 없음",
          "Lift 를 쓰지 않으면 DO3/DO4 'Lift Up/Down', DI4/DI5 'Lift Top/Bottom Limit' 이름이 붙지 않는다",
          [("lift", "미사용"), ("lift", "not used")], admin=False)
def io_lift_off(ctx):
    ui = ctx.ui
    _open(ctx, "IO", "Modbus Master")
    _io_tab(ctx, "Digital Output")
    do = _io_names(ui)
    _io_tab(ctx, "Digital Input")
    di = _io_names(ui)
    ctx.step(f"DO3 {do.get(3)!r} · DO4 {do.get(4)!r} · DI4 {di.get(4)!r} · DI5 {di.get(5)!r}")
    check(len(do) >= 5 and len(di) >= 5, f"IO 행을 읽지 못함 (DO {len(do)}행, DI {len(di)}행)")
    lift = {"Lift Up", "Lift Down", "Lift Top Limit", "Lift Bottom Limit"}
    bad = [f"{k} {v}" for k, v in (("DO3", do.get(3)), ("DO4", do.get(4)), ("DI4", di.get(4)), ("DI5", di.get(5))) if v in lift]
    check(not bad, f"Lift 를 안 쓰는데 Lift 이름이 붙음: {bad}")


# ---------------------------------------------------------------- #1553 Slip Sheet
SLIP_LABELS = ["Seek Distance", "Seek Speed", "Seek Acceleration", "Retract Offset", "Retract Speed",
               "Retract Acceleration", "Move To Seek Start Position"]


@tc_check("SLIP_LABELS", "Slip Sheet 화면 문구",
          "Seek Distance·Seek Speed·Seek Acceleration·Retract Offset·Retract Speed·Retract Acceleration·Move To Seek Start Position",
          [("slip sheet", "화면 문구"), ("slipsheet", "화면 문구"), ("seek distance", "seek speed", "retract")])
def slip_labels(ctx):
    ui = ctx.ui
    _settings(ctx, "Slipsheet")
    names = _names(ui)
    miss = [n for n in SLIP_LABELS if n not in names]
    ctx.step(f"없는 문구 {miss}")
    check(not miss, f"화면에 없는 문구: {miss}")
    check("Distance" not in [t.window_text() for t in _texts(ui)], "예전 라벨 'Distance' 가 남아 있음")


def _slip_help(ctx, idx):
    ui = ctx.ui
    _settings(ctx, "Slipsheet")
    hb = sorted([b for b in ui.top_all("Button") if not b.window_text() and 30 < b.rectangle().width() < 60
                 and b.rectangle().left > 1300], key=lambda b: b.rectangle().top)
    labels = {t.window_text(): t for t in _texts(ui)}
    want = "Seek Distance" if idx == 0 else "Retract Offset"
    lab = labels.get(want)
    check(lab is not None, f"'{want}' 라벨 없음")
    btn = next((b for b in hb if abs(_cy(b) - _cy(lab)) <= 25), None)
    check(btn is not None, f"'{want}' 옆 도움말(?) 버튼 없음")
    ui.click(btn, settle=2, label=f"{want} 도움말")
    return ui


@tc_check("SLIP_HELP_SEEK", "Seek Distance 도움말",
          "도움말 제목 'Seek Distance' + 설명 'Seek Distance sets how far the Seek Start Position is from the Pick Position Point…'",
          [("seek distance", "도움말"), ("seek distance", "help")])
def slip_help_seek(ctx):
    ui = _slip_help(ctx, 0)
    try:
        ts = [t.window_text() or "" for t in _texts(ui)]
        check(ui.top_find("close") is not None, "도움말 팝업이 열리지 않음 (close 버튼 없음)")
        check(any(t.startswith("Seek Distance sets how far the Seek Start Position is from the Pick Position Point") for t in ts),
              "설명 문구가 소스와 다름")
    finally:
        c = ui.top_find("close")
        if c is not None:
            ui.click(c, settle=1.5, label="도움말 닫기")


@tc_check("SLIP_HELP_RETRACT", "Retract Offset 도움말",
          "제목 'Retract Offset', 소제목 'Retract Z direction', 예시 '–10 entered: …away' / '+10 entered: …toward'",
          [("retract offset", "도움말"), ("retract offset", "help")])
def slip_help_retract(ctx):
    ui = _slip_help(ctx, 1)
    try:
        names = [e.window_text() or "" for e in ui.top_all()]
        check("Retract Z direction" in names, "소제목 'Retract Z direction' 없음")
        check(any(n.startswith("–10 entered: 10 (in/mm) away from the holder") for n in names), "'–10 entered' 예시 없음")
        check(any(n.startswith("+10 entered: 10 (in/mm) toward the holder") for n in names), "'+10 entered' 예시 없음")
    finally:
        c = ui.top_find("close")
        if c is not None:
            ui.click(c, settle=1.5, label="도움말 닫기")


# ---------------------------------------------------------------- #1542 3D Model 팝업
@tc_check("MODEL_POPUP", "3D 모델 팝업 구성",
          "File 슬롯 'No file, default tool' + Upload, Alignment X/Y/Z·RZ/RY/RX, Scale 1, Download 비활성 + 안내, 변경 전 Save 비활성",
          [("3d", "팝업 구성"), ("3d model", "popup")])
def model_popup(ctx):
    ui = ctx.ui
    _settings(ctx, "Tool")
    lab = next((t for t in _texts(ui) if t.window_text() == "3D Model"), None)
    check(lab is not None, "Tool 화면에 '3D Model' 항목 없음")
    btn = next((b for b in ui.top_all("Button") if not b.window_text() and abs(_cy(b) - _cy(lab)) <= 25
                and b.rectangle().left > lab.rectangle().right), None)
    check(btn is not None, "3D Model 열기 버튼 없음")
    ui.click(btn, settle=3, label="3D Model 열기")
    try:
        check(ui.wait_for(lambda: "Alignment" in ui.top_names(), 6), "3D 모델 팝업이 열리지 않음")
        names = [e.window_text() or "" for e in ui.top_all()]
        ctx.step("File·Upload·Alignment·Scale·Download·Save 확인")
        check("File" in names, "'File' 없음")
        check(names.count("Upload") >= 1, "'Upload' 버튼 없음")
        check(any("No file, default tool" in n for n in names), "'No file, default tool' 표시 없음")
        for k in ("X in", "Y in", "Z in", "RZ °", "RY °", "RX °"):
            if k not in names and k.replace(" in", " mm") not in names:
                check(False, f"정합 입력칸 '{k}' 없음")
        scale = next((e for e in ui.top_all("Edit") if e.window_text() == "x"), None)
        check(scale is not None, "Scale 입력칸 없음")
        check(float(scale.iface_value.CurrentValue) == 1.0, f"Scale 기본값 {scale.iface_value.CurrentValue} (기대 1)")
        dl = ui.top_find("Download")
        check(dl is not None and not dl.is_enabled(), "파일이 없는데 Download 가 활성")
        check("Changes are saved, then downloaded as .zip" in names, "Download 안내 문구 없음")
        sv = [b for b in ui.top_all("Button") if b.window_text() == "Save" and b.rectangle().top < 900]
        check(sv and not sv[-1].is_enabled(), "바꾼 것이 없는데 Save 가 활성")
    finally:
        _cancel(ctx)


# ---------------------------------------------------------------- 스모크 결과 연동 (화면 조작 없음)
def _latest_smoke(ctx):
    """지금 설치된 버전으로 돈 가장 최근 스모크 결과 (results/2026*/result.json)."""
    from pathlib import Path

    from autotest.installer import installed_version
    root = Path(__file__).resolve().parent.parent / "results"
    ver = installed_version()
    for d in sorted(root.glob("20*"), reverse=True):
        try:
            r = json.loads((d / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ev = (r.get("expect_version") or "").lstrip("v")
        if not ver or ev != ver:  # 버전을 적지 않고 돈 실행은 어느 빌드인지 모름 → 쓰지 않음 (11-02: 10-27 2.0.0-21 결과를 잘못 씀)
            continue
        if r.get("verdict") in ("통과", "통과(주의)", "보류"):
            return d.name, r, ver
    raise NotApplicable(f"설치 버전 {ver} 로 끝까지 돈 스모크 결과가 없음 — PalletizOS_smoke 를 먼저 실행")


def _smoke_items(ctx, items):
    name, r, ver = _latest_smoke(ctx)
    st = {x["tc"]: x["status"] for x in r.get("results", [])}
    got = {i: st.get(i) for i in items}
    ctx.step(f"스모크 {name} ({ver}): {got}")
    ctx.note = f"근거: 스모크 결과 {name}"
    bad = [f"{i}={s}" for i, s in got.items() if s not in ("pass", "warn", "flaky")]
    check(not bad, f"스모크 {name} 에서 통과하지 않은 항목: {bad}")


@tc_check("SMOKE_MONITOR", "Monitoring 기본 표시 (스모크 결과)", "스모크 H04·H05 통과 = Monitoring 층·박스·진행률 표시 정상",
          [("monitoring", "기본 표시")], admin=False)
def smoke_monitor(ctx):
    _smoke_items(ctx, ["H04", "H05"])


@tc_check("SMOKE_TOOLLIST", "툴 목록 표시 (스모크 결과)", "스모크 S04 통과 = Settings Tool 목록·선택 정상",
          [("툴 목록", "회귀"), ("tool list",)], admin=False)
def smoke_toollist(ctx):
    _smoke_items(ctx, ["S04"])


@tc_check("SMOKE_ALL", "스모크 전체 회귀 (스모크 결과)", "가장 최근 스모크 전체 판정이 통과/통과(주의)",
          [("스모크", "회귀", "항목"), ("smoke", "regression")], admin=False)
def smoke_all(ctx):
    name, r, ver = _latest_smoke(ctx)
    ctx.note = f"근거: 스모크 결과 {name}"
    ctx.step(f"스모크 {name} ({ver}) 판정 {r.get('verdict')}")
    check(r.get("verdict") in ("통과", "통과(주의)"), f"최근 스모크 {name} 판정 {r.get('verdict')} — FAIL 항목 확인 필요")


# ---------------------------------------------------------------- 자동 판정 못 하는 이유 (NT 사유)
NT_REASONS = [
    (("move to",), "로봇이 움직이는 Move To — 자동 평가 대상 아님 (수동)"),
    (("start",), "Start(작업 시작)를 눌러야 함 — 자동 평가 대상 아님 (수동)"),
    (("천장",), "Settings > Robot(천장 높이)은 Super Admin 권한 필요 — 자동 평가 불가"),
    (("ceiling",), "Settings > Robot(천장 높이)은 Super Admin 권한 필요 — 자동 평가 불가"),
    (("restore",), "Restore 실행·복원 지점 필요 — 자동 평가 대상 아님 (수동)"),
    (("initialize",), "Initialize(초기화) — 자동 평가 대상 아님 (수동)"),
    (("업로드",), "파일 업로드·저장 — 자동 평가 대상 아님 (수동)"),
    (("upload",), "파일 업로드·저장 — 자동 평가 대상 아님 (수동)"),
    (("upgrade",), "이전 버전 데이터로 업그레이드 필요 — 수동"),
    (("migration",), "이전 버전 데이터로 업그레이드 필요 — 수동"),
    (("boundary",), "숫자 입력 경계값 — 백그라운드 입력 불가(키보드 입력 필요), 수동"),
    (("저장 불가",), "Save 를 눌러야 함 — 설정 변경 허용 전까지 수동"),
    (("save",), "Save 를 눌러야 함 — 설정 변경 허용 전까지 수동"),
    (("drl",), "DRL Final code 화면은 Admin 에 없음 — 수동"),
    (("depal",), "Depal 레시피 박스를 만들고 바꿔야 함 — 설정 변경 허용 전까지 수동"),
]


def nt_reason(text):
    t = text.lower()
    for words, why in NT_REASONS:
        if all(w in t for w in words):
            return why
    return "이 행에 맞는 자동 점검 루틴 없음 — 수동"


def match_check(title, text=""):
    """행 제목(Traceability·Function·항목 열)으로 매칭. 제목이 비면 행 전체 글자로."""
    t = (title or text).lower()
    for c in CHECKS:
        if any(all(w in t for w in group) for group in c["match"]):
            return c
    return None


# 기능별 루틴 (CHECKS 에 등록됨) — 맨 끝에서 불러와야 순환 import 가 없음
from . import checks_sd024  # noqa: E402,F401
from . import checks_toolio  # noqa: E402,F401
