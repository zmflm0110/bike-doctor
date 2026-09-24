# 헛걸음 제로 — 따릉이 고장 예보

사람들이 귀찮아서 안 하는 고장 신고를, 공개 대여기록 속 "빌리자마자 반납" 의 연쇄가 대신한다.
서로 다른 두 사람이 연달아 3분 안에 같은 대여소에 반납한 자전거는 다음 사람도 35~44% 가 포기한다(평소 2.5%, 약 14배).
서울 3개월·대전 2개월, 약 1천만 건으로 검증.

- 보고서 초안: [`docs/report.md`](docs/report.md) ([PDF](docs/report.pdf)) · 핵심 표: [`docs/results.md`](docs/results.md) · 계획·진행 기록: [`PLAN.md`](PLAN.md)
- 발표: [`docs/slides.html`](docs/slides.html) (브라우저로 열고 ←/→, F 전체 화면, [PDF](docs/slides.pdf)) · 말할 거리·예상 질문: [`docs/slides.md`](docs/slides.md)
- 시연 영상: [`docs/demo/demo.mp4`](docs/demo/demo.mp4) (1분 27초, 자막 포함) · 앱 화면: [`docs/shots/`](docs/shots)

## 핵심 결과
| | 결과 | 근거 |
|---|---|---|
| 앞선 포기 2명 → 다음 사람 포기 | 서울 35.3~37.1%, 대전 41.6~43.6% (평소 2.5~2.9%) | [`docs/results.md`](docs/results.md) |
| 경보 규칙 | 1월로만 정하고(3분·300m·서로 다른 사람 2연속) 3·6월·대전에 그대로 → 정밀도 51.8~60.2% (기준 달과 ±2.3%p), 3연속이면 약 70% | [`docs/phase1.md`](docs/phase1.md) |
| 신고보다 빠름 | 경보 → 고장 신고 중앙값 20~25시간, 그 사이 한 자전거에서 평균 3.5~4.6명 헛걸음 | 보고서 5-3 |
| 신고 안 되는 고장 | 서로 다른 사람의 연속 헛대여 중 49~61% 는 7일이 지나도 신고 없음 | 보고서 5-3 |
| 막을 수 있던 헛걸음 | 서울 하루 90~243명, 대전 하루 114~132명 | 보고서 5-2 |
| 실시간 공개 자료로는? | 대여소 대수만 있어 경보 정밀도 ≤1.7% → **하루 늦은 자전거별 "아침 목록"** 으로 전환 | [`docs/phase2.md`](docs/phase2.md) |
| 아침 목록 예행연습 | 운영 코드 그대로 7일 연속: 한 달 전체 목록과 99.6% 일치, 목록 자전거 첫 이용자 42.3% 헛걸음 | [`docs/phase3_rehearsal.md`](docs/phase3_rehearsal.md) |
| 생년·성별 없는 자료 | "반납 2분 안 재대여 = 같은 사람" 으로 대신 → 정밀도 차 ≤0.2%p | [`docs/no_who.md`](docs/no_who.md) |

## 진행 상황 (2026-09-24)
| Phase | 상태 | 한 것 | 남은 것 |
|---|---|---|---|
| 0 정리 | ✅ 완료 | 엔진 모듈·테스트, 원본 자료 자동 내려받기(키 불필요), 명령 하나로 5개월 결과 재생성 | — |
| 1 엔진 확정 | ✅ 완료 | 1월 격자로 규칙 선택 → 다른 달·도시 시험 통과, 두 단계 경보(노랑·빨강) | — |
| 2 실시간 가능성 | ✅ 완료 (방향 전환) | 실시간 대수 재구성 시험 → 불가 판정, 아침 목록으로 전환 | — |
| 3 매일 아침 목록 서버 | 🟡 예행연습 완료 | 목록 기록·다음 날 채점(SQLite), 7일 연속 예행연습, 생년·성별 없는 경우 대비 | **공공데이터포털 인증키** → 실제 API 연결, 7일 실운영 |
| 4 웹앱 | 🟡 거의 | 아침 목록·자전거 조회(QR)·구조대·시연·현장 조사 5개 탭, 진짜 오프라인 시연 검사 통과, 집 와이파이 https | 아이폰 실기기 확인 |
| 5 현장 검증 | ⏳ 준비 완료 | 현장 조사 탭·서버 API·검증 스크립트·절차 문서 | 2주간 대여소 5곳+ 자전거 150대+ 조사, 친구 구조대 시범 |
| 6 넓히기 (전기차 충전기) | 🟡 뼈대 | 헛충전 연쇄 엔진·수집기·테스트 | 인증키로 1~2주 수집 → 검증 |
| 7 대회 패키지 | 🟡 거의 | 보고서(PDF), 발표 10장(HTML·PDF)·예상 질문, 시연 영상 자동 녹화 | 목표 대회 정해지면 형식 맞추기, 이름·학교, 현장 조사 결과 채우기 |

