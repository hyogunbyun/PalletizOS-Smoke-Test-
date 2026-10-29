# PalletizOS Home 스모크 자동화 — 설계 결정 (2026-10-19)

## 대상·환경
- 대상: Dr.Dart-Platform 3.7.0 안의 **PalletizOS v1.1.0 Home 화면에 보이는 컨트롤만** 평가
- 제어기: 이 PC의 Docker 시뮬레이터 `dev-simulator` (dev-simulator:sdk7, Rancher Desktop WSL), `127.0.0.1`, M1013, GF03070000
- 조작: pywinauto UIA (앱이 `--remote-debugging-port`를 막아 두어서 CDP/Playwright는 쓰지 않음). 트리는 두 번째 조회부터 노출되므로 시작할 때 미리 한 번 조회
- 앱 실행: VS Code 셸에서 물려받는 `ELECTRON_RUN_AS_NODE`를 cmd에서 삭제한 뒤 실행
- UI 언어: **English 고정**. 시작할 때 다른 언어면 "환경 오류"로 중단
- 입력: **실제 마우스·키보드**. 창 크기·위치 고정(1618×1020), 실행 중 표시 띄움, 실행 중 사용자가 마우스를 움직이면 "환경 오류"

## 스모크 흐름 (9개) — 구현 기준
| # | 흐름 | 판정 (출발 값 기준 상대 변화) |
|---|---|---|
| P01 | 화면 진입 | 버전 표시(기대 버전 입력 시 일치), Home 핵심 요소 존재 |
| P02 | Left/Right 토글 | 켜면 레시피 활성·진행률 표시, 끄면 비활성·'-', 원복 |
| P03 | 레시피 선택 | Cancel 시 유지 → 다른 정상 레시피 Apply 시 표시 변경·N=0 → 원래 레시피 복귀 |
| P04 | Current Layer +/− | [+]를 끝까지 / [−]를 끝까지, 매 단계 N 모델·진행률·버튼 활성 일치 |
| P05 | Boxes on Layer +/− | N±1, 층 경계에서 다음 층 1개로 넘어감, 진행률 일치 |
| P06 | 속도 드롭다운 | 최대화 레이아웃에는 없음 → 해당없음 |
| P07 | Enable/Disable Robot | 버튼 이름·상태 문구 전환, Servo ON/OFF 로그, 원복 |
| P09 | Release Vacuum·홈 이동 | 로그(Release vacuum / Move home), 45초 안에 이동 완료, 에러 문구 없음 |
| P10 | 좌측 메뉴 이동 | 역할별 메뉴 각각 열고 Home 복귀 후 화면 값 동일 |

제외: P08(배너가 있을 때 Test Run이 막히는지), Test Run 실행, Jog, 다른 모듈 화면.
**"Safety zone error"는 무시**한다(판정과 팝업 검사 모두 대상 아님). 원인은 시뮬레이터 안전 설정에 "Reduced Collab" 영역이 빠진 것.

## 상태 관리
- 재시작하지 않는다. 시작할 때 화면 값을 스냅샷으로 저장 → 흐름마다 원래 값으로 복구 → 마지막에 스냅샷과 비교
- 복구에 실패하거나 앱이 죽은 경우에만 앱을 재시작하고 PalletizOS에 다시 진입한 뒤 남은 흐름을 진행
- PalletizOS가 떠 있지 않으면 러너가 하단 독에서 연다

## 버전
- 기본: 화면 버전(PalletizOS)과 Dr.Dart-Platform 설치 버전을 자동 기록. 지난 실행과 같으면 "버전 변경 없음" 경고
- 선택: 실행할 때 기대 버전을 입력하면 P01에서 일치 여부를 판정

## 판정
- 실패하면 스크린샷과 UI 트리를 저장하고, 복구한 뒤 1회 재시도. 재시도에서 통과하면 노랑(불안정), 두 번 다 실패하면 빨강
- 앱 로그: 숫자를 지운 에러 서명이 기준 목록에 없으면 해당 흐름을 노랑으로 표시하고 로그 줄을 첨부. 리포트에서 승인하면 기준 목록에 추가
  - 초기 기준 목록: changeNote GET 실패, send_delete_package, Modbus Recipe_Name Not connected, Login failed, get_industrial_ethernet_config, SwiftMoveTcpClient ECONNREFUSED
- 최종: 빨강이 1개라도 있으면 **보류** / 노랑만 있으면 **통과(주의)** / 전부 초록이면 **통과**

