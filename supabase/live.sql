-- 실시간 경보를 Supabase 안에서 — GitHub 예약이 몇 시간씩 건너뛰어서(2026-09-26~27), DB 가 스스로 5분마다 돈다.
--   pg_cron(예약) → pg_net 으로 서울 대여이력 API(tbCycleRentData) → live.rentals → SQL 로 연쇄·경보(engine/core.py mark 와 같은 규칙)
--   → live.snapshot(live.json 과 같은 모양) → 앱은 public.live_snapshot 을 읽는다(공개 키로 읽기만).
-- 적용: psql 로 supabase/model.sql 다음에 이 파일(여러 번 돌려도 됨). 인증키는 Vault 'seoul_openapi'(코드·git 에 없음).
-- 규칙(engine/core.py): 헛대여 = 같은 대여소, 180초 안, 300m 미만. 같은 사람 = 바로 앞 대여와 생년+성별(who)이 같음.
--   streak = 앞선 헛대여 줄의 '서로 다른 사람' 수, 경보 = 헛대여 & 재시도 아님 & streak = 1(두 번째 사람), 목록 = 마지막 대여 기준 연쇄 2+ 이고 24시간 안.

create extension if not exists pg_net with schema extensions;
create extension if not exists pg_cron;
create schema if not exists live;

create table if not exists live.rentals (
  bike text not null, t0 timestamp not null, st0 text, t1 timestamp not null, st1 text,
  dist_m real not null default 0, who text,
  primary key (bike, t0) include (st0, t1, st1, dist_m, who)
);
-- 기본 키 색인에 나머지 열도 담는다(INCLUDE): 자전거별 기록이 색인 안에 붙어 있어 표를 읽지 않고(index-only) 연쇄를 센다.
-- 표는 반납 순서로 쌓여 한 자전거의 7일이 수십 페이지에 흩어진다 — 무료 DB 디스크(기본 250 IOPS)에서 식은 캐시로 읽으면 1~2분.
-- 같은 자료로 재 보니 읽는 페이지가 3~5배 줄었다(지금 목록 17,306 → 5,750, 경보 기록 22,935 → 4,707, 2026-10-02). 옛 DB 는 한 번 바꿔 끼운다.
do $$ begin
  if (select indnkeyatts = indnatts from pg_index where indexrelid = 'live.rentals_pkey'::regclass) then
    create unique index if not exists rentals_pkey_cover on live.rentals (bike, t0) include (st0, t1, st1, dist_m, who);
    alter table live.rentals drop constraint rentals_pkey, add constraint rentals_pkey primary key using index rentals_pkey_cover;
  end if;
end $$;
create index if not exists rentals_t1 on live.rentals (t1);
-- 헛대여만 담은 작은 색인(전체의 몇 %, 자전거·대여 시각도 담음) — 후보 찾기가 24시간 대여 15만 행을 훑지 않게 (2026-10-02)
create index if not exists rentals_dud_t1 on live.rentals (t1) include (bike, t0) where st0 = st1 and t1 - t0 <= interval '180 seconds' and dist_m < 300;
-- 자주 치우기(기본 20%). 넣기만 해도 치워야 '다 보이는 페이지' 표시가 붙어 색인만 읽기가 된다
alter table live.rentals set (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.05, autovacuum_vacuum_insert_scale_factor = 0.05);
create table if not exists live.hours (hour text primary key, total int, fetched_at timestamptz);
create table if not exists live.req (id bigint primary key, hour text not null, page int not null, made_at timestamptz not null default now());
create table if not exists live.stations (id text primary key, name text);
create table if not exists live.snapshot (id int primary key default 1 check (id = 1), at timestamp, body jsonb);

-- 대여소 번호: '02720' 과 2720 을 같게 (server 쪽 from_rows 와 같음)
create or replace function live.stn(x text) returns text language sql immutable as $$
  select case when btrim(x) ~ '^[0-9]+$' then lpad(btrim(x), 5, '0') else btrim(x) end $$;
create or replace function live.ts(x text) returns timestamp language plpgsql immutable as $$
begin return nullif(btrim(x), '')::timestamp; exception when others then return null; end $$;

