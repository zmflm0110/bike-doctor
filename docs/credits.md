# 출처 (에셋·라이브러리·자료) — 대회 제출용 증명

대회 규칙: "에셋, 상용 엔진의 출처와 다운로드 받은 폴더를 함께 제출". 제출 zip 의 `출처/` 폴더에 아래 원본을 그대로 넣는다(`tools/make_submission.py`).
**상용 엔진은 쓰지 않았다.** 디자인 에셋(아이콘·색·화면)은 모두 직접 만들었다.

| 무엇 | 어디에 씀 | 라이선스 | 받은 곳 | zip 안 |
|---|---|---|---|---|
| Leaflet 1.9.4 | 웹앱·안드로이드 앱 지도 | BSD-2-Clause (무료, 상업 사용 가능) | https://leafletjs.com/download.html · https://github.com/Leaflet/Leaflet/releases/tag/v1.9.4 | `출처/leaflet-1.9.4/` |
| jsQR 1.4.0 | QR 읽기(자전거 번호) | Apache-2.0 | https://github.com/cozmo/jsQR · https://www.npmjs.com/package/jsqr | `출처/jsqr-1.4.0/` |
| Capacitor 8 | 웹앱을 안드로이드 앱(APK)으로 감쌈 | MIT | https://capacitorjs.com · https://www.npmjs.com/package/@capacitor/android | `출처/capacitor/` |
| OpenStreetMap 지도 그림 | 지도 바탕(인터넷으로 불러옴) | © OpenStreetMap 기여자, ODbL — 화면 오른쪽 아래에 표시 | https://www.openstreetmap.org/copyright | `출처/openstreetmap.txt` |
| Apple MapKit·SwiftUI | 아이폰 앱 지도·화면 (Xcode 에 들어 있는 기본 도구) | Apple SDK 라이선스 | Xcode 27 (Mac App Store) | `출처/apple.txt` |
| 서울 열린데이터광장 — 따릉이 대여이력(OA-15182, API tbCycleRentData), 고장신고(OA-15644), 대여소 정보 | 엔진·검증·실시간 | 공공누리 제1유형(출처 표시) | https://data.seoul.go.kr | `출처/공공데이터.txt` |
| 공공데이터포털 — 대전 타슈 대여이력, 한국환경공단 전기차 충전소 정보 | 다른 도시 검증, 충전기 넓히기 | 공공누리 제1유형 | https://www.data.go.kr | `출처/공공데이터.txt` |
| Supabase (DB + 5분마다 서울 API 받아 경보 계산·채점, pg_cron), GitHub Actions (백업·전기차 자료 모으기) | 클라우드 | 무료 요금제(서비스 이용) | https://supabase.com · https://github.com/features/actions | `출처/클라우드.txt` |

| Python pandas · NumPy · scikit-learn · matplotlib | 대여기록 분석, **자체 모델 학습**(그래디언트 부스팅) — 앱에는 들어가지 않고, 학습한 나무를 우리가 SQL 로 바꿔 DB 에 넣음 | BSD-3-Clause 등 (무료) | https://pypi.org | `4_소스/requirements.txt` |

**직접 만든 것**: 앱 아이콘(`web/icon.svg` → `tools/make_icons.js` 로 PNG), 색·화면 디자인(`web/style.css`, `ios/App/*`), 엔진·서버·분석 코드, 자체 모델(학습 스크립트 `analysis/train_model.py`, DB 식 `supabase/model.sql`) 전부.
**글꼴**: 앱은 기기 기본 글꼴(아이폰 Apple SD Gothic Neo, 안드로이드 Noto Sans CJK)만 쓴다 — 따로 넣은 글꼴 없음.
소개 웹사이트(site/)만 인터넷으로 글꼴을 불러온다: 영어 Outfit(Google Fonts, SIL Open Font License 1.1, https://fonts.google.com/specimen/Outfit), 한글 Pretendard(SIL Open Font License 1.1, https://github.com/orioncactus/pretendard). 파일로 넣은 것은 없다.
**로고**: 자전거 R 마크·RIDEY 글자(Y 의 체크)는 팀이 직접 그린 초안을 SVG 로 옮긴 것(`site/img/mark.svg`).
