# 헛걸음 제로 — 따릉이 고장 예보

사람들이 귀찮아서 안 하는 고장 신고를, 공개 대여기록 속 "빌리자마자 반납" 의 연쇄가 대신한다.
서로 다른 두 사람이 연달아 3분 안에 반납한 자전거는 다음 사람도 약 35~44% 가 포기한다(평소 2.5%). 서울 3개월·대전 2개월, 약 1천만 건으로 검증.

- 보고서 초안: [`docs/report.md`](docs/report.md) · 핵심 표: [`docs/results.md`](docs/results.md) · 계획·진행: [`PLAN.md`](PLAN.md)

## 바로 해 보기
```sh
python3 -m venv .venv && .venv/bin/pip install pandas numpy openpyxl matplotlib tabulate pytest
.venv/bin/python data/download.py          # 원본 자료 (인증키 불필요, 약 1.7GB)
.venv/bin/python analysis/report.py        # 핵심 표 → docs/results.md
.venv/bin/python analysis/export_web.py    # 앱 데이터 → web/data/
.venv/bin/python server/app.py             # http://localhost:8765 (웹앱 + 구조대·현장조사 API)
.venv/bin/python server/rehearse.py       # 매일 아침 작업을 과거 파일로 7일 연속 예행연습 → docs/phase3_rehearsal.md
.venv/bin/python -m pytest -q tests        # 테스트
```

## 구성
| 폴더 | 내용 |
|---|---|
| `engine/` | 헛대여·연쇄·경보 규칙(`core.py`), 아침 목록(`morning.py`) |
| `analysis/` | 검증: Phase 1 기준 선택, Phase 2 실시간 가능성, 현장 검증, 그림 |
| `server/` | 서울 API(키체인), 매일 아침 목록 작업(목록 기록·다음 날 채점 SQLite)·예행연습, 웹 서버(구조대·현장조사 SQLite) |
| `web/` | 웹앱 — 아침 목록·자전거 조회(QR)·구조대·시연·현장 조사 (홈 화면 추가 가능) |
| `docs/` | 결과·보고서·현장 조사 절차 |

## 인증키 (선택)
코드·git 에 넣지 않고 macOS 키체인에:
```sh
security add-generic-password -a bike-doctor -s seoul-openapi -w '<서울 열린데이터광장 키>'
security add-generic-password -a bike-doctor -s datagokr -w '<공공데이터포털 키>'
```