## 구현 중 확정된 사항 (2026-10-19 실측)
- **진행 상태 모델**: 층/박스/진행률은 '완료 박스 총개수 N' 하나로 설명된다. N=(층-1)×층당박스+현재층박스, 진행률=round(100N/전체). 층 [+]/[−]는 다음/이전 층 경계로, 박스 [+]/[−]는 N±1, [−]는 N=0에서만, [+]는 N=전체에서만 비활성 → P04·P05의 판정 기준
- 토글을 껐다 켜거나 레시피를 바꾸면 N=0으로 초기화됨 → 복구는 토글·레시피를 되돌린 뒤 `set_n()`으로 N을 원래 값으로 맞춤
- 레시피를 바꾸면 **꺼져 있는 반대쪽 열의 레시피 표시도 같이 바뀜** (공유 설계인지 결함인지 미확인)
- 레시피 목록의 빨간 오류 아이콘은 UIA에 노출되지 않음 → 픽셀(빨강)로 판별해 P03 후보에서 제외
- Enable Robot → 버튼 'Disable Robot', 상태 'System Not Running', ModuleLog `Servo ON`(11.0505). Release vacuum(11.0509)·Move home(11.0506)·Servo OFF(11.0510)도 로그로 판정
- P07은 출발 상태와 무관하게 Enable↔Disable을 두 번 전환(이름도 'Enable/Disable Robot'으로 변경), P09는 필요할 때만 Enable했다가 원복
- P10: 메뉴는 역할별로 다름(Operator: IO·Jog +, Admin: Recipes·IO·Log·Settings·Jog +·Quick Log). IO는 페이지형, Jog +는 떠 있는 패널(X로 닫음)
- P06: 창을 최대화한 레이아웃에는 PalletizOS 속도 컨트롤이 없어 **해당없음**(작은 창에서만 3D 뷰 + 100% 드롭다운)
- **클릭 안전장치**: PalletizOS 뒤에 깔린 Platform 층(DOM 앞쪽 형제)의 요소는 클릭 거부. 실제 사고: 가려진 투어 'Skip'을 누르자 위의 'Enable Robot'이 눌림. Chromium `ElementFromPoint`는 바깥 Document를 돌려줘 가림 판정에 못 씀
- 콜드 스타트 경로: 앱 실행 → 연결 화면(**한국어**, 연결 전은 PC 언어) → 제어권 이전 '강제 회수' → Home 모듈 → PalletizOS 타일 → 로그인(Operator, 비밀번호 없음) → Home
- 한 번 전체 실행에 약 3분

## 변경 (2026-10-19 오후)
- **범위 확장 9 → 30개**: "모든 메뉴" 요청. Home 8(H01~H08) + Recipes 5 + IO 4 + Log 5 + Settings 5 + Jog + 1 + Quick Log 1 + Recovery 1. 기존 P10(메뉴 왕복)은 메뉴별 항목으로 대체, P06(속도)은 실제로는 **3D 뷰 확대**라 H06으로 바꿈
- **Admin 필요**: Recipes·Log·Settings는 Admin에게만 보임. 비밀번호는 실행 때 입력(getpass), 저장 금지. 끝나면 시작 계정으로 원복
- **Q12 번복 → 백그라운드 방식**: 실행 중 PC를 쓸 수 있어야 한다는 요구. UIA Invoke/Toggle/Select(요소→부모 순, 기본 동작은 마지막), 입력은 ValuePattern, ESC는 PostMessage, 캡처는 PrintWindow. 실제 마우스는 `--mode mouse`. 한계: "가려져서 안 눌림" 결함은 못 잡음
- **속도**: 고정 대기에 `speed` 배수(기본 3.0), 상태 확인 간격 0.1초, 클릭마다 층 부모 탐색 캐시
- 메뉴 화면 실측: Settings에서 좌측 메뉴가 아이콘으로 접힘(이름 없음) → 펼친 상태에서 기억한 순서로 아이콘 선택. 레시피 편집기·Recovery는 별도 전체 화면 층. Digital Output 표는 좌우 2열이라 행 해석 시 오른쪽 열 'Port #' 앞까지만
- 누르지 않는 버튼: Delete, Import, Export, Initialize System, Install New Version, Get Pose/Move To, Open TeamViewer, Test Run, Clear, Save

## 구성
- `elements.yaml`: 화면 요소 이름(영어) 한곳에서 관리
- `flows/*.py`: 흐름 하나 = 함수 하나, TC 번호와 한글 설명 포함
- 실행: 바탕화면 .bat 더블클릭(CRLF, 예약작업 없음) → 끝나면 HTML 리포트를 브라우저로 자동 열기(메일 없음). 리포트에 최근 실행 이력 포함
