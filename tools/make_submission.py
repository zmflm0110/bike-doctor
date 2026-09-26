"""대회 제출 zip 만들기 — 2026 디지털콘텐츠개발대회(생활 부문) 규칙에 맞춰 하나로 묶는다.

    python tools/make_submission.py --id 30000 --name 홍길동          # dist/[생활] 2026디콘_30000_홍길동.zip
    python tools/make_submission.py --id 30000 --name 홍길동 --check  # 만들기 전에 빠진 것만 확인

규칙(PLAN.md '목표 대회'): 모두 하나로 압축, 링크 제출 불가, 파일명 '[참가분야] 2026디콘_팀장학번_이름',
에셋·엔진의 출처와 다운로드 받은 폴더를 함께(미증명 실격), 일부 누락 시 실격.

zip 안:
  1_작품설명서/   작품설명서(학교 양식 — submission/작품설명서.* 에 두면 넣음) + 보고서(docs/report.pdf)
  2_시연영상/     docs/demo/*.mp4
  3_설치파일/     헛걸음제로.apk + 설치방법.txt
  4_소스/         git 에 있는 파일 전부(원본 대여이력처럼 큰 자료는 빼고, 받는 스크립트 포함)
  5_출처/         라이브러리 원본 꾸러미(받은 그대로) + 라이선스 + 자료·지도 출처 글
  6_발표자료/     docs/slides.pdf (본심용 — 예심 제출에도 넣어 둠)
  읽어보세요.txt
"""
import argparse, io, pathlib, shutil, subprocess, sys, urllib.request, zipfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CACHE = ROOT / "data" / "cache" / "credits"   # 받은 원본 꾸러미 (git 밖)
APK = ROOT / "android-app/android/app/build/outputs/apk"

# 출처 원본 — '다운로드 받은 폴더' 를 그대로 넣으려고 받은 곳에서 다시 받아 둔다
DOWNLOADS = {
    "leaflet-1.9.4/leaflet.zip": "https://leafletjs-cdn.s3.amazonaws.com/content/leaflet/v1.9.4/leaflet.zip",
    "jsqr-1.4.0/jsqr-1.4.0.tgz": "https://registry.npmjs.org/jsqr/-/jsqr-1.4.0.tgz",
}
TEXTS = {
    "openstreetmap.txt": "지도 바탕 그림: © OpenStreetMap 기여자 (Open Database License, https://www.openstreetmap.org/copyright)\n"
                         "앱이 인터넷으로 타일을 불러와 보여 주며, 지도 오른쪽 아래에 출처를 표시한다. 파일로 넣은 것은 없다.\n",
    "apple.txt": "아이폰 앱의 지도·화면: Apple MapKit·SwiftUI — Xcode(맥 앱스토어, 무료)에 들어 있는 기본 개발 도구. 따로 받은 에셋 없음.\n",
    "공공데이터.txt": "서울 열린데이터광장(https://data.seoul.go.kr): 따릉이 대여이력 OA-15182(실시간 API tbCycleRentData), 고장신고 OA-15644, 대여소 정보 — 공공누리 제1유형(출처 표시)\n"
                     "공공데이터포털(https://www.data.go.kr): 대전 타슈 대여이력, 한국환경공단 전기자동차 충전소 정보 — 공공누리 제1유형\n"
                     "앱 안(web/data)에는 가공 결과(자전거 번호·대여소·시각)만 있고 이용자 정보(생년·성별)는 없다.\n",
    "클라우드.txt": "GitHub Actions(무료, 공개 저장소) — 10분마다 서울 API 로 경보 계산 (.github/workflows/cloud.yml)\n"
                   "Supabase(무료 요금제) — 구조대 확인·현장 조사 저장 (supabase/schema.sql)\n",
    "직접만든것.txt": "앱 아이콘·시작 화면·색·화면 디자인, 엔진·서버·분석 코드는 모두 직접 만들었다.\n"
                    "아이콘 원본: web/icon.svg → tools/make_icons.js, tools/make_android_assets.js 로 PNG.\n"
                    "글꼴: 기기 기본 글꼴만 사용(따로 넣은 글꼴 없음).\n상용 엔진: 사용하지 않음.\n",
}
SKIP_SOURCE = ("docs/demo/", "ios/shots/", "docs/shots/")   # 큰 파일은 다른 폴더에 이미 들어감


def fetch(rel, url):
    p = CACHE / rel
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r:
            p.write_bytes(r.read())
    return p