-- API 한 쪽(JSON) → live.rentals. 같은 쪽 안의 겹친 (자전거, 대여시각)은 뒤의 것
create or replace function live.ingest(body jsonb) returns int language plpgsql as $$
declare n int;
begin
  with x as (
    select e.value v, e.ordinality o from jsonb_array_elements(coalesce(body->'rentData'->'row', '[]'::jsonb)) with ordinality e
  ), p as (
    select distinct on (v->>'BIKE_ID', live.ts(v->>'RENT_DT'))
      v->>'BIKE_ID' bike, live.ts(v->>'RENT_DT') t0, live.stn(v->>'RENT_ID') st0, live.ts(v->>'RTN_DT') t1, live.stn(v->>'RTN_ID') st1,
      case when v->>'USE_DST' ~ '^-?[0-9]+(\.[0-9]+)?$' then (v->>'USE_DST')::real else 0 end dist_m,
      case when nullif(nullif(v->>'BIRTH_YEAR', ''), '\N') is null then null
           else (v->>'BIRTH_YEAR') || coalesce(upper(nullif(v->>'SEX_CD', '')), '?') end who
    from x where v->>'BIKE_ID' is not null
    order by v->>'BIKE_ID', live.ts(v->>'RENT_DT'), o desc
  )
  insert into live.rentals select * from p where t0 is not null and t1 is not null
  on conflict (bike, t0) do update set st0 = excluded.st0, t1 = excluded.t1, st1 = excluded.st1, dist_m = excluded.dist_m, who = excluded.who
    -- 5분마다 같은 시간을 다시 받으니, 바뀐 행만 고쳐 쓴다(다 고쳐 쓰면 죽은 행이 두 시간에 17만 개 쌓였다 — 2026-09-27)
    where (live.rentals.st0, live.rentals.t1, live.rentals.st1, live.rentals.dist_m, live.rentals.who)
          is distinct from (excluded.st0, excluded.t1, excluded.st1, excluded.dist_m, excluded.who);
  get diagnostics n = row_count;
  return n;
end $$;

-- 한 시간 칸의 쪽들을 요청 (아는 전체 수 + 1쪽, 모르면 2쪽 — 첫 쪽을 받으면 나머지를 더 청함)
create or replace function live.request(hour text, first_page int default 1) returns int language plpgsql as $$
declare k text; tot int; last_page int; p int; n int := 0;
begin
  select decrypted_secret into k from vault.decrypted_secrets where name = 'seoul_openapi';
  select total into tot from live.hours where live.hours.hour = request.hour;
  last_page := coalesce(ceil(tot / 1000.0)::int, 1) + 1;
  for p in first_page..last_page loop
    insert into live.req(id, hour, page) values (
      net.http_get(format('http://openapi.seoul.go.kr:8088/%s/json/tbCycleRentData/%s/%s/%s', k, (p - 1) * 1000 + 1, p * 1000, hour), timeout_milliseconds := 30000),
      hour, p);
    n := n + 1;
  end loop;
  return n;
end $$;

-- 도착한 응답을 넣고 지운다. 첫 쪽에서 전체 수를 알면 모자란 쪽을 더 요청
create or replace function live.collect() returns int language plpgsql as $$
declare q record; b jsonb; n int := 0; tot int; asked int;
begin
  for q in select r.id, r.hour, r.page, h.status_code, h.content from live.req r join net._http_response h on h.id = r.id loop
    b := null;
    if q.status_code = 200 then begin b := q.content::jsonb; exception when others then b := null; end; end if;
    if b ? 'rentData' then
      n := n + live.ingest(b);
      tot := nullif(b->'rentData'->>'list_total_count', '')::int;
      insert into live.hours(hour, total, fetched_at) values (q.hour, tot, now())
        on conflict (hour) do update set total = excluded.total, fetched_at = excluded.fetched_at;
      select max(page) into asked from live.req where hour = q.hour;
      if tot > asked * 1000 then perform live.request(q.hour, asked + 1); end if;
    elsif b is not null then   -- 자료 없음(INFO-200): 그 시간은 0건
      insert into live.hours(hour, total, fetched_at) values (q.hour, 0, now())
        on conflict (hour) do update set fetched_at = excluded.fetched_at;
    end if;
    delete from live.req where id = q.id;
    delete from net._http_response where id = q.id;
  end loop;
  delete from live.req where made_at < now() - interval '15 minutes';   -- 답 없는 요청은 버림
  return n;
end $$;

-- 연쇄 표시 (engine/core.py mark 와 같음): since 이후 대여, bikes 가 주어지면 그 자전거만
create table if not exists live.alarms (bike text not null, at timestamp not null, station text, seen_at timestamp not null, primary key (bike, at));
-- 채점 결과는 한 번 정해지면 적어 둔다(next_*) — 대여 기록은 9일 뒤 지우지만 채점은 계속 쌓이게(2026-09-27)
alter table live.alarms add column if not exists next_t0 timestamp, add column if not exists next_dud boolean;
-- 경보가 울린 그 순간 자체 모델이 본 확률 — 나중에 실제 결과와 맞춰 모델을 실시간으로도 채점 (2026-10-01)
alter table live.alarms add column if not exists p_next real;

