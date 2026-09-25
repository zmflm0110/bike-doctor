"""서울 열린데이터광장 Open API 클라이언트. 인증키는 macOS 키체인에서 읽는다(코드·git 에 넣지 않음).

키 넣기(한 번):
    security add-generic-password -a bike-doctor -s seoul-openapi -w '<인증키>'
    security add-generic-password -a bike-doctor -s datagokr -w '<공공데이터포털 인증키>'

맥이 아닌 서버·CI 에서는 환경변수로: SEOUL_OPENAPI_KEY, DATAGOKR_KEY (키체인보다 먼저 본다).
키가 없으면 'sample' 키로 동작(서비스마다 최대 5건) — 형식 확인·시험용.
"""
import json, os, subprocess, time, urllib.request

BASE = "http://openapi.seoul.go.kr:8088"


ENV = {"seoul-openapi": "SEOUL_OPENAPI_KEY", "datagokr": "DATAGOKR_KEY"}


def key(service="seoul-openapi"):
    env = os.environ.get(ENV.get(service, ""), "").strip()
    if env:
        return env
    try:
        return subprocess.run(["security", "find-generic-password", "-a", "bike-doctor", "-s", service, "-w"],
                              capture_output=True, text=True, check=True).stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):   # 키 없음 / 맥이 아님
        return None


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def fetch(service, root, extra="", page=1000, k=None):
    """서비스 전체를 page 건씩 나눠 받는다(서울 API 는 한 번에 최대 1,000건). sample 키면 5건만."""
    k = k or key() or "sample"
    step = 5 if k == "sample" else page
    rows, start = [], 1
    while True:
        data = _get(f"{BASE}/{k}/json/{service}/{start}/{start + step - 1}/{extra}")
        body = data.get(root)
        if not body:
            code = data.get("RESULT", {}).get("CODE")
            if code == "INFO-200":   # 해당 자료 없음
                break
            raise RuntimeError(f"{service}: {data}")
        rows += body["row"]
        total = int(body["list_total_count"])
        start += step
        if k == "sample" or start > total:
            break
    return rows


def station_status(k=None):
    """실시간 대여소 현황: 대여소ID, 이름, 거치대 수, 지금 자전거 수, 위도, 경도."""
    return [{"id": r["stationId"], "name": r["stationName"], "racks": int(r["rackTotCnt"]), "bikes": int(r["parkingBikeTotCnt"]),
             "lat": float(r["stationLatitude"]), "lon": float(r["stationLongitude"])}
            for r in fetch("bikeList", "rentBikeStatus", k=k)]


def stations(k=None):
    """대여소 정보: 대여소ID(ST-..), 대여소번호(5자리), 이름, 구, 위도, 경도 — 대여이력의 대여소번호와 실시간의 ST-ID 를 잇는다."""
    return [{"id": r["RENT_ID"], "no": r["RENT_NO"], "name": r["RENT_NM"], "gu": r["STA_LOC"],
             "lat": float(r["STA_LAT"]), "lon": float(r["STA_LONG"])} for r in fetch("tbCycleStationInfo", "stationInfo", k=k)]


def rentals(day, hours=range(24), k=None):
    """따릉이 대여이력(tbCycleRentData, 자전거별) — 대여 시각 기준 한 시간씩 받는다. day 'YYYY-MM-DD'.
    2026-09-25 실측: 반납하자마자 올라옴(지연 약 0분), 어제·오늘 모두 있음, 생년·성별 포함 → 월별 파일과 같은 열(engine.core.from_rows)."""
    rows = []
    for h in hours:
        rows += fetch("tbCycleRentData", "rentData", f"{day}/{h:02d}", k=k)
    return rows


if __name__ == "__main__":
    print("키:", "있음" if key() else "없음 → sample 키(5건)")
    print(station_status()[:2])
    print(stations()[:2])
