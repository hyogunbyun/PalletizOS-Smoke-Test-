"""GitHub 릴리스 확인·다운로드 (비공개 저장소 dsg-robotics/palletizingsolution).

인증: 개인 토큰(PAT, 이 저장소 Contents: Read) → Windows 자격 증명 'PalletizOS-Smoke-GitHub' (파일·로그에 남기지 않음)
명령줄: python -m autotest.github setup | check | download <태그>
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import secret

REPO = "dsg-robotics/palletizingsolution"
TARGET = "PalletizOS-Smoke-GitHub"
ROOT = Path(__file__).resolve().parent.parent
DL_DIR = ROOT / "releases"  # 받은 설치 파일 (버전별 폴더)


class GitHubError(Exception):
    pass


def _token():
    r = secret.read(TARGET)
    if not r:
        raise GitHubError("GitHub 토큰이 없음 — github_setup.bat을 먼저 실행하세요")
    return r[1]


def _req(url, accept="application/vnd.github+json", token=None, raw=False):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token or _token()}", "Accept": accept,
                                               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "palletizos-smoke"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
            return data if raw else json.loads(data)
    except urllib.error.HTTPError as e:
        msg = {401: "토큰이 틀렸거나 만료됨", 403: "권한 없음(토큰 권한·SSO 승인 확인)", 404: "저장소/릴리스를 찾을 수 없음(토큰에 이 저장소 권한 필요)"}
        raise GitHubError(f"GitHub {e.code}: {msg.get(e.code, e.reason)}")
    except urllib.error.URLError as e:
        raise GitHubError(f"GitHub 접속 실패: {e.reason}")


def releases(n=10, token=None):
    """최근 릴리스 [{tag, name, published, prerelease, assets:[{name,size,url}]}] (최신 먼저)."""
    js = _req(f"https://api.github.com/repos/{REPO}/releases?per_page={n}", token=token)
    out = []
    for r in js:
        if r.get("draft"):
            continue
        out.append({"tag": r["tag_name"], "name": r.get("name") or r["tag_name"], "published": r.get("published_at"),
                    "prerelease": r.get("prerelease"), "id": r["id"],
                    "assets": [{"name": a["name"], "size": a["size"], "url": a["url"]} for a in r.get("assets", [])]})
    return out


def download(rel, pick=None):
    """릴리스의 첨부 파일을 releases/<태그>/에 받는다. pick(name)->bool로 고를 수 있음. 받은 파일 경로 목록."""
    d = DL_DIR / rel["tag"]
    d.mkdir(parents=True, exist_ok=True)
    got = []
    for a in rel["assets"]:
        if pick and not pick(a["name"]):
            continue
        p = d / a["name"]
        if p.exists() and p.stat().st_size == a["size"]:
            got.append(p)
            continue
        data = _req(a["url"], accept="application/octet-stream", raw=True)
        p.write_bytes(data)
        got.append(p)
    return got


def setup():
    import getpass
    print("PalletizOS 데일리 빌드 감시 → GitHub 토큰 설정 (Windows 자격 증명에만 저장)")
    print(f"저장소: {REPO}")
    print("토큰 만들기: https://github.com/settings/personal-access-tokens/new")
    print("  - Repository access: Only select repositories → palletizingsolution")
    print("  - Permissions: Contents = Read-only (Metadata는 자동)")
    print("  - 회사 조직(SSO)이면 토큰 목록에서 'Configure SSO' → dsg-robotics 승인\n")
    tok = getpass.getpass("토큰 붙여넣기 (화면에 안 보임): ").strip()
    if not tok:
        sys.exit("토큰이 비어 있습니다")
    rs = releases(3, token=tok)  # 저장 전에 실제로 읽히는지 확인
    secret.save(tok, user="github", target=TARGET, comment="PalletizOS 스모크 → GitHub 릴리스 읽기 토큰")
    print(f"저장 완료. 최근 릴리스 {len(rs)}개 확인:")
    for r in rs:
        print(f"  {r['tag']}  {r['published']}  첨부 {len(r['assets'])}개")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    try:
        if cmd == "setup":
            setup()
        elif cmd == "download":
            rel = next(r for r in releases(30) if r["tag"] == sys.argv[2])
            for p in download(rel):
                print(p)
        else:
            for r in releases(5):
                print(f"{r['tag']}  {r['published']}  {'(pre)' if r['prerelease'] else ''}  {r['name']}")
                for a in r["assets"]:
                    print(f"    - {a['name']}  {a['size'] / 1e6:.1f} MB")
    except GitHubError as e:
        sys.exit(str(e))
