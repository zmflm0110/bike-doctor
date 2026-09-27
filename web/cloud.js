// 어디서든 쓰는 자료 — 맥 서버에 못 닿을 때(밖·GitHub Pages)도 앱이 진짜 앱처럼 돌게.
//   읽기: 지금 목록은 Supabase 가 5분마다 스스로(supabase/live.sql), 아침 목록·채점은 GitHub(.github/workflows/cloud.yml → live-data 가지)
//   쓰기: 구조대 확인·현장 조사 → Supabase (supabase/schema.sql — 누구나 넣기만, 읽기는 자전거별 확인 수만)
const CLOUD = {
  data: "https://raw.githubusercontent.com/zmflm0110/ridey/live-data/data/",
  sb: "https://iqvquwvoljzuvdgtbpnu.supabase.co",
  key: "sb_publishable_YFBKlBvyPFAhBpLdS3o8_A_xIeUmTVE",   // Supabase 공개(publishable) 키 — 앱에 넣는 용도의 공개 키. 비어 있으면 맥 서버로만 보낸다
};
const sbOn = () => !!CLOUD.key && !globalThis.HZ_CLOUD_OFF;   // 검사에서 맥 서버(임시 DB)로만 보낼 때 끔
function sbHeaders(extra = {}) {
  const h = { apikey: CLOUD.key, ...extra };
  if (CLOUD.key.startsWith("eyJ")) h.Authorization = `Bearer ${CLOUD.key}`;   // 예전 anon 키(JWT)만 — 새 publishable 키는 apikey 로 충분
  return h;
}
// 'spb 1234' → 'SPB-01234' (server/app.py norm_bike 와 같음)
function normBike(x) {
  const m = String(x).toUpperCase().match(/SPB\s*-?\s*(\d{3,6})/);
  return m ? `SPB-${m[1].padStart(5, "0")}` : null;
}
async function sbInsert(table, row) {
  return fetch(`${CLOUD.sb}/rest/v1/${table}`, { method: "POST", body: JSON.stringify(row),
    headers: sbHeaders({ "Content-Type": "application/json", Prefer: "return=minimal" }) });
}
// 자전거별 {판정: 명} — 구조대 확인 + 현장 조사
async function sbChecked(bike) {
  const q = bike ? `&bike=eq.${encodeURIComponent(bike)}` : "";
  const r = await fetch(`${CLOUD.sb}/rest/v1/checked?select=bike,verdict,n${q}`, { headers: sbHeaders() });
  if (!r.ok) throw new Error(r.status);
  const out = {};
  for (const x of await r.json()) (out[x.bike] = out[x.bike] || {})[x.verdict] = x.n;
  return out;
}
// 지금 목록 — Supabase 가 5분마다 스스로 만든 것 (supabase/live.sql, pg_cron). [{at, body}] → body
async function sbLive() {
  const r = await fetch(`${CLOUD.sb}/rest/v1/live_snapshot?select=at,body`, { headers: sbHeaders() });
  if (!r.ok) throw new Error(r.status);
  const x = (await r.json())[0];
  return x && x.body;
}
// 매일 아침 목록·채점 — Supabase 가 06:10 에 스스로 만든 것 (live.morning_job)
async function sbGet(path) {
  const r = await fetch(`${CLOUD.sb}/rest/v1/${path}`, { headers: sbHeaders() });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
const sbOpsDays = async () => (await sbGet("ops_lists?select=day&order=day.desc&limit=14")).map((x) => x.day).reverse();
const sbOpsList = async (day) => ((await sbGet(`ops_lists?select=body&day=eq.${day}`))[0] || {}).body;
async function sbScores() {
  const out = {};
  for (const x of await sbGet("ops_scores?select=day,listed,rode,first_dud")) out[x.day] = { listed: x.listed, rode: x.rode, first_dud: x.first_dud };
  return out;
}
// 사진(data:image/jpeg;base64,…) → 비공개 저장소, 이름(16자 hex.jpg) 돌려줌
async function sbPhoto(dataUrl) {
  const bin = atob(dataUrl.split(",")[1]);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const name = [...crypto.getRandomValues(new Uint8Array(8))].map((b) => b.toString(16).padStart(2, "0")).join("") + ".jpg";
  const r = await fetch(`${CLOUD.sb}/storage/v1/object/survey-photos/${name}`, { method: "POST", body: bytes,
    headers: sbHeaders({ "Content-Type": "image/jpeg" }) });
  if (!r.ok) throw Object.assign(new Error("photo " + r.status), { status: r.status });
  return name;
}
if (typeof module !== "undefined") module.exports = { CLOUD, normBike };
