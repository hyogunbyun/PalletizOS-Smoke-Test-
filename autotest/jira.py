"""FAIL 항목 → JIRA 이슈 (2026-10-22 사용자 요청: 리포트에서 '이슈 등록' → 미리보기 → 등록, 로그·사진 첨부).

- 대상: TER 프로젝트 / 버그 유형 (설정은 jira_config.json, 처음 한 번 `jira_setup.bat`)
- 인증: Atlassian 이메일 + API 토큰 → Windows 자격 증명 'PalletizOS-Smoke-Jira' (파일·로그에 남기지 않음)
- REST v2 (설명은 위키 표기), 첨부는 /attachments (X-Atlassian-Token: no-check)
명령줄: python -m autotest.jira setup | check
"""
import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import secret

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
CFG = ROOT / "jira_config.json"
TARGET = "PalletizOS-Smoke-Jira"
LABEL = "palletizos-smoke"
STD_FIELDS = {"summary", "issuetype", "project", "reporter", "description", "attachment"}


class JiraError(Exception):
    pass


def load_cfg():
    try:
        return json.loads(CFG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def configured():
    c = load_cfg()
    return bool(c.get("site") and c.get("project") and c.get("issuetype_id") and secret.read(TARGET))


# ---------------------------------------------------------------- HTTP
def _auth():
    cred = secret.read(TARGET)
    if not cred:
        raise JiraError("JIRA 인증 정보가 없음 — jira_setup.bat을 먼저 실행하세요")
    return "Basic " + base64.b64encode(f"{cred[0]}:{cred[1]}".encode()).decode()


def _req(method, path, body=None, data=None, headers=None, site=None):
    url = (site or load_cfg()["site"]).rstrip("/") + path
    h = {"Authorization": _auth(), "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        fields = {}
        try:
            j = json.loads(txt)
            fields = j.get("errors", {}) or {}
            msg = "; ".join(j.get("errorMessages", []) + [f"{k}: {v}" for k, v in fields.items()])
        except (ValueError, AttributeError):
            msg = txt[:300]
        err = JiraError(f"JIRA {e.code}: {msg or e.reason}")
        err.code, err.fields = e.code, fields
        raise err
    except urllib.error.URLError as e:
        raise JiraError(f"JIRA 접속 실패: {e.reason}")


def _multipart(path):
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8") + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={b}", "X-Atlassian-Token": "no-check"}


# ---------------------------------------------------------------- 결과 → 이슈 초안
def _run_dir(run):
    if not re.fullmatch(r"\d{8}_\d{6}", run or ""):
        raise JiraError("잘못된 실행 폴더 이름")
    d = RESULTS / run
    if not (d / "result.json").exists():
        raise JiraError(f"결과 파일 없음: {run}")
    return d


def _result(run, tc):
    d = _run_dir(run)
    data = json.loads((d / "result.json").read_text(encoding="utf-8"))
    r = next((x for x in data["results"] if x["tc"] == tc), None)
    if r is None:
        raise JiraError(f"{tc} 항목이 결과에 없음")
    return d, data, r


def attachments(d, r):
    """[(파일 이름, 설명)] — 시도별 스크린샷·앱 로그 발췌·UI 트리 중 실제로 있는 것."""
    out = []
    for a in r.get("attempts", []):
        n = a["attempt"]
        for key, what in (("shot", "실패 시점 앱 화면"), ("log", "이 항목 실행 중 앱 로그"), ("tree", "화면 구조(UI 트리)"),
                          ("detail", "전체 클릭 기록")):
            if a.get(key) and (d / a[key]).exists():
                out.append((a[key], f"{n}차 시도 — {what}"))
    return out


def registered(run):
    p = _run_dir(run) / "jira.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def preview(run, tc):
    d, data, r = _result(run, tc)
    pv, plat = data.get("palletizos_version") or "?", data.get("platform_version") or "?"
    first = r["attempts"][0]["msg"] if r.get("attempts") else r.get("msg", "")
    summary = f"[PalletizOS {pv}] 스모크 {tc} {r['title']} 실패 — {first}"[:240]
    tries = "\n".join(f"* {a['attempt']}차 시도: {a.get('msg') or a.get('status')}" for a in r.get("attempts", []))
    files = attachments(d, r)
    errs = "\n".join(r.get("new_errors", {}).values())
    started = data.get("started", "").replace("T", " ")
    desc = f"""h3. 개요
PalletizOS 스모크 자동화(dart_autotest)에서 *FAIL* 발생 — 원래 상태로 되돌린 뒤 다시 실행해도 같은 결과

h3. 환경
* PalletizOS: {pv} (화면 표시)
* Dr.Dart-Platform: {plat}
* 제어기: 가상 제어기 dev-simulator (M1013)
* 실행: {started} (결과 폴더 results/{run})
* 입력 방식: {data.get('mode') or 'background (UIA)'}

h3. 항목
* {tc} {r['title']}
* 확인 내용: {r['desc']}

h3. 실패 내용
{tries}
""" + (f"""
h3. 실행 중 새로 찍힌 앱 로그 에러
{{noformat}}
{errs}
{{noformat}}
""" if errs else "") + ("""
h3. 첨부
""" + "\n".join(f"* {n} — {w}" for n, w in files) if files else "") + """

h3. 비고
자동화 판정 결과임. 백그라운드 입력(UIA)의 한계로 생긴 실패일 수 있으니 첨부 화면에서 실제 화면 상태를 확인할 것.
"""
    return {"summary": summary, "description": desc, "files": [{"name": n, "what": w} for n, w in files],
            "registered": registered(run).get(tc), "open_issues": search_open(tc),
            "project": load_cfg().get("project"), "issuetype": load_cfg().get("issuetype_name")}


def search_open(tc):
    """같은 항목으로 이미 열려 있는 이슈 (라벨 기준). 실패해도 등록은 막지 않음."""
    if not configured():
        return []
    c = load_cfg()
    jql = f'project = "{c["project"]}" AND labels = "smoke-{tc}" AND statusCategory != Done ORDER BY created DESC'
    try:
        j = _req("GET", "/rest/api/2/search?" + urllib.parse.urlencode({"jql": jql, "fields": "summary,status", "maxResults": 5}))
    except JiraError:
        return []
    return [{"key": i["key"], "summary": i["fields"]["summary"], "status": i["fields"]["status"]["name"],
             "url": f'{c["site"].rstrip("/")}/browse/{i["key"]}'} for i in j.get("issues", [])]


def create(run, tc, summary, description, files):
    if not configured():
        raise JiraError("JIRA 설정이 없음 — jira_setup.bat을 먼저 실행하세요")
    d, _, r = _result(run, tc)
    allowed = {n for n, _ in attachments(d, r)}
    bad = [f for f in files if f not in allowed]
    if bad:
        raise JiraError(f"첨부할 수 없는 파일: {bad}")
    c = load_cfg()
    fields = {"project": {"key": c["project"]}, "issuetype": {"id": c["issuetype_id"]},
              "summary": summary.strip()[:250], "description": description,
              "labels": [LABEL, f"smoke-{tc}"], **c.get("extra_fields", {})}
    try:
        res = _req("POST", "/rest/api/2/issue", {"fields": fields})
    except JiraError as e:
        if "labels" in getattr(e, "fields", {}):  # 생성 화면에 라벨 필드가 없는 프로젝트
            fields.pop("labels")
            res = _req("POST", "/rest/api/2/issue", {"fields": fields})
        else:
            raise
    key = res["key"]
    failed = []
    for f in files:
        try:
            body, h = _multipart(d / f)
            _req("POST", f"/rest/api/2/issue/{key}/attachments", data=body, headers=h)
        except JiraError as e:
            failed.append(f"{f} ({e})")
    url = f'{c["site"].rstrip("/")}/browse/{key}'
    reg = registered(run)
    reg[tc] = {"key": key, "url": url, "files": [f for f in files if not any(x.startswith(f) for x in failed)]}
    (d / "jira.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"key": key, "url": url, "attach_failed": failed}


# ---------------------------------------------------------------- 처음 설정
def _ask(prompt, default=None):
    v = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return v or default


def setup():
    import getpass
    c = load_cfg()
    print("PalletizOS 스모크 → JIRA 이슈 등록 설정 (API 토큰은 Windows 자격 증명에만 저장)")
    print("API 토큰 발급: https://id.atlassian.com/manage-profile/security/api-tokens\n")
    site = _ask("JIRA 주소 (예: https://회사.atlassian.net)", c.get("site"))
    old = secret.read(TARGET)
    email = _ask("Atlassian 로그인 이메일", old[0] if old else None)
    token = getpass.getpass("API 토큰 (화면에 안 보임, 엔터 = 저장된 값 유지): ") or (old[1] if old else "")
    if not (site and email and token):
        sys.exit("주소·이메일·토큰이 모두 필요합니다")
    secret.save(token, user=email, target=TARGET, comment="PalletizOS 스모크 → JIRA API 토큰")
    me = _req("GET", "/rest/api/2/myself", site=site)
    print(f"  인증 확인: {me.get('displayName')} ({me.get('emailAddress')})")
    project = _ask("프로젝트 키", c.get("project", "TER")).upper()
    types = _req("GET", f"/rest/api/2/issue/createmeta/{project}/issuetypes", site=site).get("issueTypes") \
        or _req("GET", f"/rest/api/2/issue/createmeta/{project}/issuetypes", site=site).get("values", [])
    for i, t in enumerate(types, 1):
        print(f"  {i}. {t['name']}")
    guess = next((i for i, t in enumerate(types, 1) if t["name"].lower() in ("버그", "bug")), 1)
    it = types[int(_ask("이슈 유형 번호", str(guess))) - 1]
    meta = _req("GET", f"/rest/api/2/issue/createmeta/{project}/issuetypes/{it['id']}?maxResults=200", site=site)
    flds = meta.get("fields") or meta.get("values", [])
    extra, names = {}, {}
    for f in flds:
        fid = f.get("fieldId") or f.get("key")
        if not f.get("required") or fid in STD_FIELDS or f.get("hasDefaultValue"):
            continue
        print(f"\n필수 필드: {f['name']} ({fid})")
        av = f.get("allowedValues") or []
        arr = (f.get("schema") or {}).get("type") == "array"
        if av:
            for i, v in enumerate(av, 1):
                print(f"  {i}. {v.get('name') or v.get('value')}")
            v = av[int(_ask("번호", "1")) - 1]
            val = {"id": v["id"]}
            names[f["name"]] = v.get("name") or v.get("value")
        else:
            val = _ask("값")
            names[f["name"]] = val
        extra[fid] = [val] if arr else val
    c.update(site=site.rstrip("/"), project=project, issuetype_id=it["id"], issuetype_name=it["name"],
             extra_fields=extra, extra_names=names)
    CFG.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장 완료: {CFG.name} (프로젝트 {project} / {it['name']}" + (f", 필수 필드 {names}" if names else "") + ")")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "setup":
        setup()
    else:
        c = load_cfg()
        print("설정됨" if configured() else "설정 안 됨", "-", c.get("site"), c.get("project"), c.get("issuetype_name"))
        if configured():
            print("  인증:", _req("GET", "/rest/api/2/myself").get("displayName"))
