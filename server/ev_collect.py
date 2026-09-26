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
import argparse, datetime as dt, json, os, pathlib, sqlite3, sys, time, urllib.parse, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from server.seoul_api import key
from engine.ev import sessions, zombie_chargers

URL = "http://apis.data.go.kr/B552584/EvCharger/getChargerStatus"
DB = pathlib.Path(os.environ.get("EV_DB", ROOT / "data" / "ev.sqlite"))   # GitHub 에서는 캐시에 둔 DB
FIELDS = ["statId", "chgerId", "stat", "statUpdDt", "lastTsdt", "lastTedt", "nowTsdt"]


def db(path=None):
    path = pathlib.Path(path or DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("create table if not exists snap(at text, " + ", ".join(f"{f} text" for f in FIELDS) + ")")
    c.execute("create table if not exists runs(at text primary key, rows int)")        # 찍은 때 — 빈틈없이 이어 찍은 구간을 알려고
    c.execute("create table if not exists last(charger text primary key, sig text)")   # 충전기마다 마지막으로 본 상태
    return c


def store(c, at, items):
    """바뀐 상태만 저장한다 — period 창이 겹쳐 같은 상태가 여러 번 오므로. 처음 본 때(at)가 그대로 남는다."""
    seen = dict(c.execute("select charger, sig from last"))
    new = []
    for it in items:
        row = [str(it.get(f, "")) for f in FIELDS]
        ch, sig = f"{row[0]}-{row[1]}", "|".join(row[2:])
        if seen.get(ch) != sig:
            new.append((at, *row)); seen[ch] = sig
    with c:
        c.executemany(f"insert into snap values (?, {', '.join('?' * len(FIELDS))})", new)
        c.executemany("insert or replace into last values (?, ?)", [(f"{r[1]}-{r[2]}", "|".join(r[3:])) for r in new])
        c.execute("insert or replace into runs values (?, ?)", (at, len(items)))
    return len(new)


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


def collect(zcode, every, once=False, period=None):
    if not once:
        print(f"{every}분마다 → 하루 약 {24 * 60 // every}번 × 쪽 수 호출 (한도 확인). 두 번 찍는 사이 끝난 충전 두 건 중 앞의 것은 못 봄.", flush=True)
    c = db()
    while True:
        at = dt.datetime.now().isoformat(timespec="seconds")
        try:
            items = fetch(zcode, period=period or every * 2)
            print(f"{at} 상태 {len(items)}건, 바뀐 것 {store(c, at, items)}건", flush=True)
        except Exception as e:   # 한 번 실패해도 계속 모은다
            if once:
                raise
            print(f"{at} 실패: {e}", flush=True)
        if once:
            return
        time.sleep(every * 60)


def report():
    with db() as c:   # 예전(바뀐 것만 저장 전) 기록도 같은 표라 그대로 읽힌다
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
    ap.add_argument("--period", type=int, help="최근 N분 안에 바뀐 충전기 (기본: 간격×2). GitHub 은 늦게 돌 때가 있어 30")
    ap.add_argument("--once", action="store_true", help="한 번만 (GitHub 예약 작업용)")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    report() if a.report else collect(a.zcode, a.every, a.once, a.period)