-- 연쇄 표시는 자전거 수에 따라 두 길로 (2026-10-02 실측):
--   아주 많을 때(하루치 아침 목록 등 수천 대) — 최근 기록을 한 번 죽 읽고 해시 조인
--   보통(5분 예약의 후보·목록·채점, 수백 대 이하) — 자전거마다 기본 키 색인으로 바로(LATERAL)
-- 예전엔 5분마다 후보 3천여 대를 표시해 계획에 따라 15~40초 걸렸다. 지금은 후보를 줄여(live.cand) 색인 길로 충분하다.
-- 0.5GB 무료 DB 라 work_mem 은 올리지 않는다(올렸더니 메모리·디스크가 밀려 예약 연결까지 막혔다, 2026-10-02).
create or replace function live.mark_rows_big(since timestamp, bikes text[], until timestamp default 'infinity')
returns table (bike text, t0 timestamp, t1 timestamp, st1 text, dud boolean, retry boolean, streak int) language sql stable
set enable_nestloop = off as $$
with b as materialized (select distinct unnest(bikes) bike), r as (
  select r.bike, r.t0, r.t1, r.st1, r.who, (r.st0 = r.st1 and r.t1 - r.t0 <= interval '180 seconds' and r.dist_m < 300) dud,
         lag(r.who) over (partition by r.bike order by r.t0) prev_who
  from live.rentals r join b using (bike) where r.t0 >= since and r.t0 < until
), r2 as (
  select *, coalesce(who = prev_who, false) retry,
         coalesce(sum(case when dud then 0 else 1 end) over (partition by bike order by t0 rows between unbounded preceding and 1 preceding), 0) g
  from r
), r3 as (
  select *, row_number() over (partition by bike, g order by t0) rn from r2
)   -- streak = 헛대여 줄 안에서, 첫 대여 뒤로 '재시도 아님' 인 대여 수
select bike, t0, t1, st1, dud, retry,
       (sum(case when rn > 1 and not retry then 1 else 0 end) over (partition by bike, g order by t0 rows between unbounded preceding and current row))::int
from r3
$$;
create or replace function live.mark_rows_small(since timestamp, bikes text[], until timestamp default 'infinity')
returns table (bike text, t0 timestamp, t1 timestamp, st1 text, dud boolean, retry boolean, streak int) language sql stable as $$
with r as (
  select r.bike, r.t0, r.t1, r.st1, r.who, (r.st0 = r.st1 and r.t1 - r.t0 <= interval '180 seconds' and r.dist_m < 300) dud,
         lag(r.who) over (partition by r.bike order by r.t0) prev_who
  from (select distinct unnest(bikes) bike) b
  cross join lateral (select * from live.rentals x where x.bike = b.bike and x.t0 >= since and x.t0 < until) r
), r2 as (
  select *, coalesce(who = prev_who, false) retry,
         coalesce(sum(case when dud then 0 else 1 end) over (partition by bike order by t0 rows between unbounded preceding and 1 preceding), 0) g
  from r
), r3 as (
  select *, row_number() over (partition by bike, g order by t0) rn from r2
)   -- streak = 헛대여 줄 안에서, 첫 대여 뒤로 '재시도 아님' 인 대여 수
select bike, t0, t1, st1, dud, retry,
       (sum(case when rn > 1 and not retry then 1 else 0 end) over (partition by bike, g order by t0 rows between unbounded preceding and current row))::int
from r3
$$;
-- engine/core.py mark 와 같은 규칙: since 이후 대여, 주어진 자전거만
create or replace function live.mark_rows(since timestamp, bikes text[], until timestamp default 'infinity')
returns table (bike text, t0 timestamp, t1 timestamp, st1 text, dud boolean, retry boolean, streak int) language plpgsql stable as $$
begin
  if coalesce(cardinality(bikes), 0) > 1500 then
    return query select * from live.mark_rows_big(since, bikes, until);
  else
    return query select * from live.mark_rows_small(since, bikes, until);
  end if;
end $$;

-- 24시간 안에 헛대여가 있던 자전거 (목록·오늘 경보는 모두 여기서 나온다)
-- 경보(두 번째 사람)와 목록(연쇄 2+)은 헛대여가 둘 이상 이어져야 생긴다 → '바로 앞 대여도 헛대여' 인 것만 후보로 (답은 똑같고 후보는 몇 분의 1, 2026-10-02)
create or replace function live.cand(now_ timestamp) returns text[] language sql stable as $$
  select coalesce(array_agg(distinct d.bike), '{}') from live.rentals d
  cross join lateral (select p.st0, p.st1, p.t0, p.t1, p.dist_m from live.rentals p where p.bike = d.bike and p.t0 < d.t0 order by p.t0 desc limit 1) p
  where d.t1 >= now_ - interval '24 hours' and d.st0 = d.st1 and d.t1 - d.t0 <= interval '180 seconds' and d.dist_m < 300
    and p.st0 = p.st1 and p.t1 - p.t0 <= interval '180 seconds' and p.dist_m < 300 $$;

