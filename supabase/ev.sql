-- 전기차 충전기 상태를 클라우드 DB 가 5분마다 스스로 모은다 (2026-10-01) — GitHub 예약은 3시간에 한 번꼴이라
-- 빈틈없이 이어 찍은 구간이 0 이었다(연쇄 검증 불가). 자전거와 같은 방식: pg_cron → pg_net → 응답을 다음 차례에 넣음.
-- 자전거 예약(live-tick)과 따로 'ev-tick' 으로 돈다 — 충전기 쪽이 실패해도 자전거 목록은 그대로.
--   API: 공공데이터포털 한국환경공단 getChargerStatus, 서울(zcode 11), 최근 10분 안에 바뀐 충전기만 (5분마다 부르니 겹쳐서 빠짐없음)
--   키: Vault 'datagokr' (코드·git 에 없음)
--   저장: 충전기마다 (상태, 마지막 충전 시작·종료, 지금 충전 시작) 이 바뀐 때만 한 줄 — '상태 갱신 시각' 만 바뀐 건 안 남김(줄 수가 열 배)
--   검증은 맥에서: python tools/ev_pull.py (→ data/ev.sqlite) → python analysis/ev_validate.py (→ docs/ev_validation.md)
-- 적용: psql 로 이 파일 (여러 번 돌려도 됨)

create table if not exists live.ev_req (id bigint primary key, made_at timestamptz not null default now());
create table if not exists live.ev_runs (at timestamp primary key, items int not null);            -- 찍은 때 (빈틈 계산용)
create table if not exists live.ev_last (charger text primary key, sig text not null);            -- 충전기마다 마지막으로 본 상태
create table if not exists live.ev_snap (
  at timestamp not null,          -- 처음 본 때 (서울 시각)
  charger text not null,          -- statId-chgerId
  stat smallint, stat_upd text, ts text, te text, now_ts text   -- API 글자 그대로 (YYYYMMDDHHMMSS)
);
create index if not exists ev_snap_at on live.ev_snap (at);
alter table live.ev_snap set (autovacuum_vacuum_scale_factor = 0.05);

-- 요청 하나 (한 쪽 9,999건 — 서울 10분이면 1,200건 안팎)
create or replace function live.ev_request() returns bigint language plpgsql as $$
declare k text; id bigint;
begin
  select decrypted_secret into k from vault.decrypted_secrets where name = 'datagokr';
  if k is null then return null; end if;
  id := net.http_get('http://apis.data.go.kr/B552584/EvCharger/getChargerStatus',
                     jsonb_build_object('serviceKey', k, 'dataType', 'JSON', 'pageNo', '1', 'numOfRows', '9999', 'period', '10', 'zcode', '11'),
                     timeout_milliseconds := 30000);
  insert into live.ev_req(id) values (id);
  return id;
end $$;

-- 도착한 응답 넣기: 바뀐 상태만 ev_snap 에, 찍은 때는 ev_runs 에
create or replace function live.ev_collect() returns int language plpgsql as $$
declare q record; b jsonb; n int := 0; m int;
begin
  for q in select r.id, r.made_at, h.status_code, h.content from live.ev_req r join net._http_response h on h.id = r.id loop
    b := null;
    if q.status_code = 200 and pg_input_is_valid(q.content, 'jsonb') then b := q.content::jsonb; end if;   -- 키 오류면 XML 이 옴
    if b is not null and coalesce(b->>'resultCode', '00') in ('00', '0') then
      with it as (
        select coalesce(e->>'statId', '') || '-' || coalesce(e->>'chgerId', '') charger, nullif(e->>'stat', '')::smallint stat,
               nullif(e->>'statUpdDt', '') stat_upd, nullif(e->>'lastTsdt', '') ts, nullif(e->>'lastTedt', '') te, nullif(e->>'nowTsdt', '') now_ts
        from jsonb_array_elements(case jsonb_typeof(b->'items'->'item') when 'array' then b->'items'->'item'
                                       when 'object' then jsonb_build_array(b->'items'->'item') else '[]'::jsonb end) e
      ), sig as (
        select distinct on (charger) *, concat_ws('|', stat, ts, te, now_ts) s from it order by charger
      ), changed as (
        select s.* from sig s left join live.ev_last l on l.charger = s.charger where l.sig is distinct from s.s
      ), ins as (
        insert into live.ev_snap(at, charger, stat, stat_upd, ts, te, now_ts)
        select (q.made_at at time zone 'Asia/Seoul'), charger, stat, stat_upd, ts, te, now_ts from changed
        returning charger
      ), up as (
        insert into live.ev_last(charger, sig) select charger, s from changed
        on conflict (charger) do update set sig = excluded.sig
      )
      select count(*) into m from ins;
      insert into live.ev_runs(at, items) values ((q.made_at at time zone 'Asia/Seoul')::timestamp(0),
        jsonb_array_length(case jsonb_typeof(b->'items'->'item') when 'array' then b->'items'->'item' else '[]'::jsonb end))
        on conflict (at) do nothing;
      n := n + m;
    end if;
    delete from live.ev_req where id = q.id;
    delete from net._http_response where id = q.id;
  end loop;
  delete from live.ev_req where made_at < now() - interval '15 minutes';   -- 답 없는 요청은 버림
  delete from live.ev_snap where at < (now() at time zone 'Asia/Seoul') - interval '10 days';
  delete from live.ev_runs where at < (now() at time zone 'Asia/Seoul') - interval '10 days';
  return n;
end $$;

revoke all on live.ev_req, live.ev_runs, live.ev_last, live.ev_snap from anon, authenticated;

-- 5분마다: 도착한 것 넣고 다음 요청
create or replace function live.ev_tick() returns void language plpgsql as $$
begin
  perform live.ev_collect();
  perform live.ev_request();
end $$;
select cron.unschedule(jobid) from cron.job where jobname = 'ev-tick';
select cron.schedule('ev-tick', '*/5 * * * *', 'select live.ev_tick()');
