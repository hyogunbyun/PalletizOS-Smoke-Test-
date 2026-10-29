# dev-simulator(sdk7) 제어기 시작 실패 — 원인 확인 및 요청 사항

- 작성: 2026-10-20, hyogun.byun (QVE) · PalletizOS 스모크 자동화 환경에서 발견
- 대상 이미지: `2ldl9mume9.execute-api.ap-northeast-2.amazonaws.com/dsg-robotics/dev-simulator:sdk7` (ID `70d142b454cc`, 2026-09-07 빌드, `GV03070000_20260820_999`)
- 환경: Windows 11 (22631) · WSL 3.0.1.0 · 커널 6.18.40.1-microsoft-standard-WSL2 · Rancher Desktop 1.24.0 (moby 29.5.3, cgroup v2) · Intel Core Ultra 5 125H (18 스레드)

## 1. 증상
- 컨테이너 안의 DRCF가 시작 1초 만에 죽고, `start_services.sh` 감시 루프가 재시작을 반복함
  `drcf-restart.log`: `DRCF died with rc=139 after 1s - restart #N in 60s` (수십~100회 이상)
- VM 커널 기록: `DRCF[…]: segfault at 9 ip …f24 … error 4 in DRCF[29bf24, …]` — **매번 같은 오프셋**(재현되는 충돌)
- DRCF 자체 로그(`/home/dra/etc/logs/dart-suite/*`)는 모두 0바이트 — 로그를 남기기 전에 죽음
- 그런데 이미지 HEALTHCHECK(`pgrep -x DRCF`)는 재시작 사이 1초에 걸리면 **healthy로 표시**됨 (충돌 중인데 healthy)

## 2. 원인 (실험으로 확인)
**DRCF는 메모리 고정(mlock) 한도가 기본값(64MB, `ulimit -l` = 65536)이면 시작 직후 segfault로 죽는다.**
같은 이미지·같은 VM에서 옵션만 바꾼 컨테이너로 40초씩 비교:

| 컨테이너 옵션 (`-e ROBOT_MODEL=M1013` 공통) | DRCF | 충돌(rc=139) | 12345 LISTEN |
|---|---|---|---|
| 기본 | 없음 | 5~9회 | X |
| `--cpuset-cpus 0-3` (CPU 4개) | 없음 | 5회 | X |
| `--shm-size 1g --cpus 4 --memory 2g` | 없음 | 6회 | X |
| `--cap-add SYS_NICE` / `--ulimit rtprio=99` / 둘 다 | 없음 | 6회 | X |
| `--privileged` | 실행 | 0회 | — |
| **`--cap-add IPC_LOCK`** | **실행** | **0회** | **O** |
| **`--ulimit memlock=-1`** | **실행** | **0회** | **O** |

→ `IPC_LOCK` 권한 또는 `memlock` 무제한 둘 중 하나면 정상. 실시간 스케줄링 권한(SYS_NICE·rtprio)·CPU 수·공유메모리 크기와는 무관.
[추정] DRCF가 `mlockall()`(또는 큰 영역 mlock) 실패를 확인하지 않고 진행하다 NULL 근처(주소 9)를 읽고 죽는 것으로 보임.

## 3. 발생 경위
- 원래 컨테이너는 Dr.Dart 도구(docker-compose, 네트워크 `compose_default`)가 만든 것으로 10-19까지 정상 → 아마 compose에 memlock/권한 설정이 있었음
- 10-20 PC 재부팅 후 컨테이너·compose 네트워크가 사라지고 이미지만 남음 → 이미지로 직접 다시 만들면(`docker run`) 위 증상
- 함께 확인된 것: `ROBOT_MODEL` 환경변수가 없어도 같은 rc=139 반복, dockerd 재시작으로 꺼진 컨테이너는 다시 켜도 같은 증상

## 4. 현재 우회 (자동화 쪽 적용 완료)
```
docker run -dit --name dev-simulator --ulimit memlock=-1 -e ROBOT_MODEL=M1013 \
  -p 12345:12345 -p 12350:12350/udp -p 12360:12360/udp -p 3600:3600 -p 3601:3601 -p 502:502 <이미지>
```
→ 28초 만에 DRCF 안정(충돌 0), Windows에서 127.0.0.1:12345·3601 접속 확인

## 5. 요청 사항
1. **실행 가이드/compose에 `ulimits: memlock: -1`(또는 `cap_add: IPC_LOCK`) 명시** — 이미지만으로 다시 만드는 경우가 생김
2. **DRCF: mlock 실패 시 오류 메시지를 남기고 종료(또는 비고정으로 계속)** — 지금은 로그 없이 segfault라 원인 파악이 매우 어려움
3. **HEALTHCHECK 개선** — `pgrep`만으로는 충돌 반복 중에도 healthy. 예: DRCF 가동 시간 N초 이상 + 12345 LISTEN 확인
4. 재부팅 후 컨테이너가 사라진 이유(도구가 정리했는지) 확인 — Rancher Desktop 재시작마다 컨테이너가 Exited(255)되는 것은 별개로 관찰됨