-- 다음 '다른 사람'(재시도 아님)의 대여: at_ 뒤 첫 대여부터, 바로 앞 대여와 생년·성별이 같으면 건너뜀.
-- mark_rows(since_, …) 의 retry 와 같은 뜻(since_ 앞 대여는 앞사람으로 안 봄). 9일 창 전체를 표시하지 않고 기본 키 색인으로 몇 줄만 (2026-10-02)
create or replace function live.next_rider(bike_ text, at_ timestamp, since_ timestamp)
returns table (t0 timestamp, dud boolean) language sql stable as $$
  select t0, dud from (
    select x.t0, (x.st0 = x.st1 and x.t1 - x.t0 <= interval '180 seconds' and x.dist_m < 300) dud,
           coalesce(x.who = lag(x.who) over (order by x.t0), false) retry
    from ((select * from live.rentals p where p.bike = bike_ and p.t0 <= at_ and p.t0 >= since_ order by p.t0 desc limit 1)
          union all
          (select * from live.rentals n where n.bike = bike_ and n.t0 > at_ and n.t0 >= since_ order by n.t0 limit 20)) x
  ) y where y.t0 > at_ and not y.retry order by y.t0 limit 1
$$;

-- 경보 채점 (server/live.py score 와 같음): 경보 뒤 '다른 사람'(재시도 아님)의 첫 대여도 헛대여였나. 아직 없으면 기다림.
-- live_only: 5분 예약이 15분 안에 알아챈 경보만 (처음 채운 지난 경보는 뺌). 적어 둔 결과(next_dud)가 있으면 그것, 없으면 지금 기록으로 매김.
create or replace function live.score(now_ timestamp, live_only boolean default true) returns jsonb language sql stable as $$
with a as (
  select bike, at, next_dud, p_next from live.alarms where not live_only or seen_at - at <= interval '15 minutes'
), nx as (
  select a.bike, a.at, a.p_next, coalesce(a.next_dud, (select n.dud from live.next_rider(a.bike, a.at, now_ - interval '9 days') n)) nd from a
)
select jsonb_build_object('alarms', count(*), 'scored', count(nd), 'next_rider_dud', count(*) filter (where nd),
  'precision_%', round(100.0 * count(*) filter (where nd) / nullif(count(nd), 0), 1), 'waiting', count(*) - count(nd), 'seen_within_min', 15,
  'since', to_char(min(at), 'YYYY-MM-DD'),
  -- 자체 모델 실시간 채점: 경보 때 모델이 말한 확률의 평균 vs 실제로 다음 사람도 반납한 비율 (결과가 나온 경보만)
  'model', jsonb_build_object('n', count(*) filter (where p_next is not null and nd is not null),
    'pred_%', round((100 * avg(p_next) filter (where nd is not null))::numeric, 1),
    'real_%', round(100.0 * count(*) filter (where p_next is not null and nd) / nullif(count(*) filter (where p_next is not null and nd is not null), 0), 1)))
from nx
$$;

-- 다음 사람이 정해진 경보는 결과를 적어 둔다. 그 대여가 7시간 넘게 지난 뒤에만(2~6시간 전 기록은 30분마다 다시 받으므로, 늦게 온 앞 대여가 끼어들 수 없을 때)
create or replace function live.settle(now_ timestamp) returns int language plpgsql as $$
declare n int;
begin
  update live.alarms a set next_t0 = x.t0, next_dud = x.dud
  from (
    select a.bike, a.at, n.t0, n.dud
    from live.alarms a cross join lateral live.next_rider(a.bike, a.at, now_ - interval '9 days') n
    where a.next_dud is null
  ) x
  where a.bike = x.bike and a.at = x.at and x.t0 < now_ - interval '7 hours';
  get diagnostics n = row_count;
  return n;
end $$;

-- 자체 모델의 특징 (analysis/train_model.py · ml_compare.py features 와 같은 정의) — 자전거마다 마지막 헛대여 반납 시점, 지난 7일(그 대여 포함).
-- 확률 식 live.p_next_dud 는 supabase/model.sql (학습 스크립트가 만듦) — 이 파일보다 먼저 적용한다.
drop function if exists live.p_features(timestamp, text[]);
drop function if exists live.p_features(timestamp, text[], timestamp);
-- until: 지난 시각으로 다시 만들 때(스스로 배우기 자료 채우기) 그 뒤 기록을 안 보게
create or replace function live.p_features(now_ timestamp, bikes text[], until timestamp default 'infinity')
returns table (bike text, chain int, hist7_duds int, hist7_rentals int, prior_alarms7 int, dur_sec float8, age_h float8, shun float8)
language sql stable as $$
with m as (
  select * from live.mark_rows(now_ - interval '8 days', bikes, until)
), last as (
  select distinct on (bike) * from m order by bike, t0 desc
), base as (
  select l.bike, l.streak + 1 chain,
         (count(*) filter (where x.dud))::int duds, count(*)::int rentals,
         (count(*) filter (where x.dud and not x.retry and x.streak = 1) - case when l.streak + 1 >= 2 then 1 else 0 end)::int prior,
         extract(epoch from l.t1 - l.t0)::float8 dur, l.t1, r.st1
  from last l join m x on x.bike = l.bike and x.t0 >= l.t0 - interval '7 days' and x.t0 <= l.t0
  join live.rentals r on r.bike = l.bike and r.t0 = l.t0
  where l.dud
  group by l.bike, l.streak, l.t0, l.t1, r.st1
), recent as materialized (   -- 최근 25시간 대여를 한 번만, 목록 자전거의 대여소만 (t1 색인) — 자전거마다 전체 표를 훑던 계획이 30~40초 걸렸다(2026-10-02)
  select st0, t0 from live.rentals where t1 >= now_ - interval '25 hours' and t0 < now_ and st0 in (select st1 from base)
), near as (   -- 외면: 마지막 헛대여 뒤 지금까지 같은 대여소에서 다른 사람이 빌려 간 수
  select b.bike, count(r.t0) n
  from base b left join recent r on r.st0 = b.st1 and r.t0 > b.t1
  group by b.bike
)
select b.bike, b.chain, b.duds, b.rentals, b.prior, b.dur,
       greatest(0, extract(epoch from now_ - b.t1) / 3600)::float8, ln(1 + n.n)::float8
