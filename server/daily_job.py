"""매일 새벽 작업 — 어제까지의 자전거별 대여기록으로 오늘 아침 목록을 만든다 → web/data/morning/<오늘>.json

출처:
  --source file --month 2606      월별 파일(열린데이터광장 OA-15182). 시연용. 한 달 치 전부의 아침 목록을 만든다.
  --source api                    공공데이터포털 '서울시설공단_공공자전거 대여이력 정보'(키 2). 명세는 키 발급 뒤 확인 →
                                  fetch_rentals_api() 를 채운다. 그 전엔 친절한 오류로 멈춘다.
그리고 키 1 이 있으면 실시간 대여소 현황을 web/data/status.json 에 남긴다(지도의 지금 자전거 수).
"""
import argparse, datetime as dt, json, pathlib, sqlite3, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import load_seoul, load_faults, mark
from engine.morning import RULE, morning_lists
from server import seoul_api

OUT = ROOT / "web" / "data" / "morning"
DB = ROOT / "data" / "daily.sqlite"
LOOKBACK_DAYS = 7   # 연쇄는 며칠씩 이어지기도 한다 — 일주일 치를 보고 오늘 아침 목록을 만든다 (server/rehearse.py 로 확인)


def db(path=DB):
    c = sqlite3.connect(path)
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


def fetch_rentals_api(start, end):
    k = seoul_api.key("datagokr")
    if not k:
        raise SystemExit("공공데이터포털 인증키가 키체인에 없습니다: security add-generic-password -a bike-doctor -s datagokr -w '<키>'")
    raise SystemExit("대여이력 API 명세 확인 필요(키 발급 뒤 공공데이터포털 '서울시설공단_공공자전거 대여이력 정보' 상세기능) — "
                     "받은 행을 load_seoul 과 같은 열(bike,t0,st0,t1,st1,dist_m,who)로 바꿔 돌려주면 된다.")


def write(days, station_name, only_latest):
    OUT.mkdir(parents=True, exist_ok=True)
    keys = [max(days)] if only_latest else sorted(days)
    for day in keys:
        json.dump({"date": day, "generated": dt.datetime.now().isoformat(timespec="seconds"),
                   "rule": "서로 다른 사람이 3분·300m 안 반납을 2번 이상 이어서 한 뒤 아직 정상 이용이 없는 자전거",
                   "bikes": days[day]}, open(OUT / f"{day}.json", "w"), ensure_ascii=False)
    idx = sorted({p.stem for p in OUT.glob("2*.json")})
    json.dump(idx, open(OUT / "index.json", "w"))
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["file", "api"], default="file")
    ap.add_argument("--month", default="2606")
    a = ap.parse_args()
    stn = {s["id"]: s["name"] for s in json.load(open(ROOT / "web" / "data" / "stations.json"))}
    if a.source == "file":
        R = load_seoul(ROOT / "data" / "raw" / f"rent_{a.month}.csv")
        F = load_faults(ROOT / "data" / "raw" / "fault_2601-2606.csv")
        days = morning_lists(R, F, station_name=stn, with_truth=False)
        written = write(days, stn, only_latest=False)
    else:
        today = dt.date.today()
        R = fetch_rentals_api(today - dt.timedelta(days=LOOKBACK_DAYS), today - dt.timedelta(days=1))
        items, scored = run_morning(db(), today.isoformat(), R, stn)
        days = {today.isoformat(): items}
        written = write(days, stn, only_latest=True)
        if scored:
            print(f"어제({scored[0]}) 목록 {scored[1]}대 중 어제 빌린 {scored[2]}대, 첫 이용자 헛걸음 {scored[3]}대")
    if seoul_api.key():
        json.dump({"at": dt.datetime.now().isoformat(timespec="seconds"), "stations": seoul_api.station_status()},
                  open(ROOT / "web" / "data" / "status.json", "w"), ensure_ascii=False)
    print(f"아침 목록 {len(written)}일 작성 (마지막 {written[-1]}, {len(days[written[-1]])}대)")


if __name__ == "__main__":
    main()
