"""Supabase 실시간 DB(live 스키마) 처음 채우기·검사 — supabase/live.sql 을 적용한 뒤.

    python tools/supabase_live_load.py --stations          # 대여소 이름 (web/data/stations.json)
    python tools/supabase_live_load.py --backfill 8         # 지난 8일 대여이력을 서울 API 로 받아 한꺼번에 넣기 (맥에서 몇 분)
    python tools/supabase_live_load.py --parity             # SQL 로 만든 지금 목록 = 파이썬 엔진(server/live.py live_state) 인지
    python tools/supabase_live_load.py --parity-model       # 자체 모델 특징: SQL live.p_features = 파이썬 features

DB 비밀번호는 키체인 'supabase-db'. 5분마다 도는 예약(pg_cron)은 이 뒤로 새 시간만 받는다.
"""
import argparse, csv, datetime as dt, io, json, os, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from server import seoul_api
from server.seoul_api import key

DSN = "host=aws-0-ap-southeast-1.pooler.supabase.com port=5432 dbname=postgres user=postgres.iqvquwvoljzuvdgtbpnu sslmode=require"


def psql(sql, stdin=None):
    pw = key("supabase-db")
    return subprocess.run(["psql", DSN, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql], input=stdin, env={**os.environ, "PGPASSWORD": pw},
                          capture_output=True, text=True, check=True).stdout


