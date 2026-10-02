"""클라우드 5분 예약 SQL 을 고칠 때 — 옛 live.sql 과 새 live.sql 이 같은 답을 내는지, 얼마나 빨라졌는지 로컬 Postgres 에서 잰다.

    python tools/live_sql_compare.py --port 54329 [--old HEAD] [--month 2606]
    python tools/live_sql_compare.py --old 9d4233f --cold <로컬 PGDATA>   # 식은 캐시에서 읽는 페이지 수 (디스크가 느린 무료 DB 의 비용)

지난 달 대여이력(분석 캐시 M_<달>.pkl)을 '반납된 순서대로' 30분씩 흘려 넣으며 두 DB 에서 같은 일을 시킨다:
  record_alarms → settle (매번), compute·score (매번 비교), sample_list (3시간마다), settle_samples (매번).
비교: 지금 목록(자전거·연쇄·대여소·확률·이유), 오늘 경보 수, 모델 기대·하한, 경보 표(확률·채점 결과), 채점, 스스로 배우기 표본.
클라우드 DB 는 건드리지 않는다. pg_net·pg_cron·Vault 는 빈 껍데기로 대신한다(이 비교에 안 쓰임).
--cold: 클라우드처럼 '반납 순서' 로 쌓은 표에서, 쿼리마다 로컬 서버를 다시 켜(shared_buffers 32MB) 디스크에서 읽은 페이지 수를 센다.
  무료 DB 는 디스크가 기본 250 IOPS 라 이 수가 곧 시간이다(읽기 4천 번 ≈ 16초).
"""
import argparse, pathlib, re, subprocess, sys, tempfile, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
import pandas as pd

STUBS = """
do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
create schema if not exists cron;
create table if not exists cron.job (jobid bigserial, jobname text, schedule text, command text);
create or replace function cron.schedule(n text, s text, c text) returns bigint language sql as $f$ insert into cron.job(jobname, schedule, command) values (n, s, c) returning jobid $f$;
create or replace function cron.unschedule(j bigint) returns boolean language sql as $f$ delete from cron.job where jobid = j returning true $f$;
create schema if not exists net;
create table if not exists net._http_response (id bigint primary key, status_code int, content text);
create sequence if not exists net.req_seq;
create or replace function net.http_get(url text, params jsonb default '{}', headers jsonb default '{}', timeout_milliseconds int default 5000)
  returns bigint language sql as $f$ select nextval('net.req_seq') $f$;
create schema if not exists vault;
create table if not exists vault.decrypted_secrets (name text, decrypted_secret text);
"""


