"""매일 새벽 작업 — 어제까지의 자전거별 대여기록으로 오늘 아침 목록을 만든다 → web/data/morning/<오늘>.json

출처:
  --source file --month 2606      월별 파일(열린데이터광장 OA-15182). 시연용. 한 달 치 전부의 아침 목록을 만든다.
  --source api --api-url <주소>    공공데이터포털 '서울시설공단_공공자전거 대여이력 정보'(키 2). 명세의 요청주소만 넣으면
                                  최근 7일을 하루씩·쪽마다 받아 목록을 만든다. 열 이름이 낯설면 받은 열을 보여 주며 멈춤
                                  → engine/core.py FIELDS 에 한 줄. 날짜 인자 이름이 다르면 --date-param.
그리고 키 1 이 있으면 실시간 대여소 현황을 web/data/status.json 에 남긴다(지도의 지금 자전거 수).
"""
import argparse, datetime as dt, json, pathlib, sqlite3, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import load_seoul, load_faults, mark
from engine.morning import RULE, morning_lists
from server import seoul_api

OUT = ROOT / "web" / "data" / "morning"   # 시연용(월별 파일) — git 에 들어감
OPS = ROOT / "web" / "data" / "ops"       # 운영(API·실시간) 매일 목록·채점·대여소 현황 — git 에서 뺌(매일 바뀜), 앱이 둘을 합쳐 보여 줌
DB = ROOT / "data" / "daily.sqlite"
LOOKBACK_DAYS = 7   # 연쇄는 며칠씩 이어지기도 한다 — 일주일 치를 보고 오늘 아침 목록을 만든다 (server/rehearse.py 로 확인)


def db(path=None):
    c = sqlite3.connect(path or DB)
    c.execute("create table if not exists lists(day text, bike text, station text, chain int, level text, primary key(day, bike))")
    c.execute("create table if not exists scores(day text primary key, listed int, rode int, first_dud int, scored_at text)")
    return c


def record(c, day, items):
    """오늘 아침 목록을 남긴다 (내일 아침 채점용)."""
    with c:
        c.execute("delete from lists where day = ?", (day,))
        c.executemany("insert into lists values (?, ?, ?, ?, ?)", [(day, x["bike"], x["station"], x["chain"], x["level"]) for x in items])


def score(c, day, R):
    """어제(day) 목록 자전거를 어제 처음 빌린 '다른 사람' 이 헛걸음했나 — 매일 아침 어제 기록이 들어오면 채점 (Phase 3 합격 기준)."""
    bikes = {b for (b,) in c.execute("select bike from lists where day = ?", (day,))}
    if not bikes:
        return None
    M = mark(R[R["bike"].isin(bikes)], RULE)
    lo = pd.Timestamp(day)
    M = M[(M["t0"] >= lo) & (M["t0"] < lo + pd.Timedelta(days=1)) & ~M["retry"]]
    first = M.groupby("bike").head(1)
    row = (day, len(bikes), len(first), int(first["dud"].sum()), dt.datetime.now().isoformat(timespec="seconds"))
    with c:
        c.execute("insert or replace into scores values (?, ?, ?, ?, ?)", row)
    return row


def run_morning(c, today, R, station_name):
    """today 아침: 어제까지의 기록 R(최근 LOOKBACK_DAYS 일) → 오늘 목록 기록 + 어제 목록 채점. 운영(api)·예행연습이 같이 쓴다."""
    days = morning_lists(R, None, station_name=station_name, with_truth=False)
    items = days.get(today, [])
    record(c, today, items)
    yesterday = (pd.Timestamp(today) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return items, score(c, yesterday, R)


def _items(data):
    """공공데이터포털 응답에서 행 목록과 전체 건수를 꺼낸다. 형식 두 가지:
    표준 {"response": {"header": {...}, "body": {"items": {"item": [...]}, "totalCount": n}}}, odcloud {"data": [...], "totalCount": n}."""
    if isinstance(data.get("data"), list):
        return data["data"], int(data.get("totalCount") or data.get("matchCount") or len(data["data"]))
    resp = data.get("response", data)
    head = resp.get("header", {})
    if head and str(head.get("resultCode", "00")) not in ("00", "0", "000"):
        raise RuntimeError(f"API 오류 {head.get('resultCode')}: {head.get('resultMsg')}")
    body = resp.get("body", {})
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):   # 한 건이면 목록이 아니라 딕셔너리로 온다
        items = [items]
    return items, int(body.get("totalCount") or len(items))


