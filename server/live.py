"""실시간 경보 — 서울 대여이력 API(tbCycleRentData)는 반납하자마자 자전거별 기록이 올라온다(2026-09-25 실측: 지연 약 0분).
그래서 '하루 늦은 아침 목록' 대신, 서로 다른 두 번째 사람이 빌리자마자 반납하는 그 순간 경보를 낼 수 있다.

    python server/live.py                 # 처음엔 최근 7일을 채우고, 그 뒤 1분마다 받아 web/data/live.json 갱신 (Ctrl+C 로 멈춤)
    python server/live.py --once          # 한 번만 받고 끝 (시험용)
    python server/live.py --report        # 지금까지 낸 경보가 맞았나: 경보 뒤 '다른 사람' 첫 대여도 헛대여였나

받는 법: 대여 시각 기준 한 시간씩 받는다. 긴 대여는 반납해야 올라오므로(09:50 에 빌려 12:30 반납 → 09시 칸에 12:30 에 생김)
지금·직전 시간은 1분마다, 그 전 6시간은 10분마다 다시 받는다. 헛대여(3분 안)는 한 시간 안에 다 들어온다.

자료 지연: 2026-09-25 14시부터 API 가 한 시간에 평소(6천~1만 건)의 3~6% 만 내놓았다. 그러면 경보를 놓치고,
채점에선 빠진 대여 때문에 '다음 사람' 을 잘못 볼 수 있다. 그래서 시간마다 평소(같은 시각 지난 7일 중앙값)와 비교해
크게 모자란 시간(THIN)은 48시간 동안 10분마다 다시 받고, 앱에 '자료 지연' 을 알리고, 그 시간이 낀 경보는 채점을 보류한다.
"""
import argparse, datetime as dt, json, pathlib, sqlite3, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from engine.core import from_rows, mark
from engine.morning import RULE
from server import seoul_api

DB = ROOT / "data" / "live.sqlite"
OUT = ROOT / "web" / "data" / "live.json"
LOOKBACK_DAYS = 7          # 연쇄는 며칠 이어지기도 한다 (아침 목록과 같게)
FRESH_HOURS = 24           # 마지막 헛대여가 이보다 오래된 연쇄는 목록에서 뺌 — 2일+ 서 있던 연쇄는 다음 사람 헛걸음 10~12% (docs/report.md 5-4)
COLS = ["bike", "t0", "st0", "t1", "st1", "dist_m", "who"]


def db(path=DB):
    c = sqlite3.connect(path)
    c.execute("create table if not exists rentals(bike text, t0 text, st0 text, t1 text, st1 text, dist_m real, who text, primary key(bike, t0))")
    c.execute("create table if not exists hours(hour text primary key, rows int, fetched_at text)")
    c.execute("create table if not exists alarms(bike text, at text, station text, chain int, seen_at text, primary key(bike, at))")
    return c


def store(c, rows, hour):
    R = from_rows(rows)
    recs = [(r.bike, str(r.t0), r.st0, str(r.t1), r.st1, float(r.dist_m), r.who if isinstance(r.who, str) else None)
            for r in R[COLS].itertuples(index=False)]
    with c:
        c.executemany("insert or replace into rentals values (?, ?, ?, ?, ?, ?, ?)", recs)
        c.execute("insert or replace into hours values (?, ?, ?)", (hour, len(recs), dt.datetime.now().isoformat(timespec="seconds")))
    return len(recs)


def fetch_hour(c, t):
    """t 가 속한 한 시간을 받아 저장. 'YYYY-MM-DD/HH'."""
    hour = t.strftime("%Y-%m-%d/%H")
    return store(c, seoul_api.fetch("tbCycleRentData", "rentData", hour), hour)