def run(port, db, sql, quiet=True):
    r = subprocess.run(["psql", "-h", "localhost", "-p", str(port), "-U", "postgres", "-d", db, "-X", "-At", "-v", "ON_ERROR_STOP=1"] + (["-q"] if quiet else []),
                       input=sql, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{db}: {r.stderr[-2000:]}")
    return r.stdout


def portable(sql):
    return "\n".join(l for l in sql.splitlines() if not re.match(r"\s*create extension", l))


def timed(port, db, sql):
    t = time.perf_counter(); out = run(port, db, sql); return out, time.perf_counter() - t


def fresh(port, db, body, model):
    subprocess.run(["dropdb", "-h", "localhost", "-p", str(port), "-U", "postgres", "--if-exists", db], check=True, capture_output=True)
    subprocess.run(["createdb", "-h", "localhost", "-p", str(port), "-U", "postgres", db], check=True)
    run(port, db, "create schema live;" + STUBS)
    run(port, db, model)
    run(port, db, portable(body))


def cold(a, old_sql, new_sql, model, M):
    import json
    now = pd.Timestamp(a.start)
    R = M[M["bike"].notna() & (M["t0"] >= now - pd.Timedelta(days=9)) & (M["t1"] <= now)][["bike", "t0", "st0", "t1", "st1", "dist_m", "who"]].copy()
    R["bike"] = R["bike"].astype(str)
    R = R.drop_duplicates(["bike", "t0"], keep="last").sort_values("t1")   # 클라우드처럼 반납(도착) 순서로 쌓임
    f = pathlib.Path(tempfile.gettempdir()) / "live_sql_cold.csv"; R.to_csv(f, header=False, index=False)
    T = f"'{now:%Y-%m-%d %H:%M:%S}'::timestamp"
    Q = [("후보 찾기", f"select cardinality(live.cand({T}))"),
         ("연쇄 표시(7일)", f"select count(*) from live.mark_rows({T} - interval '7 days', live.cand({T}))"),
         ("지금 목록", f"select live.compute({T})"),
         ("경보 기록", f"select live.record_alarms({T})")]
    out = {}
    for db, body in (("cold_old", old_sql), ("cold_new", new_sql)):
        fresh(a.port, db, body, model)
        run(a.port, db, f"copy live.rentals (bike, t0, st0, t1, st1, dist_m, who) from '{f}' with csv; vacuum analyze live.rentals;")
        for name, q in Q:
            # 로그는 파일로 — 출력을 붙잡으면 새로 뜬 서버가 그 통로를 계속 쥐고 있어 끝나지 않는다
            subprocess.run(["pg_ctl", "-D", a.cold, "-m", "fast", "-w", "-l", str(pathlib.Path(tempfile.gettempdir()) / "live_sql_cold.log"), "restart", "-o",
                            f"-p {a.port} -c shared_buffers=32MB -c work_mem=2184kB -c max_parallel_workers_per_gather=0"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p = json.loads(run(a.port, db, f"explain (analyze, buffers, format json) {q}"))[0]
            rd = p["Plan"].get("Shared Read Blocks", 0) + p.get("Planning", {}).get("Shared Read Blocks", 0)
            out[(db, name)] = (rd, p["Execution Time"] + p["Planning Time"])
    print(f"\n{now} · 대여 {len(R):,}행을 반납 순서로 · 식은 캐시(32MB)에서 읽은 페이지 (250 IOPS 면 걸릴 시간)")
    for name, _ in Q:
        (o, ot), (n, nt) = out[("cold_old", name)], out[("cold_new", name)]
        print(f"  {name:12s} {o:>7,} → {n:>7,}  ({o / 250:5.1f}초 → {n / 250:5.1f}초, 로컬 {ot:6.0f} → {nt:6.0f} ms)")
    return 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=54329); ap.add_argument("--old", default="HEAD")
    ap.add_argument("--month", default="2606"); ap.add_argument("--start", default="2026-06-12 06:00"); ap.add_argument("--hours", type=int, default=36)
    ap.add_argument("--cold", metavar="PGDATA", help="식은 캐시 읽기 수 재기 (그 로컬 서버를 다시 켠다)")
    a = ap.parse_args()
    old_sql = subprocess.run(["git", "-C", str(ROOT), "show", f"{a.old}:supabase/live.sql"], capture_output=True, text=True, check=True).stdout
    new_sql = (ROOT / "supabase" / "live.sql").read_text()
    model = (ROOT / "supabase" / "model.sql").read_text()
    M = pd.read_pickle(ROOT / "data" / "cache" / "ml" / f"M_{a.month}.pkl")
    if a.cold:
        return cold(a, old_sql, new_sql, model, M)
    start = pd.Timestamp(a.start)
    R = M[M["bike"].notna() & (M["t0"] >= start - pd.Timedelta(days=9)) & (M["t1"] <= start + pd.Timedelta(hours=a.hours))]
    R = R[["bike", "t0", "st0", "t1", "st1", "dist_m", "who"]].copy()
    R["bike"] = R["bike"].astype(str)
    R = R.sort_values(["bike", "t0"]).drop_duplicates(["bike", "t0"], keep="last")
    print(f"대여 {len(R):,}행 ({R['t0'].min()} ~ {R['t1'].max()})", flush=True)
    for db, body in (("old", old_sql), ("new", new_sql)):
        fresh(a.port, db, body, model)
    t_prev = None
    cur = start
    diffs = 0
    times = {"old": {}, "new": {}}
    while cur <= start + pd.Timedelta(hours=a.hours):
        chunk = R[(R["t1"] <= cur) & ((R["t1"] > t_prev) if t_prev is not None else True)]
        f = pathlib.Path(tempfile.gettempdir()) / "live_sql_compare.csv"; chunk.to_csv(f, header=False, index=False)
        for db in ("old", "new"):
            if len(chunk):   # 로컬 서버라 파일을 바로 읽는다
                run(a.port, db, f"copy live.rentals (bike, t0, st0, t1, st1, dist_m, who) from '{f}' with csv")
            if t_prev is None:
                run(a.port, db, "analyze live.rentals")
        ts = f"'{cur:%Y-%m-%d %H:%M:%S}'::timestamp"
        res = {}
        for db in ("old", "new"):
            out = {}
            for name, q in (("record_alarms", f"select live.record_alarms({ts})"), ("settle", f"select live.settle({ts})"),
                            ("compute", f"select live.compute({ts}) - 'rentals_in_window'"), ("score", f"select live.score({ts}, false)")):
                out[name], dt = timed(a.port, db, q)
                times[db].setdefault(name, []).append(dt)
            if cur.hour % 3 == 0 and cur.minute == 0:
                out["sample_list"], dt = timed(a.port, db, f"select live.sample_list({ts})"); times[db].setdefault("sample_list", []).append(dt)
            out["settle_samples"], dt = timed(a.port, db, f"select live.settle_samples({ts})"); times[db].setdefault("settle_samples", []).append(dt)
            if cur.hour == 6 and cur.minute == 30:   # 아침 목록(06:10 뒤)과 어제 목록 채점
                d = f"'{cur:%Y-%m-%d}'::date"
                out["morning"], dt = timed(a.port, db, f"select live.morning({d}) - 'generated'"); times[db].setdefault("morning", []).append(dt)
                run(a.port, db, f"insert into live.lists(day, generated, body) values ({d} - 1, now(), live.morning({d} - 1)) on conflict (day) do nothing")
                _, dt = timed(a.port, db, f"select live.score_day({d} - 1)"); times[db].setdefault("score_day", []).append(dt)
                out["scores"] = run(a.port, db, "select day, listed, rode, first_dud from live.scores order by 1")
            out["alarms"] = run(a.port, db, "select bike, at, station, round(p_next::numeric, 4), next_t0, next_dud from live.alarms order by 1, 2")
            out["samples"] = run(a.port, db, "select at, bike, last_t0, chain, hist7_duds, hist7_rentals, prior_alarms7, round(dur_sec::numeric, 2), "
                                             "round(age_h::numeric, 4), round(shun::numeric, 4), round(p::numeric, 4), next_t0, next_dud from live.samples order by 1, 2")
            res[db] = out
        bad = [k for k in res["old"] if res["old"][k] != res["new"][k]]
        nb = res["new"]["compute"].count('"bike"')
        print(f"{cur:%m-%d %H:%M} 새 행 {len(chunk):>6,} · 목록 {nb:>3}대 · " + ("같음" if not bad else f"다름: {bad}"), flush=True)
        if bad:
            diffs += 1
            for k in bad:
                o, n = res["old"][k], res["new"][k]
                print(f"   {k} 옛: {o[:300]}\n   {k} 새: {n[:300]}")
        t_prev = cur
        cur += pd.Timedelta(minutes=30)
    print("\n단계별 평균 시간 (초) — 옛 → 새")
    for k in times["old"]:
        o, n = times["old"][k], times["new"][k]
        print(f"  {k:15s} {sum(o) / len(o):7.3f} → {sum(n) / len(n):7.3f}")
    # 5분 작업 전체가 오류 없이 도는지 (네트워크는 빈 껍데기 — 응답 한 쪽을 흉내 내 넣기까지)
    page = '{"rentData":{"list_total_count":"1","row":[{"BIKE_ID":"SPB-99999","RENT_DT":"2026-06-14 06:59:00","RENT_ID":"1","RTN_DT":"2026-06-14 07:00:00","RTN_ID":"1","USE_DST":"0","BIRTH_YEAR":"1990","SEX_CD":"M"}]}}'
    run(a.port, "new", f"insert into live.req(id, hour, page) values (-1, '2026-06-14/06', 1); insert into net._http_response values (-1, 200, $j${page}$j$);"
                       "select live.tick(); select live.tick();")
    tl = run(a.port, "new", "select ms from live.tick_log order by at desc limit 1").strip()
    left = run(a.port, "new", "select count(*) from live.req where id = -1").strip()
    print(f"5분 작업(live.tick) 두 번 오류 없음 · 단계별 ms {tl} · 흉내 응답 넣음 {left == '0'}")
    print("\n결과:", "모든 시각에서 같은 답" if diffs == 0 else f"{diffs}개 시각에서 다름")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