## 사람이 해야 하는 것
| 할 일 | 왜 |
|---|---|
| 서울 열린데이터광장·공공데이터포털 인증키 (무료·즉시) | 실시간 대여소 현황, 자전거별 일별 기록(Phase 3), 충전기 상태(Phase 6) |
| 목표 대회와 마감 | 보고서·영상·시연 형식 맞추기 |
| 현장 조사 2주 (앱 '현장 조사' 탭, [`docs/field_protocol.md`](docs/field_protocol.md)) | 사람이 본 고장 vs 엔진 → 실측 정밀도 |
| 아이폰에 로컬 인증서 설치 (1분, `sh server/https_local.sh` 안내) | 아이폰은 https 에서만 위치·QR 카메라 허용 |
| 친구 5~10명 구조대 시범 | "3초 확인" 이 실제로 되는지 |
| 작품 이름 확정 (현재 "헛걸음 제로") | 앱·발표 |

## 바로 해 보기
```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python data/download.py          # 원본 자료 (인증키 불필요, 약 1.7GB)
.venv/bin/python analysis/report.py        # 핵심 표 → docs/results.md
.venv/bin/python analysis/export_web.py    # 앱 데이터 → web/data/
.venv/bin/python server/app.py             # http://localhost:8765 (웹앱 + 구조대·현장조사 API)
sh server/https_local.sh && .venv/bin/python server/app.py 8443 --https   # 아이폰(같은 와이파이)에서 위치·QR — 안내가 나옴
.venv/bin/python server/rehearse.py       # 매일 아침 작업을 과거 파일로 7일 연속 예행연습 → docs/phase3_rehearsal.md
.venv/bin/python -m pytest -q tests        # 테스트
node tests/web/smoke.js                     # 웹앱 다섯 탭 휴대폰 화면 검사 (npm i playwright, 서버는 스스로 띄움)
PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS=1 node tests/web/offline.js evict   # 진짜 오프라인 시연 검사 (normal|evict|notiles)
```
GitHub 에 올리면 `.github/workflows/test.yml` 이 위 검사를 전부 돌린다(원본 자료·인증키 불필요).

제출물 다시 만들기 (`npm i playwright marked`):
```sh
SHOTS=docs/shots node tests/web/smoke.js     # 앱 화면 사진 (발표에 쓰임)
node tests/web/record_demo.js                # 시연 영상 → docs/demo/demo.webm·demo.mp4 (mp4 는 ffmpeg 필요, FFMPEG=경로)
node docs/build_pdf.js                       # docs/report.pdf, docs/slides.pdf
```
인터넷이 되는 곳에서 찍으면 지도 조각이 깔린다(안 되면 대여소 점 바탕).

## 구성
| 폴더 | 내용 |
|---|---|
| `engine/` | 헛대여·연쇄·경보 규칙(`core.py`), 아침 목록(`morning.py`) |
| `analysis/` | 검증: Phase 1 기준 선택, Phase 2 실시간 가능성, 현장 검증, 그림 |
| `server/` | 서울 API(키체인), 매일 아침 목록 작업(목록 기록·다음 날 채점 SQLite)·예행연습, 웹 서버(구조대·현장조사 SQLite) |
| `web/` | 웹앱 — 아침 목록·자전거 조회(QR)·구조대·시연·현장 조사 (홈 화면 추가 가능) |
| `docs/` | 결과·보고서·현장 조사 절차 |
| `tests/` | 엔진·서버·매일 작업·충전기 단위 테스트(pytest), 웹 화면 검사(`tests/web/smoke.js`)·오프라인 검사(`tests/web/offline.js`) |

## 인증키 (선택)
코드·git 에 넣지 않고 macOS 키체인에:
```sh
security add-generic-password -a bike-doctor -s seoul-openapi -w '<서울 열린데이터광장 키>'
security add-generic-password -a bike-doctor -s datagokr -w '<공공데이터포털 키>'
```

## 자료·라이선스
- 대여이력·고장신고·대여소: 서울 열린데이터광장(서울시설공단), 대전 타슈: 공공데이터포털. 원본은 저장소에 넣지 않고 `data/download.py` 로 받는다.
  `web/data/` 에는 가공한 결과(자전거 번호·대여소·시각)만 있고 이용자 정보(생년·성별)는 없다.
- 포함한 라이브러리: [Leaflet](https://leafletjs.com) 1.9.4 (BSD-2), [jsQR](https://github.com/cozmo/jsQR) 1.4.0 (Apache-2.0) — `web/vendor/` 에 라이선스 동봉. 지도 © OpenStreetMap 기여자.