from base b join near n using (bike)
$$;

-- 스스로 배우기 (2026-10-02): 3시간마다(0·3·…·21시) 지금 목록의 자전거마다 모델 입력(특징 7개)과 그때 확률을 적어 두고,
-- 다음 다른 사람이 빌려 결과가 정해지면 정답(next_dud)을 채운다 → 사람이 정답을 달지 않아도 학습 자료가 쌓인다.
-- 맥에서 tools/retrain.py 가 이것과 지난 기록을 합쳐 다시 배우고, 최근 자료에서 지금 모델보다 나을 때만 바꾼다. (analysis/snapshot_model.py 의 표본과 같은 정의)
create table if not exists live.samples (
  at timestamp not null, bike text not null, last_t0 timestamp not null,
  chain int, hist7_duds int, hist7_rentals int, prior_alarms7 int, dur_sec real, age_h real, shun real,
  p real, next_t0 timestamp, next_dud boolean,
  primary key (at, bike)
);
drop function if exists live.sample_list(timestamp);
create or replace function live.sample_list(now_ timestamp, until timestamp default 'infinity') returns int language plpgsql as $$
declare n int; b text[] := live.cand(now_);
begin
  insert into live.samples(at, bike, last_t0, chain, hist7_duds, hist7_rentals, prior_alarms7, dur_sec, age_h, shun, p)
  with m as (select * from live.mark_rows(now_ - interval '7 days', b, until)),
  last as (select distinct on (bike) bike, t0, t1, dud, streak from m order by bike, t0 desc),
  fresh as (select * from last where dud and streak + 1 >= 2 and t1 >= now_ - interval '24 hours' and t1 <= now_),   -- 아직 반납 안 된 대여가 마지막이면 목록에 없음
  f as (select * from live.p_features(now_, (select coalesce(array_agg(bike), '{}') from fresh), until))
  select now_, fresh.bike, fresh.t0, f.chain, f.hist7_duds, f.hist7_rentals, f.prior_alarms7, f.dur_sec, f.age_h, f.shun,
         live.p_next_dud(f.chain, f.hist7_duds, f.hist7_rentals, f.prior_alarms7, f.dur_sec, f.age_h, f.shun)
  from fresh join f using (bike)
  on conflict (at, bike) do nothing;
  get diagnostics n = row_count;
  return n;
end $$;
-- 정답 채우기: 마지막 헛대여 뒤 처음 빌린 다른 사람(재시도 아님)도 헛대여였나. 그 대여가 7시간 넘게 지난 뒤에만(늦게 온 기록이 끼어들 수 없게)
create or replace function live.settle_samples(now_ timestamp) returns int language plpgsql as $$
declare n int;
begin
  update live.samples s set next_t0 = x.t0, next_dud = x.dud
  from (
    select s.at, s.bike, n.t0, n.dud
    from live.samples s cross join lateral live.next_rider(s.bike, s.last_t0, now_ - interval '9 days') n
    where s.next_dud is null and s.at > now_ - interval '8 days'
  ) x
  where s.at = x.at and s.bike = x.bike and x.t0 < now_ - interval '7 hours';
  get diagnostics n = row_count;
  return n;
end $$;

