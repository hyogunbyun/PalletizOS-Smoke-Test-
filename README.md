# PalletizOS 스모크 자동화 — 설치·실행 안내

Dr.Dart-Platform의 PalletizOS 모듈을 **가상 제어기**에서 자동으로 점검하는 프로그램입니다.
새 빌드를 설치한 뒤 42개 항목(기본 30 + 전체 클릭 8 + 녹화 4)을 사람 손 없이 확인하고 HTML 리포트를 만듭니다.
상세 사용법은 `MANUAL.md`.

## 1. 준비물 (이 PC에 있어야 함)
| 항목 | 비고 |
|---|---|
| Windows 10/11 | |
| **Dr.Dart-Platform 3.7.0** | `C:\Dr.Dart-Platform`에 설치 (PalletizOS 모듈 포함) |
| **Rancher Desktop**(Docker) + 가상 제어기 이미지 `dev-simulator:sdk7` | 시뮬레이터는 자동으로 만들고 켭니다 (`elements.yaml` simulator) |
| **Python 3.12** | python.org 설치본 |
| PalletizOS **Admin 비밀번호** | Recipe·Log·Settings 항목에 필요 |

## 2. 처음 한 번
1. 소스 받기 (경로에 한글·공백이 없으면 가장 안전):
   `git clone https://github.com/hyogunbyun/PalletizOS-Smoke-Test-.git`
   (저장소가 Private 이라 소유자가 GitHub에서 공동작업자로 초대해야 받을 수 있음)
2. **`setup.bat`** 더블클릭 → Python 환경(.venv) 생성·패키지 설치·바탕화면 실행 아이콘 3개 생성.
3. Admin 비밀번호 저장(한 번만, Windows 자격 증명에만 저장):
   `.venv\Scripts\python.exe -m autotest.secret set`
   (또는 첫 실행 때 콘솔에서 물어보면 입력 → 성공하면 자동 저장)

## 3. 실행
- 실행하면 먼저 **신규 버전 확인 팝업**이 뜹니다: GitHub 최신 릴리스와 설치된 버전을 비교해 최신이면 3초 뒤 평가 시작, **새 버전이면 묻지 않고 자동 설치**(다운로드 → 앱 재시작·연결 → Install from File, 약 2분, 진행 단계가 팝업에 표시) 후 그 버전으로 평가. 토큰이 없거나 설치에 실패하면 이유를 보여 주고 지금 버전으로 평가
- 바탕화면 **`PalletizOS_smoke.bat`** → 설치한 버전 입력(엔터=생략) → 무인 진행(약 75분) → 끝나면 리포트가 브라우저로 열리고 콘솔은 15초 뒤 닫힘
- 실행 중 앱 오른쪽 위 **상태 표시창**: 칩 색 = 항목 결과, 칩 두 번 = 그 항목만 다시 실행, ■ 종료(0.6~3초 사이 두 번)
- 실행 중 다른 업무 가능(마우스를 쓰지 않음). 단 **Dr.Dart 앱 창 최소화·직접 조작 금지**
- 결과: `results\<날짜_시각>\report.html`, 사건 기록 `results\events.log`

## 4. 선택 기능
| 기능 | 처음 한 번 | 사용 |
|---|---|---|
| FAIL → **JIRA 이슈 등록** (TER/버그) | `jira_setup.bat` (JIRA 주소·이메일·API 토큰) | 리포트 FAIL 행의 '이슈 등록' |
| **데일리 빌드 자동 설치·평가** (GitHub `dsg-robotics/palletizingsolution`) | `github_setup.bat` (저장소 읽기 전용 토큰) | `watch_start.bat` → 30분마다 새 빌드 확인 → 설치 → 스모크. 지금 한 번: `watch_check_now.bat`, 중지: `watch_stop.bat`. 로그온 때 자동 시작하려면 시작프로그램에 `pythonw.exe -m autotest.watcher`(작업 폴더 = 이 폴더) 바로가기 추가 |
| 시나리오 녹화·관리 | — | `record.bat`, `scenarios.bat` |

토큰·비밀번호는 모두 **Windows 자격 증명**(`PalletizOS-Smoke-Admin` / `-Jira` / `-GitHub`)에만 저장됩니다. 파일에 적지 마세요.

## 5. 반드시 지킬 것
- **가상 제어기에서만** 실행 (실제 로봇 연결 금지 — Enable·홈 이동·IO 출력을 실제로 누름)
- "Safety zone error" 배너는 판정에서 제외됨 (시뮬레이터 설정 탓)
- 실행 중 멈춤·앱 재시작이 생기면 먼저 `results\events.log`에서 원인 확인 (표시창 버튼·콘솔 닫힘·복구 실패가 모두 기록됨)

## 6. 폴더 구성
| 경로 | 내용 |
|---|---|
| `run_smoke.py`, `autotest\` | 실행기와 자동화 코드 |
| `elements.yaml` | 화면 문구·속도·전체 클릭 차단 목록·감시 주기 등 설정 |
| `scenarios\` | 녹화 시나리오 (C01~C04 중 C01·C02·C04는 v2.0.0 화면에 맞게 재녹화 필요) |
| `tools\` | 화면 조사·QA 점검(`qa_static.py`)·QA 리포트(`qa_report.py`) |
| `judgment_doc\` · `video\` | 소개 자료(PDF·HTML)·판정 기준 문서와 소개 영상 생성 스크립트 |
| `results\` | 실행 결과 (처음엔 비어 있음) |
| `MANUAL.md` / `DESIGN.md` | 상세 사용법 / 설계 결정과 근거 |

문의: QVE hyogun.byun
