"""전기차 충전기 상태를 몇 분마다 모은다 → data/ev.sqlite. 공공데이터포털 '한국환경공단_전기자동차 충전소 정보'(키 2, 키체인 datagokr).

    python server/ev_collect.py --zcode 11 --every 5     # 서울(11), 5분마다 (Ctrl+C 로 멈춤)
    python server/ev_collect.py --report                 # 모은 것으로 '헛충전 연쇄' 충전기 목록

요청: http://apis.data.go.kr/B552584/EvCharger/getChargerStatus?serviceKey=..&dataType=JSON&pageNo=..&numOfRows=9999&period=10&zcode=11
(period = 최근 N분 안에 상태가 바뀐 충전기만. 응답 필드: statId, chgerId, stat, statUpdDt, lastTsdt, lastTedt, nowTsdt)
※ 키 발급 뒤 첫 호출에서 필드 이름·페이지 구조를 확인해 필요하면 여기만 고친다.

한계(수집 간격): API 는 충전기마다 '마지막' 충전 한 건만 준다. 두 번 찍는 사이에 충전이 두 번 끝나면 앞의 것은 덮여 사라진다 —
하필 헛충전(3분 안)이 바로 다음 사람으로 이어지는 경우가 잘 사라진다. 그래서 --report 는 '찍은 간격' 도 보여 주고,
간격은 호출 한도(개발 계정 보통 하루 1,000번) 안에서 짧게: 5분 = 하루 288번(쪽 1개일 때), 2분 = 720번.
"""
import argparse, datetime as dt, json, pathlib, sqlite3, sys, time, urllib.parse, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from server.seoul_api import key
from engine.ev import sessions, zombie_chargers

URL = "http://apis.data.go.kr/B552584/EvCharger/getChargerStatus"
DB = ROOT / "data" / "ev.sqlite"
FIELDS = ["statId", "chgerId", "stat", "statUpdDt", "lastTsdt", "lastTedt", "nowTsdt"]


def db():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("create table if not exists snap(at text, " + ", ".join(f"{f} text" for f in FIELDS) + ")")
    return c


def fetch(zcode, period):
    k = key("datagokr")
    if not k:
        raise SystemExit("공공데이터포털 인증키가 없습니다: security add-generic-password -a bike-doctor -s datagokr -w '<키>'")
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({"serviceKey": k, "dataType": "JSON", "pageNo": page, "numOfRows": 9999, "period": period, "zcode": zcode})
        with urllib.request.urlopen(f"{URL}?{q}", timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        items = data.get("items", {}).get("item", []) if isinstance(data.get("items"), dict) else data.get("items") or []
        if isinstance(items, dict):   # 한 건이면 목록이 아니라 딕셔너리로 온다
            items = [items]
        if not items and str(data.get("resultCode", "00")) not in ("00", "0"):
            raise RuntimeError(f"API 오류 {data.get('resultCode')}: {data.get('resultMsg')}")
        rows += items
        total = int(data.get("totalCount", len(rows)))
        if len(rows) >= total or not items:
            return rows
        page += 1


def collect(zcode, every):
    print(f"{every}분마다 → 하루 약 {24 * 60 // every}번 × 쪽 수 호출 (한도 확인). 두 번 찍는 사이 끝난 충전 두 건 중 앞의 것은 못 봄.", flush=True)
    while True:
        at = dt.datetime.now().isoformat(timespec="seconds")
        try:
            items = fetch(zcode, period=every * 2)
            with db() as c:
                c.executemany(f"insert into snap values (?, {', '.join('?' * len(FIELDS))})",
                              [(at, *[str(it.get(f, "")) for f in FIELDS]) for it in items])
            print(f"{at} 상태 {len(items)}건", flush=True)
        except Exception as e:   # 한 번 실패해도 계속 모은다
            print(f"{at} 실패: {e}", flush=True)
        time.sleep(every * 60)


def report():
    with db() as c:
        S = pd.read_sql("select * from snap", c)
    X = sessions(S)
    ats = pd.to_datetime(S["at"].drop_duplicates()).sort_values()
    if len(ats) > 1:
        gap = ats.diff().dt.total_seconds().div(60)
        print(f"찍은 횟수 {len(ats)}, 간격 중앙값 {gap.median():.1f}분 (최대 {gap.max():.0f}분 — 이 사이 끝난 충전은 마지막 한 건만 보임)")
    Z = zombie_chargers(X, now=pd.Timestamp.now())
    print(f"끝난 충전 {len(X):,}건, 헛충전(3분 안) {100 * (X['minutes'] <= 3).mean():.1f}%, 연쇄 끊기지 않은 충전기 {len(Z)}대")
    print(Z.head(20).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zcode", default="11")
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    report() if a.report else collect(a.zcode, a.every)
