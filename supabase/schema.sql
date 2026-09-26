-- 헛걸음 제로 — 쓰기 DB (Supabase Postgres). 앱·웹앱이 어디서든 구조대 확인·현장 조사를 보낸다.
-- 적용: psql 로 이 파일을 한 번 (server/supabase_setup.sh). 여러 번 돌려도 된다.
-- 원칙: 누구나(anon 키) '넣기' 만 된다. 행을 읽을 수는 없고, 자전거별 '사람 확인' 수(집계)만 읽는다.
--       위치·메모·사진은 우리만(DB 비밀번호) 본다.

create table if not exists public.rescue (
  id      bigint generated always as identity primary key,
  at      timestamptz not null default now(),
  bike    text not null check (bike ~ '^SPB-[0-9]{5,6}$'),
  verdict text not null check (verdict in ('체인·기어', '타이어', '안장·핸들', '브레이크', '멀쩡함')),
  day     text check (day is null or day ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
);

create table if not exists public.survey (
  id      bigint generated always as identity primary key,
  at      timestamptz not null default now(),          -- 본 시각 (폰에 모았다 늦게 보내도 그때 시각)
  station text check (station is null or char_length(station) <= 10),
  bike    text not null check (bike ~ '^SPB-[0-9]{5,6}$'),
  status  text not null check (status in ('체인·기어', '타이어', '안장·핸들', '브레이크', '멀쩡함', '기타 고장')),
  note    text check (note is null or char_length(note) <= 200),
  lat     double precision check (lat is null or lat between 33 and 39),
  lon     double precision check (lon is null or lon between 124 and 132),
  photo   text check (photo is null or photo ~ '^[0-9a-f]{16}\.jpg$')   -- 저장소 survey-photos 안 이름
);
create index if not exists rescue_bike on public.rescue (bike);
create index if not exists survey_bike on public.survey (bike);

alter table public.rescue enable row level security;
alter table public.survey enable row level security;
drop policy if exists "누구나 넣기" on public.rescue;
drop policy if exists "누구나 넣기" on public.survey;
create policy "누구나 넣기" on public.rescue for insert to anon, authenticated with check (true);
create policy "누구나 넣기" on public.survey for insert to anon, authenticated with check (true);
revoke all on public.rescue, public.survey from anon, authenticated;
grant insert on public.rescue, public.survey to anon, authenticated;

-- 자전거별 사람 확인 수 (구조대 + 현장 조사) — 앱의 '사람 확인' 표시. 행 자체는 안 보인다(뷰 주인 권한으로 집계만).
create or replace view public.checked as
  select bike, v as verdict, count(*)::int as n
  from (select bike, verdict as v from public.rescue union all select bike, status from public.survey) x
  group by bike, v;
grant select on public.checked to anon, authenticated;

-- 사진: 비공개 저장소. 누구나 올리기만(이름 16자 hex .jpg, 1MB 이하 JPEG — 폰에서 긴 변 1280px 로 줄여 보냄), 보기는 우리만.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('survey-photos', 'survey-photos', false, 1000000, array['image/jpeg'])
on conflict (id) do update set public = false, file_size_limit = 1000000, allowed_mime_types = array['image/jpeg'];
drop policy if exists "조사 사진 올리기" on storage.objects;
create policy "조사 사진 올리기" on storage.objects for insert to anon, authenticated
  with check (bucket_id = 'survey-photos' and name ~ '^[0-9a-f]{16}\.jpg$');