def backfill(c, now, days=LOOKBACK_DAYS, workers=6):
    """아직 안 받은 지난 시간들을 채운다 (한 시간 ≈ 1~7번 호출, 서울 API 는 호출 수 제한 없음). 받기는 여러 개 동시에, 저장은 차례로."""
    from concurrent.futures import ThreadPoolExecutor
    have = {h for (h,) in c.execute("select hour from hours")}
    t = (now - dt.timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    todo = []
    while t < now - dt.timedelta(hours=7):
        if t.strftime("%Y-%m-%d/%H") not in have:
            todo.append(t.strftime("%Y-%m-%d/%H"))
        t += dt.timedelta(hours=1)
    n = 0
    with ThreadPoolExecutor(workers) as ex:
        for hour, rows in zip(todo, ex.map(lambda h: seoul_api.fetch("tbCycleRentData", "rentData", h), todo)):
            n += store(c, rows, hour)
    return n


SETTLE = dt.timedelta(hours=3)   # 대여 시각 기준 한 시간 칸은 끝나고 3시간쯤 지나야 긴 대여까지 거의 다 들어온다


def ensure_complete(c, start, end, settle=SETTLE):
    """start~end 사이 시간 칸 중 아예 없거나, 칸이 끝나고 settle 이 지나기 전에 마지막으로 받은 것을 다시 받는다.
    아침 목록(daily_job --source live)이 맥이 막 깨어난 때 돌아도 어제 기록이 빠짐없게 (2026-09-26 09:15 목록이 23시 이후 없이 만들어졌었다)."""
    got = {h: dt.datetime.fromisoformat(f) for h, f in c.execute("select hour, fetched_at from hours")}
    t, todo = start.replace(minute=0, second=0, microsecond=0), []
    while t < end:
        h = t.strftime("%Y-%m-%d/%H")
        if h not in got or got[h] < t + dt.timedelta(hours=1) + settle:
            todo.append(t)
        t += dt.timedelta(hours=1)
    for t in todo:
        fetch_hour(c, t)
    return len(todo)


KEEP_DAYS = LOOKBACK_DAYS + 2   # 채점에 이틀 더 — 그보다 오래된 대여(생년·성별 포함)는 지운다


def prune(c, now, keep_days=KEEP_DAYS):
    """오래된 대여 기록 지우기 — 하루 약 15만 건이라 안 지우면 끝없이 커지고, 생년·성별을 필요 이상 오래 갖게 된다."""
    lo = str(now - dt.timedelta(days=keep_days))
    with c:
        n = c.execute("delete from rentals where t0 < ?", (lo,)).rowcount
        c.execute("delete from hours where hour < ?", ((now - dt.timedelta(days=keep_days)).strftime("%Y-%m-%d/%H"),))
    return n


THIN = 0.3           # 지난 7일 같은 시각 중 '가장 한산했던 날' 의 30% 도 안 되면 모자란 시간
RECHECK_HOURS = 48   # 모자란 시간을 다시 받는 기간
# 가장 한산한 날과 비교하는 까닭: 추석(9/24~26) 아침은 평일 중앙값의 22~25% 였지만 주말 아침과는 비슷했다(진짜로 적음).
# 자료가 끊긴 9/25 14~16시는 가장 한산한 날의 3~7% — 둘 사이가 넓다.


def hour_health(c, now):
    """시간마다 {'YYYY-MM-DD/HH': (받은 수 ÷ 평소 중앙값, 모자람 여부)} — 비교는 같은 시각 지난 7일(3일 이상 있을 때만).
    지금 시간은 아직 덜 찼으니 빼고, 직전 시간부터 본다(짧은 대여는 한 시간 안에 거의 다 들어옴)."""
    H = pd.read_sql("select hour, rows from hours", c)
    if H.empty:
        return {}
    H["t"] = pd.to_datetime(H["hour"], format="%Y-%m-%d/%H")
    H = H[H["t"] < pd.Timestamp(now).floor("h")]
    out = {}
    for r in H.itertuples():
        past = H[(H["t"].dt.hour == r.t.hour) & (H["t"] < r.t) & (H["t"] >= r.t - pd.Timedelta(days=7))]["rows"]
        if len(past) >= 3 and past.min() > 0:
            out[r.hour] = (r.rows / past.median(), r.rows < THIN * past.min())
    return out


def thin_hours(health):
    return {h for h, (_, thin) in health.items() if thin}


def feed_status(health, now):
    """앱에 보일 상태: 직전 시간까지 이어진 모자란 시간들의 시작과 가장 최근 시간의 비율(평소 중앙값 대비)."""
    t = pd.Timestamp(now).floor("h") - pd.Timedelta(hours=1)
    since, ratio = None, None
    while (h := t.strftime("%Y-%m-%d/%H")) in health and health[h][1]:
        since, ratio = t, health[h][0] if ratio is None else ratio
        t -= pd.Timedelta(hours=1)
    if since is None:
        return {"ok": True}
    return {"ok": False, "since": since.strftime("%Y-%m-%dT%H:00"), "ratio": round(float(ratio), 3)}


def window(c, now, days=LOOKBACK_DAYS):
    lo = str(now - dt.timedelta(days=days))
    R = pd.read_sql("select * from rentals where t0 >= ?", c, params=(lo,))
    R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"])
    R["who"] = R["who"].where(R["who"].notna(), None)
    return R.sort_values(["bike", "t0"], kind="stable").reset_index(drop=True)


def live_state(R, now, station_name=None, rule=RULE):
    """지금 이 순간 '서로 다른 사람 헛대여 연쇄가 끊기지 않은' 자전거 + 창 안에서 켜진 경보들."""
    station_name = station_name or {}
    M = mark(R, rule)
    d, retry, streak = M["dud"].to_numpy(), M["retry"].to_numpy(), M["streak"].to_numpy()
    M["chain_after"] = np.where(d & ~retry, streak + 1, np.where(d, streak, 0))
    last = M.groupby("bike").tail(1)
    fresh = last[(last["chain_after"] >= rule.alarm_k) & (last["t1"] >= now - pd.Timedelta(hours=FRESH_HOURS))]
    bikes = [{"bike": r.bike, "station": r.st1, "station_name": station_name.get(r.st1, r.st1), "chain": int(r.chain_after),
              "level": "빨강" if r.chain_after >= 3 else "노랑", "last_dud": r.t1.strftime("%m-%d %H:%M"),
              "minutes_ago": int((now - r.t1).total_seconds() // 60), "reported": None}
             for r in fresh.sort_values(["chain_after", "t1"], ascending=[False, False]).itertuples()]
    alarms = M.loc[M["alarm"], ["bike", "t1", "st1", "streak"]]
    return bikes, alarms


def score(c, now, live_only=True):
    """낸 경보마다: 경보 뒤 다른 사람(같은 사람 재시도 제외)의 첫 대여도 헛대여였나. 아직 아무도 안 빌렸으면 채점 보류.
    live_only: 서비스가 켜져 있을 때 10분 안에 알아챈 경보만 (처음 채운 지난 7일 경보는 파일로 잰 것과 같은 옛 기록이라 뺌)."""
    A = pd.read_sql("select * from alarms", c)
    if live_only and not A.empty:
        A = A[(pd.to_datetime(A["seen_at"]) - pd.to_datetime(A["at"])) <= pd.Timedelta(minutes=10)]
    if A.empty:
        return {"alarms": 0}
    R = mark(window(c, now, days=LOOKBACK_DAYS + 2), RULE)
    g = {k: v for k, v in R.groupby("bike")}
    thin = thin_hours(hour_health(c, now))
    hit = miss = wait = held = 0
    for a in A.itertuples():
        b = g.get(a.bike)
        nxt = b[(b["t0"] > pd.Timestamp(a.at)) & ~b["retry"]] if b is not None else None
        if nxt is None or nxt.empty:
            wait += 1
            continue
        span = pd.date_range(pd.Timestamp(a.at).floor("h"), nxt["t0"].iloc[0].floor("h"), freq="h")
        if any(t.strftime("%Y-%m-%d/%H") in thin for t in span):   # 그 사이 자료가 빠졌으면 진짜 다음 사람을 모른다
            held += 1
        elif nxt["dud"].iloc[0]:
            hit += 1
        else:
            miss += 1
    done = hit + miss
    return {"alarms": len(A), "scored": done, "next_rider_dud": hit, "precision_%": round(100 * hit / done, 1) if done else None,
            "waiting": wait, "held_thin_feed": held}


_last_score = {}


def tick(c, now, station_name, refresh_older=False):
    hours = [now - dt.timedelta(hours=k) for k in range(2, 8)] if refresh_older else []
    if refresh_older:   # 모자랐던 시간(48시간 안)도 다시 — API 가 뒤늦게 채우면 경보·채점이 바로잡힌다
        old = [dt.datetime.strptime(h, "%Y-%m-%d/%H") for h in thin_hours(hour_health(c, now))]
        hours += [t for t in old if now - dt.timedelta(hours=RECHECK_HOURS) <= t < now - dt.timedelta(hours=7)]
    for h in hours + [now - dt.timedelta(hours=1), now]:
        fetch_hour(c, h)
    R = window(c, now)
    bikes, alarms = live_state(R, pd.Timestamp(now), station_name)
    with c:   # 창 안에서 켜진 경보를 모두 기록 (이미 있으면 그대로) — 나중에 채점
        c.executemany("insert or ignore into alarms values (?, ?, ?, ?, ?)",
                      [(a.bike, str(a.t1), a.st1, int(a.streak) + 1, now.isoformat(timespec="seconds")) for a in alarms.itertuples()])
    today = alarms[alarms["t1"] >= pd.Timestamp(now.date())]
    out = {"date": "live", "at": now.isoformat(timespec="seconds"), "rule": "서로 다른 사람이 3분·300m 안 반납을 2번 이상 이어서 했고, "
           f"그 뒤 정상 이용이 없는 자전거 (마지막 헛대여 {FRESH_HOURS}시간 안)", "bikes": bikes,
           "today_alarms": len(today), "rentals_in_window": len(R), "score": _last_score,
           "feed": feed_status(hour_health(c, now), now)}
    if refresh_older:   # 10분마다 오래된 기록 정리 + 정비 동선용 대여소 붐빔(지난 7일 시간대별)
        prune(c, now)
        from engine.busy import station_busy
        ops = ROOT / "web" / "data" / "ops"
        ops.mkdir(parents=True, exist_ok=True)
        json.dump(station_busy(R, days=LOOKBACK_DAYS, end=pd.Timestamp(now)), open(ops / "busy.json", "w"), separators=(",", ":"))
    if refresh_older or not _last_score:   # 채점은 10분마다
        _last_score.clear(); _last_score.update(score(c, pd.Timestamp(now)))
    tmp = OUT.with_suffix(".tmp")
    json.dump(out, open(tmp, "w"), ensure_ascii=False)
    tmp.replace(OUT)   # 앱이 반쯤 쓴 파일을 읽지 않게
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--every", type=int, default=60, help="초")
    a = ap.parse_args()
    c = db()
    if a.report:
        print("실시간으로 알아챈 경보:", json.dumps(score(c, pd.Timestamp.now()), ensure_ascii=False))
        print("처음 채운 지난 기록 포함:", json.dumps(score(c, pd.Timestamp.now(), live_only=False), ensure_ascii=False))
        h = hour_health(c, pd.Timestamp.now())
        print("자료 상태:", json.dumps(feed_status(h, pd.Timestamp.now()), ensure_ascii=False),
              "· 모자란 시간:", ", ".join(f"{k[5:]}시 {v[0]:.0%}" for k, v in sorted(h.items()) if v[1]) or "없음")
        return
    if not seoul_api.key():
        raise SystemExit("서울 열린데이터광장 인증키가 없습니다: security add-generic-password -a bike-doctor -s seoul-openapi -w")
    stn = {s["id"]: s["name"].strip() for s in json.load(open(ROOT / "web" / "data" / "stations.json"))}
    n = backfill(c, dt.datetime.now())
    print(f"지난 {LOOKBACK_DAYS}일 채움: 새로 {n:,}건", flush=True)
    i, last = 0, None
    while True:
        now = dt.datetime.now()
        try:
            # 맥이 잠들었다 깨면(지난 판단에서 3분 넘게 지남) 바로 지난 7시간을 다시 받고, 잠든 사이 통째로 빠진 시간도 채운다
            # (2026-09-25 22시~26일 9시 잠듦 → 23·0·1시가 아예 안 받아졌었다: 지난 7일 채우기는 켤 때만 돌았음)
            woke = last is not None and (now - last) > dt.timedelta(minutes=3)
            if woke or i % 10 == 0:
                n = backfill(c, now)
                if n or woke:
                    print(f"{now:%m-%d %H:%M} {'깨어남 — ' if woke else ''}빠진 시간 채움: 새로 {n:,}건", flush=True)
            out = tick(c, now, stn, refresh_older=(woke or i % 10 == 0))
            s, f = out["score"], out["feed"]
            print(f"{now:%m-%d %H:%M} 지금 의심 {len(out['bikes'])}대 · 오늘 경보 {out['today_alarms']} · "
                  f"채점 {s.get('scored', 0)}건 정밀도 {s.get('precision_%')}%"
                  + ("" if f["ok"] else f" · 자료 지연 {f['since'][11:13]}시부터 (평소의 {f['ratio']:.0%})"), flush=True)
        except Exception as e:   # 한 번 실패해도 계속
            print(f"{now:%m-%d %H:%M} 실패: {e}", flush=True)
        if a.once:
            break
        i, last = i + 1, now
        time.sleep(max(5, a.every - (dt.datetime.now() - now).total_seconds()))   # 받기·판정에 걸린 시간을 빼고 기다림 → 약 1분 간격


if __name__ == "__main__":
    main()
