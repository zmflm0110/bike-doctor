# 문서 목록

## 제출물
| 문서 | 내용 |
|---|---|
| [report.md](report.md) · [PDF](report.pdf) | 보고서 — 문제 · 아이디어 · 자료 · 방법 · 결과 · 실시간 · 서비스 · 한계 · 확장 |
| [slides.html](slides.html) · [PDF](slides.pdf) | 발표 10장 (브라우저로 열고 ←/→, F 전체 화면) |
| [slides.md](slides.md) | 발표에서 말할 거리 · 예상 질문 |
| [proposal.md](proposal.md) · [PDF](proposal.pdf) | 서울시설공단 제안서 초안 — 한 구에서 2주 시범 |
| [demo/demo.mp4](demo/demo.mp4) | 시연 영상 (1분 39초, 자막 — 2026-09-27 새로 찍음) |
| [shots/](shots) · [img/site.png](img/site.png) | 앱 화면 사진 · 웹사이트 화면 |

## 결과 표 (스크립트가 자동으로 만듦)
| 문서 | 무엇을 쟀나 | 만드는 스크립트 |
|---|---|---|
| [results.md](results.md) | 앞선 포기 인원 → 다음 사람 포기, 도시·달별 핵심 표 | `analysis/report.py` |
| [phase1.md](phase1.md) | 헛대여 기준·경보 규칙을 1월로 고르고 다른 달·도시에 시험 | `analysis/phase1_rules.py` |
| [per_alarm.md](per_alarm.md) | 경보 한 건마다 다음 사람 기준 정밀도 (실시간 채점과 같은 방식) | `analysis/per_alarm.py` |
| [phase2.md](phase2.md) · [phase2_nextday.md](phase2_nextday.md) | 실시간 대여소 대수로 되나(안 됨) · 하루 늦은 자전거별 목록 | `analysis/phase2_*.py` |
| [api_parity.md](api_parity.md) | 실시간 대여이력 API 와 월별 파일이 같은 자료인가 (같음) | `analysis/api_parity.py` |
| [ev_validation.md](ev_validation.md) | 전기차 충전기 헛충전 중간 검증 — 기록 품질 거르기, 연쇄 뒤 다음 충전 | `analysis/ev_validate.py` |
| [outreach.md](outreach.md) | 이야기와 실제 반응 모으기 — 이용자 설문·정비 쪽 인터뷰·공단 문의 초안 | — |
| [phase3_rehearsal.md](phase3_rehearsal.md) | 매일 아침 작업 7일 연속 예행연습 | `server/rehearse.py` |
| [no_who.md](no_who.md) | 생년·성별 없이 같은 사람 거르기 (반납 2분 안 재대여) | `analysis/no_who.py` |
| [fault_kind.md](fault_kind.md) · [fault_kind_per_bike.md](fault_kind_per_bike.md) | 헛대여 모양으로 고장 종류 짐작 — 평균은 갈리지만 한 대씩은 10~14% | `analysis/fault_kind*.py` |
| [fig_chain.png](fig_chain.png) | 핵심 그림 | `analysis/figures.py` |

## 절차
| 문서 | 내용 |
|---|---|
| [field_protocol.md](field_protocol.md) | 현장 조사 2주 절차 — 무엇을 보고 어떻게 기록하나, 그날 바로 대조하는 법 |

## 초안 기록
| 문서 | 내용 |
|---|---|
| [evidence.md](evidence.md) | 규칙을 확정하기 **전** 탐색 기록 (당시 기준 2분·200m) — 숫자는 확정 결과와 다름 |