-- AI 가 본 이유 (설명 가능한 AI, 2026-10-02): 특징 하나씩을 '목록의 보통 자전거' 값(목록 표본 중앙값)으로 바꿨을 때 확률이 얼마나 변하나.
-- 가장 크게 움직인 셋을 사람 말로 — 앱의 조회 화면에 '왜 이 확률?' 로. (중앙값: 연쇄 2, 지난 7일 헛대여 4·대여 21, 이전 경보 0, 대여 34초, 경과 6.8시간, 외면 log1p 2.2)
create or replace function live.p_why(chain float8, duds float8, rentals float8, prior float8, dur float8, age float8, shun float8)
returns jsonb language sql immutable as $$
with p as (select live.p_next_dud(chain, duds, rentals, prior, dur, age, shun) v),
c as (
  select * from (values
    (case when chain >= 3 then format('서로 다른 %s명이 연달아 반납', chain::int) end,
     (select v from p) - live.p_next_dud(2, duds, rentals, prior, dur, age, shun)),
    (case when duds > 4 then format('지난 7일 바로 반납 %s번 (보통 4번)', duds::int) else format('지난 7일 바로 반납 %s번뿐', duds::int) end,
     (select v from p) - live.p_next_dud(chain, 4, rentals, prior, dur, age, shun)),
    (format('지난 7일 대여 %s번 (보통 21번)', rentals::int),
     (select v from p) - live.p_next_dud(chain, duds, 21, prior, dur, age, shun)),
    (case when prior > 0 then format('이번 주 경보 %s번 더 있었음', prior::int) end,
     (select v from p) - live.p_next_dud(chain, duds, rentals, 0, dur, age, shun)),
    (case when dur < 34 then format('%s초 만에 반납', dur::int) else format('%s초 타고 반납', dur::int) end,
     (select v from p) - live.p_next_dud(chain, duds, rentals, prior, 34, age, shun)),
    (case when age < 6.8 then format('%s 전에 반납 (최근)', case when age < 1 then (age * 60)::int || '분' else round(age::numeric, 1) || '시간' end)
          else format('%s시간째 그대로', round(age::numeric, 1)) end,
     (select v from p) - live.p_next_dud(chain, duds, rentals, prior, dur, 6.8, shun)),
    (format('그사이 이 대여소에서 빌려 간 사람 %s명 (%s)', round(exp(shun) - 1)::int, case when shun < 2.2 then '적음' else '많음' end),
     (select v from p) - live.p_next_dud(chain, duds, rentals, prior, dur, age, 2.2))
  ) x(t, d) where t is not null
)
select coalesce(jsonb_agg(jsonb_build_object('t', t, 'd', round(d::numeric * 100)::int) order by abs(d) desc), '[]'::jsonb)
from (select * from c where abs(d) >= 0.02 order by abs(d) desc limit 3) top
$$;

-- 지금 목록 (live.json 과 같은 모양)
create or replace function live.compute(now_ timestamp default (now() at time zone 'Asia/Seoul')::timestamp) returns jsonb language sql stable as $$
with m as (
  select * from live.mark_rows(now_ - interval '7 days', live.cand(now_))
), last as (
  select distinct on (bike) bike, t1, st1, case when dud then streak + 1 else 0 end chain
  from m order by bike, t0 desc
), fresh as (
  select l.*, s.name from last l left join live.stations s on s.id = l.st1
  where l.chain >= 2 and l.t1 >= now_ - interval '24 hours'
), pf as (   -- 자체 모델: 다음에 빌린 다른 사람도 바로 반납할 확률
  select f.bike, live.p_next_dud(f.chain, f.hist7_duds, f.hist7_rentals, f.prior_alarms7, f.dur_sec, f.age_h, f.shun) p,
         live.p_why(f.chain, f.hist7_duds, f.hist7_rentals, f.prior_alarms7, f.dur_sec, f.age_h, f.shun) why
  from live.p_features(now_, (select coalesce(array_agg(bike), '{}') from fresh)) f
), fp as (
  select fresh.*, pf.p, pf.why from fresh left join pf using (bike)
)
select jsonb_build_object(
  'date', 'live', 'source', 'supabase', 'at', to_char(now_, 'YYYY-MM-DD"T"HH24:MI:SS'),
  'rule', '서로 다른 사람이 3분·300m 안 반납을 2번 이상 이어서 했고, 그 뒤 정상 이용이 없는 자전거 (마지막 헛대여 24시간 안)',
  'bikes', coalesce((select jsonb_agg(jsonb_build_object(
      'bike', bike, 'station', st1, 'station_name', coalesce(name, st1), 'chain', chain,
      'level', case when chain >= 3 then '빨강' else '노랑' end,
      'last_dud', to_char(t1, 'MM-DD HH24:MI'), 'minutes_ago', floor(extract(epoch from now_ - t1) / 60)::int, 'reported', null,
      'p_next', round(100 * p)::int, 'why', why)
      order by p desc nulls last, chain desc, t1 desc) from fp), '[]'::jsonb),   -- 모델 확률 순 (목록 위 20대 정밀도가 세 달 모두 올라감, docs/model.md)
  'model', jsonb_build_object('q', live.list_q(), 'expected', round(coalesce((select sum(p) from fp), 0)::numeric, 1),
    'at_least', greatest(0, floor(coalesce((select sum(p) + live.list_q() * sqrt(sum(p * (1 - p))) from fp), 0)))::int),
  'today_alarms', (select count(*) from m where dud and not retry and streak = 1 and t1 >= date_trunc('day', now_)),
  'rentals_in_window', (select sum(total) from live.hours where hour > to_char(now_ - interval '7 days', 'YYYY-MM-DD/HH24') and hour <= to_char(now_, 'YYYY-MM-DD/HH24')),   -- API 시간별 합계(110만 행을 매번 세지 않게)
  'latest_return', (select to_char(max(t1), 'YYYY-MM-DD"T"HH24:MI:SS') from live.rentals where t1 <= now_ + interval '5 minutes'))