def npm_pack(pkgdir, name):
    """안드로이드 앱에 실제로 들어간 Capacitor 꾸러미를 그대로 (node_modules 에서 버전 확인)."""
    out = CACHE / "capacitor"
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["npm", "pack", f"{pkgdir}/node_modules/{name}", "--pack-destination", str(out)], capture_output=True, text=True, cwd=pkgdir)
    return out / r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else None


def apk_file():
    for kind in ("release", "debug"):
        c = sorted((APK / kind).glob("*.apk")) if (APK / kind).exists() else []
        if c:
            return c[0]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="팀장 학번")
    ap.add_argument("--name", required=True, help="팀장 이름")
    ap.add_argument("--field", default="생활")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    name = f"[{a.field}] 2026디콘_{a.id}_{a.name}"
    need = {"보고서 PDF": ROOT / "docs/report.pdf", "발표 PDF": ROOT / "docs/slides.pdf", "시연 영상": next(iter(sorted((ROOT / "docs/demo").glob("*.mp4"))), None),
            "APK": apk_file(), "작품설명서(학교 양식)": next(iter(sorted((ROOT / "submission").glob("작품설명서.*"))), None) if (ROOT / "submission").exists() else None}
    missing = [k for k, v in need.items() if not v or not pathlib.Path(v).exists()]
    for k, v in need.items():
        print(f"  {'✓' if k not in missing else '✗'} {k}: {v or '없음'}")
    if a.check:
        return 1 if missing else 0
    if "APK" in missing or "시연 영상" in missing:
        raise SystemExit("APK·시연 영상은 꼭 있어야 한다(없으면 실격). 먼저 만들 것.")

    DIST.mkdir(exist_ok=True)
    out = DIST / f"{name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        put = lambda src, arc: z.write(src, f"{name}/{arc}")
        if need["작품설명서(학교 양식)"]:
            put(need["작품설명서(학교 양식)"], f"1_작품설명서/{pathlib.Path(need['작품설명서(학교 양식)']).name}")
        put(need["보고서 PDF"], "1_작품설명서/보고서_헛걸음제로.pdf")
        put(need["시연 영상"], "2_시연영상/헛걸음제로_시연.mp4")
        put(need["APK"], "3_설치파일/헛걸음제로.apk")
        z.writestr(f"{name}/3_설치파일/설치방법.txt",
                   "1. 안드로이드 폰(8.0 이상)에 헛걸음제로.apk 를 옮긴다.\n2. 파일을 누르고 '출처를 알 수 없는 앱 설치' 를 허용한다.\n"
                   "3. 설치 뒤 '헛걸음 제로' 를 연다. 인터넷이 있으면 '지금 (실시간)' 목록이, 없으면 앱 안의 시연 자료(2026-06-15)가 보인다.\n"
                   "4. QR 읽기는 카메라, '내 위치에서 출발' 은 위치 권한을 물어본다.\n아이폰 앱은 소스(4_소스/ios)로 Xcode 에서 빌드한다(애플 정책상 설치 파일 배포 불가).\n")
        for f in subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=ROOT, check=True).stdout.splitlines():
            if not f.startswith(SKIP_SOURCE) and (ROOT / f).is_file():
                put(ROOT / f, f"4_소스/{f}")
        for rel, url in DOWNLOADS.items():
            put(fetch(rel, url), f"5_출처/{rel}")
        put(ROOT / "web/vendor/leaflet/LICENSE", "5_출처/leaflet-1.9.4/LICENSE")
        put(ROOT / "web/vendor/jsqr/LICENSE", "5_출처/jsqr-1.4.0/LICENSE")
        for pkg in ("@capacitor/core", "@capacitor/android", "@capacitor/cli"):
            t = npm_pack(ROOT / "android-app", pkg)
            if t:
                put(t, f"5_출처/capacitor/{t.name}")
        for fn, text in TEXTS.items():
            z.writestr(f"{name}/5_출처/{fn}", text)
        put(ROOT / "docs/credits.md", "5_출처/출처_목록.md")
        put(need["발표 PDF"], "6_발표자료/헛걸음제로_발표.pdf")
        z.writestr(f"{name}/읽어보세요.txt",
                   "헛걸음 제로 — 따릉이 고장을 대여기록으로 먼저 찾는 앱 (2026 디지털콘텐츠개발대회 생활 부문)\n\n"
                   "1_작품설명서  작품 설명서·보고서\n2_시연영상  시연 영상\n3_설치파일  안드로이드 APK·설치 방법\n"
                   "4_소스  전체 소스(엔진·서버·웹앱·아이폰·안드로이드). 처음 볼 곳: README.md\n5_출처  라이브러리 원본·라이선스, 지도·자료 출처\n6_발표자료  발표 자료\n")
    print(f"→ {out} ({out.stat().st_size / 1e6:.1f}MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
