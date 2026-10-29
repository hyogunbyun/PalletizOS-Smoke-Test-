"""이슈 등록 서버 (이 PC 전용 127.0.0.1:8781). 리포트 페이지의 '이슈 등록' 버튼이 여기를 거쳐 JIRA에 등록한다.

브라우저의 리포트(HTML)는 JIRA를 직접 부를 수 없어서(인증·교차 출처) 이 서버가 대신 호출한다.
- GET  /results/...                 결과 폴더 파일 (리포트·스크린샷) — 리포트는 반드시 이 주소로 열어야 버튼이 동작
- GET  /api/status                  JIRA 설정 여부
- GET  /api/registered?run=          이 실행에서 이미 등록한 이슈
- GET  /api/preview?run=&tc=         이슈 초안(제목·설명·첨부 목록)·같은 항목의 열린 이슈
- POST /api/create {run,tc,summary,description,files}
아무 요청 없이 3시간 지나면 스스로 종료한다. 실행: pythonw -m autotest.issue_server
"""
import json
import mimetypes
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import jira

PORT = 8781
IDLE_EXIT = 3 * 3600
_last = [time.time()]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _origin_ok(self):
        # 이 서버가 내준 리포트 페이지에서 온 요청만 허용. 'null'(파일로 연 페이지·샌드박스 iframe)도 거부 →
        # 아무 웹페이지가 몰래 이슈를 만들 수 없게. 리포트는 러너가 http://127.0.0.1:8781/results/... 로 연다
        o = self.headers.get("Origin")
        return o in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        o = self.headers.get("Origin")
        if o and self._origin_ok():
            self.send_header("Access-Control-Allow-Origin", o)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204 if self._origin_ok() else 403)
        if self._origin_ok():
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        _last[0] = time.time()
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path.startswith("/results/"):
                return self._file(urllib.parse.unquote(u.path[len("/results/"):]))
            if not self._origin_ok():
                return self._send(403, {"error": "허용되지 않은 출처"})
            if u.path == "/api/status":
                c = jira.load_cfg()
                return self._send(200, {"configured": jira.configured(), "project": c.get("project"),
                                        "issuetype": c.get("issuetype_name"), "site": c.get("site")})
            if u.path == "/api/registered":
                return self._send(200, jira.registered(q.get("run")))
            if u.path == "/api/preview":
                jira._run_dir(q.get("run"))  # 실행 폴더 이름 검사 먼저 (설정 여부와 관계없이 잘못된 입력은 400)
                if not jira.configured():  # 설정이 없으면 안내 문구 대신 설정 창을 바로 띄움 (2026-10-22 사용자 요청)
                    return self._send(200, {"configured": False, "setup_opened": open_setup()})
                return self._send(200, {"configured": True, **jira.preview(q.get("run"), q.get("tc"))})
            self._send(404, {"error": "없음"})
        except jira.JiraError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        _last[0] = time.time()
        if not self._origin_ok():
            return self._send(403, {"error": "허용되지 않은 출처"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            b = json.loads(self.rfile.read(n).decode("utf-8"))
            if urllib.parse.urlparse(self.path).path != "/api/create":
                return self._send(404, {"error": "없음"})
            if not (b.get("summary") or "").strip():
                return self._send(400, {"error": "제목이 비어 있음"})
            self._send(200, jira.create(b.get("run"), b.get("tc"), b["summary"], b.get("description", ""), b.get("files", [])))
        except jira.JiraError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def _file(self, rel):
        base = jira.RESULTS.resolve()
        p = (base / rel).resolve()
        if base not in p.parents or not p.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or p.suffix in (".html", ".txt", ".json"):
            ctype = (ctype if ctype != "application/octet-stream" else "text/plain") + "; charset=utf-8"
        self._send(200, p.read_bytes(), ctype)


_setup_at = [0.0]


def open_setup():
    """jira_setup.bat을 새 콘솔 창으로 연다 (60초 안에 여러 번 눌러도 한 번만). 열었으면 True."""
    import subprocess
    if time.time() - _setup_at[0] < 60:
        return True
    _setup_at[0] = time.time()
    subprocess.Popen(["cmd", "/c", "start", "PalletizOS JIRA 설정", "cmd", "/c", str(jira.ROOT / "jira_setup.bat")],
                     cwd=str(jira.ROOT))
    return True


def running():
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_running():
    """없으면 창 없이 띄우고 최대 5초 기다림. 띄웠거나 이미 있으면 True."""
    if running():
        return True
    import subprocess
    import sys
    from pathlib import Path
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else exe), "-m", "autotest.issue_server"], cwd=str(jira.ROOT),
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    for _ in range(25):
        time.sleep(0.2)
        if running():
            return True
    return False


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)

    def idle():
        while time.time() - _last[0] < IDLE_EXIT:
            time.sleep(60)
        srv.shutdown()

    threading.Thread(target=idle, daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