$$;

-- 지금 보이는 경보를 적어 둔다 (처음 본 때 = seen_at) — 채점용
-- 후보 자전거를 먼저 변수로 — 인자 자리에서 부르면 plpgsql 계획이 나빠 9~21초 걸렸다(변수면 1초, 2026-09-30)
create or replace function live.record_alarms(now_ timestamp) returns int language plpgsql as $$
declare n int; b text[] := live.cand(now_);
begin
  insert into live.alarms(bike, at, station, seen_at)
  select bike, t1, st1, now_ from live.mark_rows(now_ - interval '7 days', b)
  where dud and not retry and streak = 1 and t1 >= now_ - interval '24 hours'
  on conflict (bike, at) do nothing;
  get diagnostics n = row_count;
  if n > 0 then   -- 방금 울린 경보에 그 순간 모델 확률을 적어 둠
    update live.alarms a set p_next = live.p_next_dud(f.chain, f.hist7_duds, f.hist7_rentals, f.prior_alarms7, f.dur_sec, f.age_h, f.shun)
    from live.p_features(now_, (select coalesce(array_agg(bike), '{}') from live.alarms where seen_at = now_ and p_next is null)) f
    where a.bike = f.bike and a.seen_at = now_ and a.p_next is null;
  end if;
  return n;
end $$;

-- 매일 아침 목록 (engine/morning.py morning_lists 와 같음): 어제(d-1) 마지막 대여 기준 연쇄 2+ 인 자전거, 기록은 자정 전 7일
create table if not exists live.lists (day date primary key, generated timestamp not null, body jsonb not null);
create table if not exists live.scores (day date primary key, listed int, rode int, first_dud int, scored_at timestamp);

create or replace function live.morning(d date) returns jsonb language sql stable as $$
with c as (   -- 어제 헛대여 중 바로 앞 대여도 헛대여인 자전거 (연쇄 2+ 는 헛대여가 둘 이상 이어져야 생김 — live.cand 와 같은 생각, 답은 같음)
  select coalesce(array_agg(distinct d0.bike), '{}') b from live.rentals d0
  cross join lateral (select p.st0, p.st1, p.t0, p.t1, p.dist_m from live.rentals p where p.bike = d0.bike and p.t0 < d0.t0 order by p.t0 desc limit 1) p
  where d0.t1 >= d - 1 and d0.t0 >= d - 1 and d0.t0 < d and d0.st0 = d0.st1 and d0.t1 - d0.t0 <= interval '180 seconds' and d0.dist_m < 300
    and p.st0 = p.st1 and p.t1 - p.t0 <= interval '180 seconds' and p.dist_m < 300
), m as (
  select * from live.mark_rows((d - 7)::timestamp, (select b from c), d::timestamp)
), last as (
  select distinct on (bike) bike, t1, st1, case when dud then streak + 1 else 0 end chain
  from m where t0 >= d - 1 order by bike, t0 desc
)
select jsonb_build_object('date', to_char(d, 'YYYY-MM-DD'), 'generated', to_char((now() at time zone 'Asia/Seoul'), 'YYYY-MM-DD"T"HH24:MI:SS'), 'source', 'supabase',
  'rule', '서로 다른 사람이 3분·300m 안 반납을 2번 이상 이어서 한 뒤 아직 정상 이용이 없는 자전거',
  'bikes', coalesce(jsonb_agg(jsonb_build_object('bike', l.bike, 'station', l.st1, 'station_name', coalesce(s.name, l.st1), 'chain', l.chain,
      'level', case when l.chain >= 3 then '빨강' else '노랑' end, 'last_dud', to_char(l.t1, 'MM-DD HH24:MI'), 'reported', null)
      order by l.chain desc, l.st1), '[]'::jsonb))
from last l left join live.stations s on s.id = l.st1 where l.chain >= 2
$$;