def fetch_rentals_api(start, end, url=None, key=None, per_page=1000, date_params=None, max_pages=10000):
    """공공데이터포털 대여이력 API → 통일된 표(load_seoul 과 같은 열). 하루씩 page 를 넘기며 받는다.
    url: 상세기능 요청 주소 (환경변수 RENT_API_URL 또는 --api-url). 명세 확인 뒤 주소만 넣으면 된다.
    date_params: 날짜를 넘기는 인자 이름 (기본 RENT_API_DATE_PARAM 또는 'searchDate', 값은 YYYYMMDD — 명세에 맞게)."""
    import os, urllib.parse, urllib.request
    from engine.core import from_rows
    k = key or seoul_api.key("datagokr")
    if not k:
        raise SystemExit("공공데이터포털 인증키가 없습니다: 키체인(security add-generic-password -a bike-doctor -s datagokr -w '<키>') 또는 DATAGOKR_KEY")
    url = url or os.environ.get("RENT_API_URL")
    if not url:
        raise SystemExit("대여이력 API 주소가 없습니다 — 공공데이터포털 '서울시설공단_공공자전거 대여이력 정보' 상세기능의 요청주소를 "
                         "RENT_API_URL 또는 --api-url 로. 날짜 인자 이름이 다르면 RENT_API_DATE_PARAM.")
    dparam = date_params or os.environ.get("RENT_API_DATE_PARAM", "searchDate")
    rows, day = [], start
    while day <= end:
        page = 1
        while page <= max_pages:
            q = {"serviceKey": k, "pageNo": page, "numOfRows": per_page, "page": page, "perPage": per_page,
                 "type": "json", "returnType": "json", dparam: day.strftime("%Y%m%d")}
            with urllib.request.urlopen(url + ("&" if "?" in url else "?") + urllib.parse.urlencode(q, safe="%"), timeout=60) as r:
                items, total = _items(json.loads(r.read().decode("utf-8")))
            rows += items
            if not items or page * per_page >= total:
                break
            page += 1
        day += dt.timedelta(days=1)
    R = from_rows(rows).drop_duplicates(["bike", "t0", "st0"])   # 날짜 인자를 무시하는 API 면 날마다 같은 행이 온다
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    return R[(R["t0"] >= lo) & (R["t0"] < hi)].reset_index(drop=True)


def write_scores(c, out=None):
    """다음 날 아침 채점 결과를 앱이 읽게 → web/data/ops/scores.json {목록 날짜: {listed, rode, first_dud}}"""
    out = out or OPS / "scores.json"
    rows = c.execute("select day, listed, rode, first_dud from scores order by day").fetchall()
    json.dump({d: {"listed": n, "rode": r, "first_dud": k} for d, n, r, k in rows}, open(out, "w"))
    return len(rows)


def write(days, station_name, only_latest, out=None):
    out = out or OUT
    out.mkdir(parents=True, exist_ok=True)
    keys = [max(days)] if only_latest else sorted(days)
    for day in keys:
        json.dump({"date": day, "generated": dt.datetime.now().isoformat(timespec="seconds"),
                   "rule": "서로 다른 사람이 3분·300m 안 반납을 2번 이상 이어서 한 뒤 아직 정상 이용이 없는 자전거",
                   "bikes": days[day]}, open(out / f"{day}.json", "w"), ensure_ascii=False)
    idx = sorted({p.stem for p in out.glob("2*.json")})
    json.dump(idx, open(out / "index.json", "w"))
    return keys


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["file", "api", "live"], default="file",
                    help="live = server/live.py 가 모아 둔 서울 대여이력(data/live.sqlite, 반납 즉시) — 키 1 하나로")
    ap.add_argument("--month", default="2606")
    ap.add_argument("--api-url", help="대여이력 API 요청주소 (또는 환경변수 RENT_API_URL)")
    ap.add_argument("--date-param", help="날짜 인자 이름 (기본 searchDate, 또는 RENT_API_DATE_PARAM)")
    ap.add_argument("--today", help="이 날 아침인 것처럼 (놓친 날 다시 만들기·검사용, YYYY-MM-DD)")
    a = ap.parse_args(argv)
    stn = {s["id"]: s["name"] for s in json.load(open(ROOT / "web" / "data" / "stations.json"))}
    if a.source == "file":
        R = load_seoul(ROOT / "data" / "raw" / f"rent_{a.month}.csv")
        F = load_faults(ROOT / "data" / "raw" / "fault_2601-2606.csv")
        days = morning_lists(R, F, station_name=stn, with_truth=False)
        written = write(days, stn, only_latest=False)
    else:
        today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
        if a.source == "live":   # 오늘 0시 전까지의 최근 7일 (실시간 서버가 이미 받아 둠 → 추가 호출 없음)
            from server import live
            midnight = dt.datetime.combine(today, dt.time())
            lc = live.db()
            n = live.ensure_complete(lc, midnight - dt.timedelta(days=LOOKBACK_DAYS), midnight)
            if n:
                print(f"덜 받은 시간 {n}칸 다시 받음 (맥이 잠들었던 듯)")
            R = live.window(lc, midnight)
            R = R[R["t0"] < midnight].reset_index(drop=True)
        else:
            R = fetch_rentals_api(today - dt.timedelta(days=LOOKBACK_DAYS), today - dt.timedelta(days=1), url=a.api_url, date_params=a.date_param)
        print(f"받은 대여 {len(R):,}건 ({R['t0'].min()} ~ {R['t0'].max()})" if len(R) else "받은 대여 0건 — 날짜 인자·주소를 확인하세요")
        c = db()
        items, scored = run_morning(c, today.isoformat(), R, stn)
        OPS.mkdir(parents=True, exist_ok=True)
        write_scores(c)
        days = {today.isoformat(): items}
        written = write(days, stn, only_latest=True, out=OPS)
        if scored:
            print(f"어제({scored[0]}) 목록 {scored[1]}대 중 어제 빌린 {scored[2]}대, 첫 이용자 헛걸음 {scored[3]}대")
    if seoul_api.key() and a.source != "file":
        json.dump({"at": dt.datetime.now().isoformat(timespec="seconds"), "stations": seoul_api.station_status()},
                  open(OPS / "status.json", "w"), ensure_ascii=False)
    print(f"아침 목록 {len(written)}일 작성 (마지막 {written[-1]}, {len(days[written[-1]])}대)")


if __name__ == "__main__":
    main()
