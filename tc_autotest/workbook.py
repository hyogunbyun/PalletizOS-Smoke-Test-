"""TC·체크리스트 엑셀 읽기/쓰기.

- 읽기: 시트마다 앞 20행에서 머리글 줄(Expect·기대결과·점검내용 등)을 찾아 데이터 행을 뽑는다.
  사내 표준 TC 양식(8행 머리글, B~AD)과 자유 양식 체크리스트 모두 같은 규칙으로 읽는다.
- 쓰기: 원본은 건드리지 않고 '<이름>_자동판정_<시각>.xlsx' 사본에 Result·Comment·Tester·Test Date 를 채운다.
  Result 열이 없는 체크리스트는 맨 오른쪽에 '자동 판정'·'판정 근거'·'판정 일시' 열을 덧붙인다.
"""
import re
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl

HEAD = {
    "no": ["no", "no.", "번호", "#", "순번"],
    "expect": ["expect result", "expected result", "expect", "expected", "기대결과", "기대 결과", "예상결과", "판정기준", "확인사항"],
    "desc": ["description", "test step", "test steps", "절차", "점검내용", "점검 내용", "내용", "시험절차", "수행절차"],
    "result": ["result", "결과", "판정", "pass/fail"],
    "comment": ["comment", "비고", "코멘트", "메모"],
    "tester": ["tester", "시험자", "평가자", "담당"],
    "date": ["test date", "시험일", "평가일", "일자"],
}
TESTER = "자동평가(PalletizOS_TC)"


def _norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def _kind(cell):
    t = _norm(cell)
    if not t:
        return None
    for k, names in HEAD.items():
        if t in names or any(t.startswith(n) for n in names if len(n) > 3):
            return k
    return None


def find_header(ws, scan=20):
    """머리글 줄 번호와 {종류: 열번호}. expect 또는 desc 가 있는 줄을 머리글로 본다."""
    best = None
    for r in range(1, min(scan, ws.max_row) + 1):
        cols = {}
        for c in range(1, min(ws.max_column, 40) + 1):
            k = _kind(ws.cell(r, c).value)
            if k and k not in cols:
                cols[k] = c
        # 기대결과 열이 있거나, 내용+결과 열이 함께 있어야 TC/체크리스트로 본다 (History 시트의 Description 만 있는 표 제외)
        if "expect" in cols or ("desc" in cols and "result" in cols):
            if best is None or len(cols) > len(best[1]):
                best = (r, cols)
    return best


def read_rows(path):
    """[{sheet, row, no, text, cells}] — text 는 판정 결과 열을 뺀 그 행 글자 전부(매칭용)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for ws in wb.worksheets:
        h = find_header(ws)
        if not h:
            continue
        hr, cols = h
        skip = {cols.get(k) for k in ("result", "comment", "tester", "date")}
        heads = {c: _norm(ws.cell(hr, c).value) for c in range(1, ws.max_column + 1)}
        blank = 0
        for r in range(hr + 1, ws.max_row + 1):
            vals = {c: ws.cell(r, c).value for c in range(1, ws.max_column + 1) if c not in skip}
            texts = [str(v) for v in vals.values() if v not in (None, "")]
            key_txt = "".join(str(ws.cell(r, cols[k]).value or "") for k in ("expect", "desc") if k in cols)
            if not key_txt.strip():
                blank += 1
                if blank >= 5:
                    break
                continue
            blank = 0
            no = ws.cell(r, cols["no"]).value if "no" in cols else r - hr
            if "no" in cols and str(no or "").strip() in ("", "-", "—"):
                continue  # 'SD021. PalletizOS Jog Screen' 같은 구분(섹션) 행 — TC 아님 (11-02 Lite V2.1 에서 TC 로 셈)
            out.append({"sheet": ws.title, "row": r, "no": no, "text": " | ".join(texts),
                        "title": " / ".join(str(vals[c]) for c in vals if vals[c] not in (None, "") and
                                            heads.get(c, "").startswith(("traceability", "function", "항목", "title", "test case", "점검항목", "구분", "기능")))[:160]
                        or str(ws.cell(r, cols.get("desc", cols.get("expect"))).value or "")[:120]})
    return out


STATUS_TEXT = {"pass": "Pass", "warn": "Pass", "flaky": "Pass", "fail": "Fail", "na": "NT", "env": "NT", "partial": "NT"}


def write_results(src, rows, dest_dir=None):
    """rows: read_rows 결과에 status/msg 를 붙인 것. 사본 경로를 돌려준다."""
    src = Path(src)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    stem = re.sub(r"(_자동판정_\d{8}_\d{4})+$", "", src.stem)  # 이미 판정한 사본을 다시 가져와도 이름이 길어지지 않게
    dest = Path(dest_dir or src.parent) / f"{stem}_자동판정_{stamp}{src.suffix}"
    shutil.copyfile(src, dest)
    wb = openpyxl.load_workbook(dest)  # 수식·서식·드롭다운 유지
    today = datetime.now().strftime("%Y.%m.%d")
    by_sheet = {}
    for x in rows:
        by_sheet.setdefault(x["sheet"], []).append(x)
    for name, items in by_sheet.items():
        ws = wb[name]
        hr, cols = find_header(ws)
        if "result" not in cols:  # 결과 열이 없는 체크리스트 → 오른쪽에 덧붙임
            base = ws.max_column + 1
            for i, t in enumerate(["자동 판정", "판정 근거", "판정 일시"]):
                ws.cell(hr, base + i, t)
            cols.update(result=base, comment=base + 1, date=base + 2)
        for x in items:
            r = x["row"]
            ws.cell(r, cols["result"], STATUS_TEXT.get(x["status"], "NT"))
            note = f"[자동] {x['msg']}".strip()
            if "comment" in cols:
                old = ws.cell(r, cols["comment"]).value
                ws.cell(r, cols["comment"], f"{old}\n{note}" if old and not str(old).startswith("[자동]") else note)
            if "tester" in cols and x["status"] in ("pass", "warn", "flaky", "fail"):
                ws.cell(r, cols["tester"], TESTER)
            if "date" in cols and x["status"] in ("pass", "warn", "flaky", "fail"):
                ws.cell(r, cols["date"], today)
    wb.save(dest)
    return dest