-- 어제(d) 목록 채점 (server/daily_job.py score 와 같음): 그날 처음 빌린 '다른 사람'(재시도 아님)도 헛대여였나
create or replace function live.score_day(d date) returns void language sql as $$
with b as (select jsonb_array_elements(body->'bikes')->>'bike' bike from live.lists where day = d),
m as (select * from live.mark_rows((d - 7)::timestamp, (select coalesce(array_agg(bike), '{}') from b), (d + 1)::timestamp)),
f as (select distinct on (bike) bike, dud from m where t0 >= d and not retry order by bike, t0)
insert into live.scores(day, listed, rode, first_dud, scored_at)
select d, (select count(*) from b), (select count(*) from f), (select count(*) from f where dud), (now() at time zone 'Asia/Seoul')
where exists (select 1 from b)
on conflict (day) do update set listed = excluded.listed, rode = excluded.rode, first_dud = excluded.first_dud, scored_at = excluded.scored_at
$$;

-- 06:10: 오늘 목록 + 어제 목록 채점. 5분 예약 안에서 부르므로 06:10 이 지나 오늘 것이 없으면 만든다(늦게 켜져도)
create or replace function live.morning_job(now_ timestamp) returns void language plpgsql as $$
begin
  if now_::time >= '06:10' and not exists (select 1 from live.lists where day = now_::date) then
    insert into live.lists(day, generated, body) values (now_::date, now_, live.morning(now_::date));
    perform live.score_day(now_::date - 1);
  end if;
end $$;

-- 5분마다: 도착한 것 넣기 → 목록 만들기 → 다음 요청 (지금·직전 시간은 매번, 2~6시간 전은 30분마다, 빠진 칸은 몇 개씩)
create or replace function live.tick() returns void language plpgsql as $$
declare now_ timestamp := (now() at time zone 'Asia/Seoul')::timestamp; k int; h text; miss int := 0;
begin
  if not pg_try_advisory_xact_lock(hashtext('live.tick')) then return; end if;   -- 예약과 손으로 돌린 것이 겹치면 하나만
  perform live.collect();
  perform live.record_alarms(now_);
  perform live.settle(now_);
  perform live.morning_job(now_);
  begin   -- 스스로 배우기 자료 — 실패해도 목록은 그대로
    if extract(hour from now_)::int % 3 = 0 and extract(minute from now_)::int < 5 then perform live.sample_list(now_); end if;
    if extract(minute from now_)::int % 30 < 5 then perform live.settle_samples(now_); end if;
  exception when others then raise warning 'samples: %', sqlerrm;
  end;
  insert into live.snapshot(id, at, body) values (1, now_, live.compute(now_) || jsonb_build_object('score', live.score(now_)))
    on conflict (id) do update set at = excluded.at, body = excluded.body;
  -- 한 시간 자료는 반납 순으로 쌓인다(새 반납은 끝에 붙음, 2026-10-02 확인) → 지금·직전 시간은 마지막 꽉 찬 쪽부터만(겹쳐서 한 쪽).
  -- 30분마다 직전~6시간 전은 처음부터 다시(늦게 끼어든 기록 바로잡기). 매번 30여 쪽 → 서너 쪽.
  for k in 0..1 loop
    h := to_char(now_ - make_interval(hours => k), 'YYYY-MM-DD/HH24');
    if k = 1 and extract(minute from now_)::int % 30 < 5 then perform live.request(h);
    else perform live.request(h, greatest(1, coalesce((select total from live.hours where hour = h), 0) / 1000)); end if;
  end loop;
  if extract(minute from now_)::int % 30 < 5 then
    for k in 2..6 loop perform live.request(to_char(now_ - make_interval(hours => k), 'YYYY-MM-DD/HH24')); end loop;
  end if;
  for h in select to_char(t, 'YYYY-MM-DD/HH24') from generate_series(date_trunc('hour', now_) - interval '8 days', date_trunc('hour', now_) - interval '7 hours', interval '1 hour') t
           where to_char(t, 'YYYY-MM-DD/HH24') not in (select hour from live.hours) order by t desc loop
    exit when miss >= 6;
    perform live.request(h); miss := miss + 1;
  end loop;
  delete from live.rentals where t1 < now_ - interval '9 days';   -- t1 색인으로 (t0 로는 표 전체를 훑었다). t1 ≥ t0 라 9일 안 대여는 안 지워짐
  delete from live.alarms where at < now_ - interval '10 days' and next_dud is null;   -- 채점된 경보는 계속 둔다(작음)
end $$;

-- 앱이 읽는 곳 — 공개 키로 읽기만 (행 자료·생년·성별은 안 보임, 목록 JSON 만)
create or replace view public.live_snapshot as select at, body from live.snapshot;
create or replace view public.ops_lists as select day, body from live.lists;
create or replace view public.ops_scores as select day, listed, rode, first_dud from live.scores;
grant select on public.live_snapshot, public.ops_lists, public.ops_scores to anon, authenticated;
revoke all on all tables in schema live from anon, authenticated;

-- 예약 (5분마다). 다시 적용해도 하나만
select cron.unschedule(jobid) from cron.job where jobname = 'live-tick';
select cron.schedule('live-tick', '*/5 * * * *', 'select live.tick()');
