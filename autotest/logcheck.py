"""앱 로그 감시: 흐름 구간에 새로 찍힌 줄을 읽고, 기준 목록에 없는 에러 서명을 찾는다."""
import re
from datetime import date
from pathlib import Path

LOG_DIR = Path(r"C:\Dr.Dart-Platform\logs")
ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "baseline_errors.txt"


def signature(line):
    """[시각][error][DP] 이후 메시지에서 숫자를 지워 같은 종류의 에러를 하나로 묶는다."""
    m = re.sub(r"^\[[^\]]*\]\[error\s*\]\[\w+\]\s*", "", line.strip())
    m = re.sub(r"\d+", "#", m)
    return m[:140]


def load_baseline():
    if not BASELINE.exists():
        return set()
    return {l.strip() for l in BASELINE.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}


class LogWatcher:
    def __init__(self):
        self.pos = {}

    def _files(self):
        d = date.today().isoformat()
        return sorted(LOG_DIR.glob(f"{d}*.log"))

    def mark(self):
        self.pos = {f: f.stat().st_size for f in self._files()}

    def new_lines(self):
        out = []
        for f in self._files():
            start = self.pos.get(f, 0)
            with open(f, "rb") as fh:
                fh.seek(start)
                out += fh.read().decode("utf-8", "replace").splitlines()
        return out

    def all_lines(self):
        """오늘 로그 전체 (마지막 ModuleLog 대조용)."""
        out = []
        for f in self._files():
            out += f.read_bytes().decode("utf-8", "replace").splitlines()
        return out

    def saw(self, pattern):
        rx = re.compile(pattern)
        return any(rx.search(l) for l in self.new_lines())

    def new_errors(self):
        """기준 목록에 없는 에러 서명 → {서명: 첫 원문 줄}"""
        base = load_baseline()
        found = {}
        for l in self.new_lines():
            if "][error" in l:
                sig = signature(l)
                if sig not in base and sig not in found:
                    found[sig] = l.strip()[:300]
        return found
