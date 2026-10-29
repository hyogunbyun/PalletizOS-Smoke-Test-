"""sw_coverage_methods 양식의 <style>을 가져와 body 파일과 합친다.
사용: python build.py [body파일 출력파일 제목]  (인수 없으면 판정기준 문서)"""
import re
import sys
from pathlib import Path
here = Path(__file__).parent
body_name, out_name, title = (sys.argv[1:4] if len(sys.argv) >= 4
                              else ("body.html", "판정기준.html", "PalletizOS 스모크 판정 기준"))
tpl = Path(r"D:\hyogun.byun\Desktop\log\sw_coverage_methods\sw_coverage_methods.html").read_text(encoding="utf-8")
style = re.search(r"<style>.*?</style>", tpl, re.S).group(0)
body = (here / body_name).read_text(encoding="utf-8")
html = f'<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="UTF-8">\n<title>{title}</title>\n{style}\n</head>\n<body>\n{body}\n</body>\n</html>\n'
(here / out_name).write_text(html, encoding="utf-8")
print("ok", out_name)