def copy_rows(table, cols, rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    pw = key("supabase-db")
    subprocess.run(["psql", DSN, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", f"\\copy {table}({','.join(cols)}) from stdin with csv"],
                   input=buf.getvalue(), env={**os.environ, "PGPASSWORD": pw}, text=True, check=True)


def stations():
    st = json.load(open(ROOT / "web/data/stations.json"))
    psql("truncate live.stations")
    copy_rows("live.stations", ["id", "name"], [(s["id"], s["name"].strip()) for s in st])
    print("대여소", psql("select count(*) from live.stations").strip())


def backfill(days):
    from concurrent.futures import ThreadPoolExecutor
    from engine.core import from_rows
    now = dt.datetime.now()
    have = set(psql("select hour from live.hours").split())
    t = (now - dt.timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    todo = []
    while t <= now:
        h = t.strftime("%Y-%m-%d/%H")
        if h not in have:
            todo.append(h)
        t += dt.timedelta(hours=1)
    print(f"받을 시간 {len(todo)}칸")
    psql("create table if not exists live.load (like live.rentals); truncate live.load")
    n = 0
    with ThreadPoolExecutor(6) as ex:
        for hour, rows in zip(todo, ex.map(lambda h: seoul_api.fetch("tbCycleRentData", "rentData", h), todo)):
            R = from_rows(rows)
            recs = [(r.bike, r.t0, r.st0, r.t1, r.st1, float(r.dist_m), r.who if isinstance(r.who, str) else None)
                    for r in R[["bike", "t0", "st0", "t1", "st1", "dist_m", "who"]].itertuples(index=False)]
            if recs:
                copy_rows("live.load", ["bike", "t0", "st0", "t1", "st1", "dist_m", "who"], recs)
            psql(f"insert into live.hours(hour, total, fetched_at) values ('{hour}', {len(rows)}, now()) on conflict (hour) do update set total = excluded.total, fetched_at = now()")
            n += len(recs)
            if len(todo) > 20 and todo.index(hour) % 24 == 0:
                print(f"  {hour} … 누적 {n:,}건", flush=True)
    psql("insert into live.rentals select distinct on (bike, t0) * from live.load order by bike, t0 "
         "on conflict (bike, t0) do update set st0 = excluded.st0, t1 = excluded.t1, st1 = excluded.st1, dist_m = excluded.dist_m, who = excluded.who; drop table live.load")
    total = psql("select count(*) from live.rentals").strip()
    size = psql("select pg_size_pretty(pg_total_relation_size('live.rentals'))").strip()
    print(f"넣음 {n:,}건 · DB 대여 {total}건 · 크기 {size}")


def parity():
    """같은 시각·같은 행으로 SQL(live.compute) 과 파이썬(live.live_state) 의 지금 목록이 같은지."""
    from server import live
    now = pd.Timestamp(psql("select to_char(max(t1), 'YYYY-MM-DD HH24:MI:SS') from live.rentals where t1 <= (now() at time zone 'Asia/Seoul')").strip())
    sql = json.loads(psql(f"select live.compute('{now}'::timestamp)"))
    out = psql(f"copy (select bike, t0, st0, t1, st1, dist_m, who from live.rentals where t0 >= '{now}'::timestamp - interval '7 days') to stdout with csv")
    R = pd.read_csv(io.StringIO(out), names=["bike", "t0", "st0", "t1", "st1", "dist_m", "who"], dtype={"st0": str, "st1": str, "who": object})
    R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"])
    R["who"] = R["who"].where(R["who"].notna(), None)
    R = R.sort_values(["bike", "t0"], kind="stable").reset_index(drop=True)
    bikes, alarms = live.live_state(R, now)
    py = {(b["bike"], b["chain"], b["station"]) for b in bikes}
    sq = {(b["bike"], b["chain"], b["station"]) for b in sql["bikes"]}
    today = int((alarms["t1"] >= now.normalize()).sum())
    print(f"기준 {now} · 파이썬 {len(py)}대 / SQL {len(sq)}대 · 같음 {len(py & sq)} · 파이썬만 {sorted(py - sq)[:5]} · SQL만 {sorted(sq - py)[:5]}")
    print(f"오늘 경보: 파이썬 {today} / SQL {sql['today_alarms']}")
    # 채점: DB 에 적힌 경보 전부(live_only 아님)를 파이썬으로 다시 매겨 SQL live.score 와 비교
    sc = json.loads(psql(f"select live.score('{now}'::timestamp, false)"))
    A = pd.read_csv(io.StringIO(psql("copy (select bike, at from live.alarms) to stdout with csv")), names=["bike", "at"], parse_dates=["at"])
    out9 = psql(f"copy (select bike, t0, st0, t1, st1, dist_m, who from live.rentals where t0 >= '{now}'::timestamp - interval '9 days' "
                f"and bike in (select bike from live.alarms)) to stdout with csv")
    R9 = pd.read_csv(io.StringIO(out9), names=["bike", "t0", "st0", "t1", "st1", "dist_m", "who"], dtype={"st0": str, "st1": str, "who": object})
    R9["t0"] = pd.to_datetime(R9["t0"]); R9["t1"] = pd.to_datetime(R9["t1"]); R9["who"] = R9["who"].where(R9["who"].notna(), None)
    from engine.core import mark
    from engine.morning import RULE
    M = mark(R9.sort_values(["bike", "t0"], kind="stable").reset_index(drop=True), RULE)
    g = {k: v for k, v in M.groupby("bike")}
    hit = scored = 0
    for a in A.itertuples():
        b = g.get(a.bike)
        nxt = b[(b["t0"] > a.at) & ~b["retry"]] if b is not None else None
        if nxt is not None and not nxt.empty:
            scored += 1; hit += bool(nxt["dud"].iloc[0])
    print(f"채점: 파이썬 {hit}/{scored} / SQL {sc['next_rider_dud']}/{sc['scored']} (경보 {len(A)})")
    return py == sq and today == sql["today_alarms"] and (hit, scored) == (sc["next_rider_dud"], sc["scored"])


def parity_model():
    """자체 모델의 특징: SQL live.p_features = 파이썬 analysis/ml_compare.py features (같은 행, 지금 기준 8일, 목록 자전거마다 마지막 헛대여)."""
    from engine.core import mark
    from engine.morning import RULE
    from analysis.ml_compare import features
    from analysis.train_model import FEATS5
    from analysis.snapshot_model import FEATS6
    now = pd.Timestamp(psql("select to_char(max(t1), 'YYYY-MM-DD HH24:MI:SS') from live.rentals where t1 <= (now() at time zone 'Asia/Seoul')").strip())
    sql = json.loads(psql(f"select live.compute('{now}'::timestamp)"))
    bikes = [b["bike"] for b in sql["bikes"]]
    arr = "array[" + ",".join(f"'{b}'" for b in bikes) + "]::text[]"
    S = pd.read_csv(io.StringIO(psql(f"copy (select * from live.p_features('{now}'::timestamp, {arr})) to stdout with csv")),
                    names=["bike"] + FEATS6).set_index("bike").sort_index()
    out = psql(f"copy (select bike, t0, st0, t1, st1, dist_m, who from live.rentals where t0 >= '{now}'::timestamp - interval '8 days' "
               f"and bike = any({arr})) to stdout with csv")
    R = pd.read_csv(io.StringIO(out), names=["bike", "t0", "st0", "t1", "st1", "dist_m", "who"], dtype={"st0": str, "st1": str, "who": object})
    R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"]); R["who"] = R["who"].where(R["who"].notna(), None)
    M = mark(R.sort_values(["bike", "t0"], kind="stable").reset_index(drop=True), RULE)
    F = features(M)
    F["bike"] = M["bike"].astype(str).to_numpy()
    last = M.assign(**{c: F[c].to_numpy() for c in FEATS5}).groupby(M["bike"].astype(str)).tail(1).set_index(M["bike"].astype(str).groupby(M["bike"].astype(str)).tail(1).to_numpy())
    P = last[FEATS5].copy()
    P["age_h"] = (now - last["t1"]).dt.total_seconds() / 3600
    near = pd.read_csv(io.StringIO(psql(f"copy (select st0, t0 from live.rentals where t1 >= '{now}'::timestamp - interval '25 hours' and t0 < '{now}'::timestamp) to stdout with csv")),
                       names=["st0", "t0"], dtype={"st0": str}, parse_dates=["t0"])
    P["shun"] = [np.log1p(((near["st0"] == st) & (near["t0"] > t1)).sum()) for st, t1 in zip(last["st1"], last["t1"])]
    P = P.sort_index()
    same = (S.round(3) == P.loc[S.index, FEATS6].round(3)).all(axis=1)
    p_sql = {b["bike"]: b.get("p_next") for b in sql["bikes"]}
    print(f"목록 {len(bikes)}대 · SQL 특징 {len(S)}대 · 파이썬과 같음 {int(same.sum())} · 다름 {list(S.index[~same])[:5]}")
    print("확률 예:", ", ".join(f"{b} 연쇄{int(S.loc[b, 'chain'])}·{S.loc[b, 'age_h']:.1f}시간→{p_sql[b]}%" for b in list(S.index)[:5]))
    if not same.all():
        print(pd.concat([S.loc[~same], P.loc[S.index[~same], FEATS6]], keys=["sql", "py"]).head(6))
    return bool(same.all()) and len(S) == len(bikes)


def parity_morning(day):
    """오늘(day) 아침 목록: SQL live.morning = 파이썬 engine/morning.py morning_lists (같은 행, 자정 전 7일)."""
    from engine.morning import morning_lists
    d = pd.Timestamp(day)
    sql = json.loads(psql(f"select live.morning('{day}'::date)"))
    out = psql(f"copy (select bike, t0, st0, t1, st1, dist_m, who from live.rentals where t0 >= '{day}'::date - 7 and t0 < '{day}'::date) to stdout with csv")
    R = pd.read_csv(io.StringIO(out), names=["bike", "t0", "st0", "t1", "st1", "dist_m", "who"], dtype={"st0": str, "st1": str, "who": object})
    R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"]); R["who"] = R["who"].where(R["who"].notna(), None)
    items = morning_lists(R.sort_values(["bike", "t0"], kind="stable").reset_index(drop=True), None, with_truth=False).get(day, [])
    py = {(x["bike"], x["chain"], x["station"]) for x in items}
    sq = {(x["bike"], x["chain"], x["station"]) for x in sql["bikes"]}
    print(f"아침 목록 {day}: 파이썬 {len(py)}대 / SQL {len(sq)}대 · 같음 {len(py & sq)} · 파이썬만 {sorted(py - sq)[:3]} · SQL만 {sorted(sq - py)[:3]}")
    return py == sq


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stations", action="store_true")
    ap.add_argument("--backfill", type=int)
    ap.add_argument("--parity", action="store_true")
    ap.add_argument("--parity-morning", metavar="YYYY-MM-DD")
    ap.add_argument("--parity-model", action="store_true")
    a = ap.parse_args()
    if a.stations:
        stations()
    if a.backfill:
        backfill(a.backfill)
    if a.parity_morning:
        sys.exit(0 if parity_morning(a.parity_morning) else 1)
    if a.parity_model:
        sys.exit(0 if parity_model() else 1)
    if a.parity:
        sys.exit(0 if parity() else 1)
