"""전기차 충전기 상태를 몇 분마다 모은다 → data/ev.sqlite. 공공데이터포털 '한국환경공단_전기자동차 충전소 정보'(키 2, 키체인 datagokr).

    python server/ev_collect.py --zcode 11 --every 5     # 서울(11), 5분마다 (Ctrl+C 로 멈춤)
    python server/ev_collect.py --report                 # 모은 것으로 '헛충전 연쇄' 충전기 목록

요청: http://apis.data.go.kr/B552584/EvCharger/getChargerStatus?serviceKey=..&dataType=JSON&pageNo=..&numOfRows=9999&period=10&zcode=11
(period = 최근 N분 안에 상태가 바뀐 충전기만. 응답 필드: statId, chgerId, stat, statUpdDt, lastTsdt, lastTedt, nowTsdt)
※ 키 발급 뒤 첫 호출에서 필드 이름·페이지 구조를 확인해 필요하면 여기만 고친다.
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
        items = data.get("items", {}).get("item", []) if isinstance(data.get("items"), dict) else data.get("items", [])
        rows += items
        total = int(data.get("totalCount", len(rows)))
        if len(rows) >= total or not items:
            return rows
        page += 1


def collect(zcode, every):
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
