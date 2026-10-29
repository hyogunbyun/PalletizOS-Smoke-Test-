"""마지막 실행에서 새로 나온 로그 에러 서명을 기준 목록(baseline_errors.txt)에 추가한다."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from autotest.logcheck import BASELINE, load_baseline  # noqa: E402

hist = json.loads((ROOT / "results" / "history.json").read_text(encoding="utf-8"))
run = json.loads((ROOT / "results" / hist[-1]["dir"] / "result.json").read_text(encoding="utf-8"))
new = []
for r in run["results"]:
    for sig in r.get("new_errors", {}):
        if sig not in load_baseline() and sig not in new:
            new.append(sig)
if not new:
    print("추가할 새 서명이 없습니다.")
    sys.exit(0)
print(f"마지막 실행({run['started']})의 새 에러 서명 {len(new)}종:")
for s in new:
    print("  -", s)
if input("정상 소음으로 승인하고 기준 목록에 추가할까요? (y/N) ").strip().lower() == "y":
    with open(BASELINE, "a", encoding="utf-8") as f:
        f.write("\n".join(new) + "\n")
    print("추가했습니다:", BASELINE)
