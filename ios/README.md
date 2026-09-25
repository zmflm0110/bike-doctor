# 헛걸음 제로 — 아이폰 앱 (SwiftUI)

웹앱과 같은 다섯 화면을 아이폰 앱으로. 자료(`web/data`)를 앱 안에 넣어 **인터넷 없이도** 목록·조회·시연이 된다(지도 바탕만 인터넷).
https 가 필요 없어서 위치·카메라(QR)가 바로 된다 — 웹앱의 "아이폰은 https 에서만" 문제가 없다.

| 탭 | 하는 일 |
|---|---|
| 아침 목록 | 구 고르기, 요약, "이 목록은 맞았을까?" 채점, 지도(의심 대여소·동선 번호), 정비 순위, 정비 동선(내 근처 10곳), 의심 자전거, 엑셀용 CSV 공유 |
| 자전거 조회 | 번호 입력 또는 QR 카메라 → 경고, 구조대 판정 |
| 구조대 | 가까운 의심 자전거부터 3초 확인 → 맥 서버로 |
| 시연 | 2026-06-15 하루 재생 (경보·막을 수 있던 헛걸음·뒤늦은 신고) |
| 현장 조사 | 가까운 대여소, 번호, 상태 6종, 메모, 사진(고르기·찍기, 1280px 로 줄임), 서버에 못 보내면 폰에 보관 |

## 아이폰에 설치 (맥에서, 약 10분)
1. 앱스토어에서 **Xcode** 설치(무료, 약 10GB — 디스크 확보 필요).
2. `ios/HeotgeoleumZero.xcodeproj` 더블클릭 → Xcode 가 엔진 패키지(`ios/Core`)를 같이 연다.
3. 왼쪽 위 프로젝트 → **Signing & Capabilities** → Team 에서 내 Apple ID(Personal Team) 고르기. 번들 ID 가 겹친다고 하면 `kr.bikedoctor.heotgeoleumzero` 끝에 아무 글자나 더하기.
4. 아이폰을 케이블로 연결 → 위쪽 기기 목록에서 내 아이폰 → ▶ (처음엔 아이폰 **설정 → 일반 → VPN 및 기기 관리**에서 개발자 앱 신뢰, **설정 → 개인정보 보호 → 개발자 모드** 켜기).
5. 무료 Apple ID 로 설치한 앱은 7일 뒤 다시 ▶ 해야 한다(유료 개발자 계정은 1년).

구조대·현장 조사 기록을 맥으로 모으려면: 맥에서 `python server/app.py` → 앱 오른쪽 위 ⚙︎ → `http://<맥이름>.local:8765`.

## 구조
- `Core/` — 엔진(Swift 패키지, 화면 없음): 자료 읽기, 순위·동선·채점·CSV, 하루 재생, 서버·조사 대기열. **리눅스에서도** `swift test`.
  정답은 웹앱에서 뽑아(`node tests/web/parity_fixture.js`) 두 앱이 같은 순위·동선(1e-6m)·채점을 내는지 검사한다.
- `App/` — SwiftUI 화면(MapKit·AVFoundation·CoreLocation·PhotosUI). iOS 17 이상.
- `project.yml` → `HeotgeoleumZero.xcodeproj` (`xcodegen generate`). 프로젝트를 고치면 project.yml 을 고치고 다시 만든다.
- 맥 CI(`.github/workflows/ios.yml`): 엔진 검사, Xcode 빌드, 시뮬레이터에서 켜고 화면 사진(Actions 의 ios-shots).

## 리눅스에서 (맥 없이) 할 수 있는 것
```sh
docker run --rm -v "$PWD":/w -w /w/ios/Core swift:6.1-noble swift test          # 엔진 검사
docker run --rm -e USER=u -v <XcodeGen 빌드>:/x -v "$PWD":/w -w /w/ios swift:6.1-noble /x/.build/release/xcodegen generate
```
화면(SwiftUI)은 애플 기기에서만 빌드된다 → 맥 CI 가 대신 확인.
